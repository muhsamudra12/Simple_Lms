from django.shortcuts import render, get_object_or_404, redirect
from .models import Course, Comment, User, CourseContent, ContentProgress, Certificate, Enrollment
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.core.paginator import Paginator
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Avg, Max, Min, Count
from django.db.models.functions import Cast
from django.db import models as db_models
from django.shortcuts import render
from django.http import HttpResponse
import io
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas


def index(request):
    query = request.GET.get('q')
    # Sebelumnya queryset ini TIDAK punya order_by() eksplisit, padahal
    # langsung dipaginate — Django sampai ngasih peringatan
    # (UnorderedObjectListWarning) karena tanpa urutan pasti, hasil per
    # halaman bisa TIDAK KONSISTEN (ada course yang ke-skip atau dobel
    # muncul di halaman lain) tergantung urutan internal database, dan
    # bisa beda-beda tiap request. Diurutkan terbaru dulu (-id) supaya
    # pasti konsisten dan course baru lebih kelihatan di halaman depan.
    courses = Course.objects.select_related('teacher').order_by('-id')

    if query:
        courses = courses.filter(name__icontains=query)

    # Pagination — sebelumnya semua kursus di-load sekaligus tanpa batas,
    # jadi kalau jumlah kursus terus bertambah, halaman beranda makin
    # berat. 9 kursus per halaman (pas untuk grid 3 kolom x 3 baris).
    paginator = Paginator(courses, 9)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Progress per kursus sekarang dihitung dari ContentProgress di
    # database (per-video, milik user yang login), bukan dari session
    # browser lagi — sebelumnya progress hilang kalau ganti device/clear
    # cookie, dan tidak bisa dilihat/diedit dari Admin sama sekali.
    #
    # Rating per kursus (gaya Udemy/Coursera: bintang + rata-rata + jumlah
    # ulasan langsung MENYATU di kartu kursusnya) dihitung di sini juga —
    # menggantikan section testimoni terpisah sebelumnya, supaya rating &
    # komentar terasa jadi satu kesatuan sama course-nya, bukan section
    # yang berdiri sendiri di tempat lain.
    user_id = request.session.get('user_id')

    # Status enrollment per kursus di kartu homepage — diambil sekali pakai
    # satu query (set of course_id) per halaman, bukan query berulang per
    # kartu, biar tetap ringan. Tombol "Ambil Kursus"/"Buka Kursus" di
    # kartu langsung mencerminkan status ini (mirip Udemy/Coursera: enroll
    # dulu sebelum bisa buka materi penuh).
    enrolled_course_ids = set()
    if user_id:
        enrolled_course_ids = set(
            Enrollment.objects.filter(student_id=user_id, status='paid').values_list('course_id', flat=True)
        )

    for c in page_obj:
        total = c.contents.count()
        c.total_content = total
        c.is_enrolled = c.id in enrolled_course_ids
        enrolled_count = Enrollment.objects.filter(course=c).count()
        c.slots_left = max(0, c.max_students - enrolled_count)
        if user_id and c.is_enrolled and total > 0:
            done = ContentProgress.objects.filter(user_id=user_id, content__course=c).count()
            c.progress_pct = int(done / total * 100)
        else:
            c.progress_pct = 0

        course_rating = c.comments.aggregate(avg=Avg('rating'), total=Count('id'))
        c.avg_rating = round(course_rating['avg'], 1) if course_rating['avg'] else None
        c.review_count = course_rating['total']

    # Statistik hero section — SEBELUMNYA pakai `courses|length` di
    # template, yang cuma ngitung jumlah kursus DI HALAMAN PAGINATION INI
    # SAJA (maks 9), bukan total semua kursus. Jadi kalau ada >9 kursus,
    # angka yang ditampilkan SALAH (kurang). Dihitung di sini pakai
    # `paginator.count` (total asli, lepas dari pagination) supaya benar.
    total_courses = paginator.count
    rating_stats = Comment.objects.aggregate(avg_rating=Avg('rating'), total_reviews=Count('id'))

    return render(request, 'tasks/index.html', {
        'courses': page_obj,
        'page_obj': page_obj,
        'query': query,
        'total_courses': total_courses,
        'avg_rating': round(rating_stats['avg_rating'], 1) if rating_stats['avg_rating'] else None,
        'total_reviews': rating_stats['total_reviews'],
    })


def detail(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    comments = course.comments.all()

    # Halaman detail kursus sekarang BISA dibuka tanpa login — supaya
    # pengunjung baru bisa lihat preview (deskripsi, daftar materi,
    # komentar/review) dulu sebelum memutuskan daftar, alih-alih
    # langsung di-redirect ke halaman login tanpa lihat apa-apa
    # (kurang menarik buat konversi pengunjung baru).
    #
    # Yang TETAP wajib login: menonton video sungguhan & menandai materi
    # selesai (lihat di bawah serta di template — guest cuma lihat
    # placeholder terkunci untuk bagian video).
    user_id = request.session.get('user_id')

    # Status enrollment — SEBELUMNYA model Enrollment ini sudah ada
    # (lengkap dengan cek kuota max_students), tapi TIDAK PERNAH dipakai
    # di halaman web sama sekali. Akibatnya siapapun yang login bisa
    # langsung buka & nonton semua materi tanpa benar-benar "mengambil"
    # course-nya dulu — gak ada gate apapun. Sekarang materi cuma
    # terbuka kalau user sudah enroll DENGAN status 'paid'.
    enrollment = None
    if user_id:
        enrollment = Enrollment.objects.filter(course=course, student_id=user_id).first()
    is_enrolled = bool(enrollment and enrollment.status == 'paid')

    if request.method == "POST":

        # ── Ambil Kursus (Enrollment) ──────────────────────────
        if 'ambil_kursus' in request.POST:
            if not user_id:
                messages.error(request, "Silakan login dulu untuk mengambil kursus ini.")
                return redirect('login_page')
            try:
                Enrollment.objects.create(course=course, student_id=user_id, status='paid')
                messages.success(request, f"Berhasil mengambil kursus '{course.name}'! Selamat belajar 🎉")
            except ValidationError as e:
                # Dilempar dari Enrollment._check_capacity() — kuota penuh
                messages.error(request, str(e.message) if hasattr(e, "message") else str(e))
            except IntegrityError:
                # unique_together (course, student) — sudah pernah enroll
                messages.error(request, "Kamu sudah terdaftar di kursus ini.")
            return redirect('course_detail', course_id=course.id)

        # ── Tandai Materi Selesai/Belum (per-video) ───────────────
        if 'toggle_content' in request.POST:
            if not user_id:
                messages.error(request, "Silakan login dulu untuk menandai materi selesai.")
                return redirect('login_page')
            if not is_enrolled:
                messages.error(request, "Ambil kursus ini dulu sebelum menandai materi selesai.")
                return redirect('course_detail', course_id=course.id)
            content_id = request.POST.get('content_id')
            content = get_object_or_404(CourseContent, id=content_id, course=course)
            progress, created = ContentProgress.objects.get_or_create(user_id=user_id, content=content)
            if not created:
                # Sudah ada sebelumnya -> klik lagi artinya batalkan tanda selesai
                progress.delete()
                messages.success(request, f"'{content.name}' ditandai belum selesai.")
            else:
                messages.success(request, f"'{content.name}' ditandai selesai!")
            return redirect('course_detail', course_id=course.id)

        # ── Kirim Komentar ────────────────────────────────────
        elif 'kirim_komentar' in request.POST:
            nama = request.POST.get('nama_komentator', '').strip()
            isi = request.POST.get('isi_komentar', '').strip()

            # Rate-limit sederhana berbasis IP — sebelumnya form ini bisa
            # disubmit berkali-kali tanpa batas (rawan spam), beda dengan
            # endpoint API komentar yang sudah dipasangi throttle.
            ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
            throttle_key = f"comment_throttle_{ip}"
            if cache.get(throttle_key):
                messages.error(request, "Tunggu beberapa saat sebelum mengirim komentar lagi.")
                return redirect('course_detail', course_id=course.id)

            if not nama or not isi:
                messages.error(request, "Nama dan isi komentar tidak boleh kosong.")
            else:
                # Rating dari form bintang — divalidasi & dipaksa ke rentang
                # 1-5. Kalau user kirim request manual tanpa lewat UI (atau
                # field-nya ke-skip), default ke 5 daripada 0/invalid.
                try:
                    rating = int(request.POST.get('rating', 5))
                except (TypeError, ValueError):
                    rating = 5
                rating = max(1, min(5, rating))

                Comment.objects.create(
                    course=course,
                    nama_komentator=nama,
                    isi_komentar=isi,
                    rating=rating,
                )
                cache.set(throttle_key, True, 10)  # 1 komentar / 10 detik per IP
                messages.success(request, "Komentar berhasil dikirim!")

            return redirect('course_detail', course_id=course.id)

    # Diurutkan eksplisit (.order_by sudah didukung Meta.ordering di model,
    # tapi dipanggil lagi di sini biar jelas & tidak bergantung diam-diam
    # ke Meta) — penting karena "materi pertama" dipakai sebagai preview
    # gratis di bawah, jadi urutannya harus konsisten.
    contents = course.contents.all().order_by('id')
    first_content = contents.first()
    first_content_id = first_content.id if first_content else None

    done_ids = set(
        ContentProgress.objects.filter(user_id=user_id, content__course=course).values_list('content_id', flat=True)
    )
    total = contents.count()
    progress_pct = int(len(done_ids) / total * 100) if total > 0 else 0
    is_course_complete = total > 0 and progress_pct == 100

    # Sertifikat di-issue OTOMATIS begitu progress kursus mencapai 100% —
    # disimpan permanen (get_or_create) supaya tanggal terbit & kode
    # verifikasinya tidak berubah-ubah tiap halaman ini dibuka ulang.
    certificate = None
    if user_id and is_enrolled and is_course_complete:
        certificate, _ = Certificate.objects.get_or_create(
            user_id=user_id, course=course
        )

    # Sisa kuota — ditampilkan di tombol "Ambil Kursus" biar transparan
    # (sama persis logika yang dipakai Enrollment._check_capacity()).
    enrolled_count = Enrollment.objects.filter(course=course).count()
    slots_left = max(0, course.max_students - enrolled_count)

    # Rating khusus course ini (beda dengan rating situs-wide di homepage)
    # — dipakai di hero section halaman preview.
    course_rating = course.comments.aggregate(avg=Avg('rating'), total=Count('id'))
    course_avg_rating = round(course_rating['avg'], 1) if course_rating['avg'] else None
    course_review_count = course_rating['total']

    return render(request, 'tasks/detail.html', {
        'course': course,
        'comments': comments,
        'contents': contents,
        'done_ids': done_ids,
        'progress_pct': progress_pct,
        'total_content': total,
        'is_course_complete': is_course_complete,
        'certificate': certificate,
        'is_enrolled': is_enrolled,
        'enrollment': enrollment,
        'slots_left': slots_left,
        'enrolled_count': enrolled_count,
        'first_content_id': first_content_id,
        'course_avg_rating': course_avg_rating,
        'course_review_count': course_review_count,
    })


def stats_view(request):
    # Statistik harga kursus sengaja dibatasi cuma untuk user yang sudah
    # login — pengunjung baru/belum daftar tidak diarahkan lihat data ini
    # duluan (supaya angka mentah tidak jadi alasan ragu sebelum sempat
    # eksplorasi konten kursusnya).
    if not request.session.get('user_id'):
        messages.error(request, "Silakan login dulu untuk melihat statistik kursus.")
        return redirect('login_page')

    stats = Course.objects.aggregate(
        total_course=Count('id'),
        avg_price=Avg('price'),
        max_price=Max('price'),
        min_price=Min('price')
    )

    # Cast ke IntegerField agar sort numerik
    cheapest_course = Course.objects.select_related('teacher').order_by(
        Cast('price', output_field=db_models.IntegerField())
    ).first()

    # Semua kursus diurutkan termurah ke termahal untuk tabel ranking
    all_courses = Course.objects.select_related('teacher').order_by(
        Cast('price', output_field=db_models.IntegerField())
    )

    return render(request, 'tasks/stats.html', {
        'stats': stats,
        'cheapest_course': cheapest_course,
        'all_courses': all_courses,
    })

def courses_page(request):
    # Halaman Grid Card kursus (versi tampilan terpisah, dipakai manual / belum dirutekan)
    return render(request, 'tasks/courses.html')


# ─────────────────────────────────────────────
# 🔐 LOGIN / REGISTER / LOGOUT (WEBSITE)
# Session-based, terpisah dari JWT yang dipakai endpoint API
# (/api/v2/auth/...) — keduanya sengaja independen: API dipakai oleh
# Postman/aplikasi eksternal dengan token, sementara website memakai
# session Django biasa supaya navbar bisa langsung tahu status login
# tanpa perlu JS menyimpan token di localStorage.
# ─────────────────────────────────────────────
def login_page(request):
    if request.session.get('user_id'):
        return redirect('index')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        # Rate-limit sederhana biar nggak bisa di-brute-force lewat form web
        ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        throttle_key = f"login_throttle_{ip}"
        attempts = cache.get(throttle_key, 0)
        if attempts >= 5:
            messages.error(request, "Terlalu banyak percobaan login. Coba lagi dalam 1 menit.")
            # Username tetap ditampilkan ulang biar nggak perlu ngetik dari nol
            # (password SENGAJA tidak dikembalikan, demi keamanan).
            return render(request, 'tasks/login.html', {'username': username})

        user = User.objects.filter(username=username).first()
        if user and check_password(password, user.password):
            request.session['user_id'] = user.id
            cache.delete(throttle_key)
            messages.success(request, f"Selamat datang kembali, {user.fullname}!")
            return redirect('index')
        else:
            cache.set(throttle_key, attempts + 1, 60)
            messages.error(request, "Username atau password salah.")
            return render(request, 'tasks/login.html', {'username': username})

    return render(request, 'tasks/login.html')


def register_page(request):
    if request.session.get('user_id'):
        return redirect('index')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        fullname = request.POST.get('fullname', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        # Form sticky: kalau gagal, field selain password ditampilkan ulang
        # biar nggak perlu ngetik dari nol (password TIDAK pernah di-echo
        # balik, demi keamanan).
        sticky = {'username': username, 'fullname': fullname, 'email': email}

        # Rate-limit — sebelumnya form registrasi web belum dibatasi sama
        # sekali (beda dengan endpoint API /auth/register yang sudah ada
        # throttle), jadi bisa dipakai bikin akun spam tanpa batas.
        ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        throttle_key = f"register_throttle_{ip}"
        attempts = cache.get(throttle_key, 0)
        if attempts >= 5:
            messages.error(request, "Terlalu banyak percobaan registrasi. Coba lagi dalam 1 menit.")
            return render(request, 'tasks/register.html', sticky)

        if not all([username, fullname, email, password]):
            cache.set(throttle_key, attempts + 1, 60)
            messages.error(request, "Semua field wajib diisi.")
            return render(request, 'tasks/register.html', sticky)
        elif User.objects.filter(username=username).exists():
            cache.set(throttle_key, attempts + 1, 60)
            messages.error(request, "Username sudah digunakan, coba yang lain.")
            return render(request, 'tasks/register.html', sticky)
        else:
            User.objects.create(
                username=username,
                fullname=fullname,
                email=email,
                password=make_password(password),
            )
            cache.delete(throttle_key)
            messages.success(request, "Registrasi berhasil! Silakan login.")
            return redirect('login_page')

    return render(request, 'tasks/register.html')


def logout_view(request):
    request.session.pop('user_id', None)
    messages.success(request, "Kamu berhasil logout.")
    return redirect('index')


def profile_page(request):
    user_id = request.session.get('user_id')
    if not user_id:
        messages.error(request, "Silakan login dulu untuk mengakses halaman ini.")
        return redirect('login_page')

    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        fullname = request.POST.get('fullname', '').strip()
        email = request.POST.get('email', '').strip()
        current_password = request.POST.get('current_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if not fullname or not email:
            messages.error(request, "Nama dan email tidak boleh kosong.")
            return render(request, 'tasks/profile.html', {'profile_user': user})

        # Ganti password itu OPSIONAL — cuma diproses kalau field current_password
        # diisi. Wajib cocok dulu dengan password lama sebelum boleh diganti,
        # supaya orang yang numpang lewat di sesi login yang lagi terbuka
        # (misal di komputer bersama) tidak bisa asal ganti password tanpa
        # tahu password aslinya.
        if current_password:
            ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
            throttle_key = f"profile_pw_throttle_{user.id}_{ip}"
            attempts = cache.get(throttle_key, 0)
            if attempts >= 5:
                messages.error(request, "Terlalu banyak percobaan. Coba lagi dalam 1 menit.")
                return render(request, 'tasks/profile.html', {'profile_user': user})

            if not check_password(current_password, user.password):
                cache.set(throttle_key, attempts + 1, 60)
                messages.error(request, "Password lama yang kamu masukkan salah.")
                return render(request, 'tasks/profile.html', {'profile_user': user})

            cache.delete(throttle_key)

            if not new_password:
                messages.error(request, "Isi password baru kalau ingin menggantinya.")
                return render(request, 'tasks/profile.html', {'profile_user': user})
            if new_password != confirm_password:
                messages.error(request, "Konfirmasi password baru tidak cocok.")
                return render(request, 'tasks/profile.html', {'profile_user': user})
            if len(new_password) < 6:
                messages.error(request, "Password baru minimal 6 karakter.")
                return render(request, 'tasks/profile.html', {'profile_user': user})

            user.password = make_password(new_password)

        # Validasi username/email unik milik orang lain
        if User.objects.filter(email=email).exclude(id=user.id).exists():
            messages.error(request, "Email itu sudah dipakai akun lain.")
            return render(request, 'tasks/profile.html', {'profile_user': user})

        user.fullname = fullname
        user.email = email

        # Upload foto profil — opsional, cuma diproses kalau user benar-benar
        # pilih file baru. Validasi tipe & ukuran file biar tidak sembarang
        # file besar/non-gambar ke-upload.
        new_image = request.FILES.get('profile_image')
        if new_image:
            if not new_image.content_type.startswith('image/'):
                messages.error(request, "File yang diupload harus berupa gambar.")
                return render(request, 'tasks/profile.html', {'profile_user': user})
            if new_image.size > 2 * 1024 * 1024:
                messages.error(request, "Ukuran gambar maksimal 2MB.")
                return render(request, 'tasks/profile.html', {'profile_user': user})
            user.profile_image = new_image

        user.save()
        messages.success(request, "Profil berhasil diperbarui.")
        return redirect('profile_page')

    return render(request, 'tasks/profile.html', {'profile_user': user})


# ─────────────────────────────────────────────
# 🏆 SERTIFIKAT KURSUS
# Diakses lewat kode unik (UUID), bukan ID urut biasa — supaya orang lain
# (misal HRD perusahaan yang ingin verifikasi) bisa lihat halaman ini
# TANPA perlu login, tapi tidak bisa asal nebak-nebak sertifikat siapapun
# cuma dengan mengganti angka di URL (seperti /certificate/1/, /2/, dst).
# Sengaja TIDAK dibatasi cuma untuk pemiliknya sendiri, karena tujuan
# utama halaman verifikasi publik adalah supaya pihak ketiga bisa
# memastikan keasliannya tanpa perlu akun.
# ─────────────────────────────────────────────
_BULAN_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def format_indo_date(dt):
    """
    LANGUAGE_CODE project ini 'en-us' (dipakai juga oleh Admin & komponen
    lain), jadi filter `|date` Django bawaan bakal nampilin nama bulan
    Inggris (June, dst). Khusus halaman sertifikat — yang seluruh teks
    lainnya Bahasa Indonesia — tanggal di-format manual di sini saja,
    tanpa perlu mengubah LANGUAGE_CODE global project.
    """
    return f"{dt.day} {_BULAN_ID[dt.month - 1]} {dt.year}"


def certificate_view(request, code):
    certificate = get_object_or_404(Certificate, code=code)
    return render(request, 'tasks/certificate.html', {
        'certificate': certificate,
        'issued_at_id': format_indo_date(certificate.issued_at),
    })


def certificate_pdf(request, code):
    certificate = get_object_or_404(Certificate, code=code)

    buffer = io.BytesIO()
    page_size = landscape(A4)
    pdf = canvas.Canvas(buffer, pagesize=page_size)
    width, height = page_size

    navy = HexColor('#0a0f2c')
    accent = HexColor('#f59e0b')
    muted = HexColor('#64748b')

    # Border ganda biar kelihatan kayak sertifikat resmi, bukan dokumen biasa
    pdf.setStrokeColor(navy)
    pdf.setLineWidth(3)
    pdf.rect(1.2 * cm, 1.2 * cm, width - 2.4 * cm, height - 2.4 * cm)
    pdf.setStrokeColor(accent)
    pdf.setLineWidth(1)
    pdf.rect(1.6 * cm, 1.6 * cm, width - 3.2 * cm, height - 3.2 * cm)

    center_x = width / 2

    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawCentredString(center_x, height - 3.2 * cm, "LMS ACADEMY")

    pdf.setFillColor(accent)
    pdf.setFont("Helvetica-Bold", 30)
    pdf.drawCentredString(center_x, height - 5 * cm, "SERTIFIKAT PENYELESAIAN")

    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(center_x, height - 6.5 * cm, "Dengan ini menyatakan bahwa")

    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 26)
    pdf.drawCentredString(center_x, height - 8 * cm, certificate.user.fullname)

    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(center_x, height - 9.3 * cm, "telah berhasil menyelesaikan seluruh materi kursus")

    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawCentredString(center_x, height - 10.6 * cm, certificate.course.name)

    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 11)
    pdf.drawCentredString(
        center_x, height - 12.5 * cm,
        f"Diterbitkan pada {format_indo_date(certificate.issued_at)}"
    )

    # Tanda tangan pengajar (nama teacher dari Course)
    pdf.setStrokeColor(muted)
    pdf.line(center_x - 4 * cm, 3.6 * cm, center_x + 4 * cm, 3.6 * cm)
    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawCentredString(center_x, 3.1 * cm, certificate.course.teacher.fullname)
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(center_x, 2.6 * cm, "Pengajar Kursus")

    # Kode verifikasi di pojok bawah — biar bisa dicek ulang keasliannya
    pdf.setFont("Helvetica", 8)
    pdf.drawCentredString(center_x, 2 * cm, f"Kode Verifikasi: {certificate.code}")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    filename = f"Sertifikat-{certificate.course.name}-{certificate.user.fullname}.pdf".replace(" ", "_")
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response