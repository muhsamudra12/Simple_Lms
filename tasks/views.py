from django.shortcuts import render, get_object_or_404, redirect
from .models import (
    Course, Comment, User, CourseContent, ContentProgress, Certificate,
    Enrollment, AccountToken,
)
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.core.paginator import Paginator
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.conf import settings
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

# Konfigurasi durasi PREVIEW GRATIS (materi pertama, untuk user yang belum
# enroll) — dihitung OTOMATIS sebagai persentase dari `duration_seconds`
# milik CourseContent (kalau diisi admin), supaya admin tidak perlu
# menghitung manual angka detik preview satu-satu per video. Dibatasi
# MIN/MAX biar tidak kepanjangan (kasih semua isinya) atau kependekan
# (gak kelihatan apa-apa).
PREVIEW_PERCENTAGE = 0.20      # 20% dari total durasi video
PREVIEW_MIN_SECONDS = 20
PREVIEW_MAX_SECONDS = 90
PREVIEW_DEFAULT_SECONDS = 60   # dipakai kalau duration_seconds tidak diisi


def _build_preview_url(video_url, duration_seconds):
    """
    Bangun URL embed YouTube dengan parameter `end=` supaya video otomatis
    berhenti di detik tertentu — dipakai HANYA untuk preview gratis materi
    pertama bagi yang belum enroll. CATATAN PENTING: ini cuma soft-limit
    sisi client (parameter URL bawaan YouTube), BUKAN proteksi keamanan —
    video sebenarnya tetap bisa diputar ulang/di-seek manual oleh user
    yang cukup paham. Untuk tujuan "kasih bocoran materi", ini cukup.
    """
    if duration_seconds:
        preview_seconds = int(duration_seconds * PREVIEW_PERCENTAGE)
        preview_seconds = max(PREVIEW_MIN_SECONDS, min(PREVIEW_MAX_SECONDS, preview_seconds))
    else:
        preview_seconds = PREVIEW_DEFAULT_SECONDS
    sep = '&' if '?' in video_url else '?'
    return f"{video_url}{sep}start=0&end={preview_seconds}", preview_seconds


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /silk/",
        "Disallow: /kursus-saya/",
        "Disallow: /profile/",
        "Disallow: /reset-password/",
        "Disallow: /verify-email/",
        f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def sitemap_xml(request):
    # Sengaja bikin manual ringan (bukan pakai django.contrib.sitemaps)
    # supaya gak perlu nambah app baru di INSTALLED_APPS cuma buat ini —
    # isinya cuma homepage + semua halaman detail course (yang memang
    # ditujukan buat publik/guest, sesuai desain preview yang sudah ada).
    urls = [request.build_absolute_uri('/')]
    for course in Course.objects.order_by('-id').values_list('id', flat=True):
        urls.append(request.build_absolute_uri(f'/course/{course}/'))

    xml_items = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{xml_items}</urlset>'
    return HttpResponse(xml, content_type="application/xml")


def index(request):
    query = request.GET.get('q')
    category_filter = request.GET.get('category', '').strip()
    price_filter = request.GET.get('price_range', '').strip()

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

    if category_filter:
        courses = courses.filter(category=category_filter)

    # Filter rentang harga — pakai preset (bukan input angka manual) biar
    # gampang dipakai dan gak butuh validasi rentang angka custom.
    PRICE_RANGES = {
        'free': (0, 0),
        'under_100k': (0, 99999),
        '100k_300k': (100000, 300000),
        'above_300k': (300001, None),
    }
    if price_filter in PRICE_RANGES:
        min_p, max_p = PRICE_RANGES[price_filter]
        courses = courses.filter(price__gte=min_p)
        if max_p is not None:
            courses = courses.filter(price__lte=max_p)

    # Daftar kategori buat dropdown filter — diambil dinamis dari data
    # yang ada (bukan hardcode), karena `category` di model bebas teks.
    available_categories = (
        Course.objects.exclude(category__isnull=True).exclude(category__exact='')
        .values_list('category', flat=True).distinct().order_by('category')
    )

    # Pagination — sebelumnya semua kursus di-load sekaligus tanpa batas,
    # jadi kalau jumlah kursus terus bertambah, halaman beranda makin
    # berat. 9 kursus per halaman (pas untuk grid 3 kolom x 3 baris).
    paginator = Paginator(courses, 9)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # PERBAIKAN PERFORMA: sebelumnya tiap kartu course manggil
    # `.count()`/`.aggregate()` sendiri² (contents, comments, enrollments)
    # — untuk 9 course di 1 halaman ini jadi >100 query database, padahal
    # cuma nampilin 9 kartu! `.count()`/`.aggregate()` SELALU bikin query
    # baru ke database, gak peduli udah di-prefetch atau belum.
    #
    # Di-fix pakai `prefetch_related`: semua content/comment/enrollment
    # dari kursus-kursus di halaman ini di-ambil sekaligus (3 query
    # total, bukan 3 query PER KURSUS), lalu dihitung manual di Python
    # dari hasil prefetch (`.all()`, bukan `.count()`/`.aggregate()` lagi).
    #
    # Sengaja TIDAK pakai `.annotate(Count(...), Avg(...))` gabungan di
    # satu query untuk relasi yang berbeda (contents + comments +
    # enrollments sekaligus) — itu rawan bug "JOIN fan-out" di Django:
    # angka rata-rata rating bisa salah/menggelembung karena baris
    # comment ke-duplikat sebanyak baris content lewat JOIN gabungan.
    # Pakai prefetch + hitung manual lebih lambat dikit tapi DIJAMIN benar.
    page_obj.object_list = list(
        page_obj.object_list.prefetch_related('contents', 'comments', 'enrollments')
    )

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
        all_contents = c.contents.all()       # sudah dari cache prefetch, bukan query baru
        all_comments = c.comments.all()       # sudah dari cache prefetch, bukan query baru
        all_enrollments = c.enrollments.all() # sudah dari cache prefetch, bukan query baru

        total = len(all_contents)
        c.total_content = total
        c.is_enrolled = c.id in enrolled_course_ids
        c.slots_left = max(0, c.max_students - len(all_enrollments))

        if user_id and c.is_enrolled and total > 0:
            content_ids_in_course = {ct.id for ct in all_contents}
            done = ContentProgress.objects.filter(
                user_id=user_id, content_id__in=content_ids_in_course
            ).count()
            c.progress_pct = int(done / total * 100)
            # Sama seperti di my_courses_page(): jaring pengaman supaya
            # sertifikat tetap ke-generate walau user nyelesain materi
            # terakhir lalu cuma balik ke homepage (gak pernah ke halaman
            # detail course-nya lagi).
            _, just_issued = _issue_certificate_if_complete(user_id, c, c.progress_pct, total)
            if just_issued:
                messages.success(request, f"🎉 Selamat! Kamu menyelesaikan kursus '{c.name}' dan sertifikatnya sudah siap diunduh!")
        else:
            c.progress_pct = 0

        ratings = [com.rating for com in all_comments]
        c.avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None
        c.review_count = len(ratings)

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
        'available_categories': available_categories,
        'category_filter': category_filter,
        'price_filter': price_filter,
        'is_filtered': bool(query or category_filter or price_filter),
    })


def _issue_certificate_if_complete(user_id, course, progress_pct, total_content):
    """
    Helper bersama buat auto-issue sertifikat — SEBELUMNYA logic ini cuma
    ada di dalam detail() view, jadi kalau user menyelesaikan materi
    terakhir lalu TIDAK PERNAH balik lagi ke halaman detail course itu
    (misal langsung ke halaman 'Kursus Saya'), sertifikatnya TIDAK PERNAH
    benar-benar ke-generate di database — padahal halaman lain (My
    Courses) sudah menampilkannya seolah-olah 100% selesai. Sekarang
    logic-nya disatukan di sini, dipanggil dari KEDUA halaman.

    Return (certificate, created) — `created=True` cuma kalau ini BENERAN
    baru pertama kali ke-generate (dipakai buat nampilin pesan perayaan
    sekali doang, bukan tiap kali halaman dibuka ulang).
    """
    is_complete = total_content > 0 and progress_pct == 100
    if user_id and is_complete:
        return Certificate.objects.get_or_create(user_id=user_id, course=course)
    return None, False


def detail(request, course_id):
    course = get_object_or_404(Course, id=course_id)

    # Pagination komentar — sebelumnya SEMUA komentar course di-load
    # sekaligus tanpa batas (`course.comments.all()` langsung dirender).
    # Untuk course populer dengan ratusan/ribuan komentar, ini bikin
    # halaman detail berat banget. 10 komentar per halaman.
    total_comment_count = course.comments.count()
    comment_paginator = Paginator(course.comments.all(), 10)
    comment_page_number = request.GET.get('comment_page', 1)
    comments = comment_paginator.get_page(comment_page_number)

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
    # Diurutkan pakai field `order` (admin bisa atur manual lewat Admin)
    # dengan `id` sebagai tiebreaker kalau order-nya sama — penting karena
    # "materi pertama" dipakai sebagai preview gratis di bawah, jadi
    # urutannya harus konsisten & sesuai yang diatur admin.
    contents = course.contents.all().order_by('order', 'id')
    first_content = contents.first()
    first_content_id = first_content.id if first_content else None

    # URL video yang BENERAN dipakai di <iframe> — dibedain per kondisi:
    # - Sudah enroll: video penuh, tanpa batasan apapun.
    # - Belum enroll, ini materi preview gratis (materi pertama): video
    #   dipotong otomatis sesuai PREVIEW_PERCENTAGE dari duration_seconds.
    # - Belum enroll, materi lain: tidak perlu URL sama sekali (di
    #   template dirender sebagai locked-row, bukan <iframe>).
    preview_seconds = None
    for content in contents:
        if is_enrolled:
            content.display_url = content.video_url
        elif content.id == first_content_id:
            content.display_url, preview_seconds = _build_preview_url(
                content.video_url, content.duration_seconds
            )
        else:
            content.display_url = None

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
    if is_enrolled:
        certificate, just_issued = _issue_certificate_if_complete(user_id, course, progress_pct, total)
        if just_issued:
            messages.success(request, f"🎉 Selamat! Kamu menyelesaikan kursus '{course.name}' dan sertifikatnya sudah siap diunduh!")

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
        'total_comment_count': total_comment_count,
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
        'preview_seconds': preview_seconds,
        'course_avg_rating': course_avg_rating,
        'course_review_count': course_review_count,
    })


def stats_view(request):
    # PERBAIKAN: sebelumnya halaman ini cuma syaratnya "sudah login" di
    # WEBSITE (session LMS biasa) — padahal isinya statistik internal
    # (rata-rata harga semua kursus, ranking semua kursus) yang sebetulnya
    # lebih cocok buat admin, bukan student biasa. Sekarang disamakan
    # dengan cara Silk diproteksi: wajib login sebagai STAFF Django
    # (`request.user.is_staff` — sistem auth Django bawaan, BEDA dengan
    # session LMS kita), bukan cuma "user yang sudah login di LMS".
    if not (request.user.is_authenticated and request.user.is_staff):
        messages.error(request, "Halaman ini cuma untuk admin.")
        return redirect(f"/admin/login/?next={request.path}")

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
def _send_verification_email(request, user):
    """Bikin AccountToken baru + 'kirim' email verifikasi (lihat EMAIL_BACKEND di settings.py — default console, ganti env var buat SMTP asli)."""
    token = AccountToken.objects.create(user=user, token_type='verify_email')
    # Sengaja pakai request.build_absolute_uri() (BUKAN settings.SITE_BASE_URL
    # statis) — supaya link di email otomatis pakai domain yang BENERAN
    # diakses user saat itu (localhost pas dev, domain Railway pas
    # production) tanpa gantung env var yang gampang lupa di-set. Kalau
    # sebelumnya pakai SITE_BASE_URL dan env var-nya kosong, SEMUA link di
    # email bakal ngarah ke "http://localhost:8000/..." yang sama sekali
    # tidak bisa diakses user di production.
    link = request.build_absolute_uri(f'/verify-email/{token.token}/')
    send_mail(
        subject="Verifikasi Email — LMS Academy",
        message=(
            f"Hai {user.fullname},\n\n"
            f"Terima kasih sudah daftar di LMS Academy. Klik link di bawah untuk verifikasi email kamu:\n\n"
            f"{link}\n\n"
            f"Link ini berlaku 24 jam. Kalau bukan kamu yang daftar, abaikan saja email ini."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,  # jangan sampai registrasi gagal total cuma karena SMTP lagi bermasalah
    )


def _send_password_reset_email(request, user):
    token = AccountToken.objects.create(user=user, token_type='reset_password')
    link = request.build_absolute_uri(f'/reset-password/{token.token}/')
    send_mail(
        subject="Reset Password — LMS Academy",
        message=(
            f"Hai {user.fullname},\n\n"
            f"Ada permintaan reset password untuk akun kamu. Klik link di bawah (berlaku 1 jam):\n\n"
            f"{link}\n\n"
            f"Kalau bukan kamu yang minta, abaikan saja email ini — password kamu tidak akan berubah."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )


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
            if not user.is_verified:
                # Sengaja TIDAK login-kan dulu — verifikasi email wajib
                # sebelum bisa masuk web (beda dengan endpoint API login
                # yang tetap longgar, dipakai buat testing/Postman).
                messages.error(
                    request,
                    "Email kamu belum diverifikasi. Cek inbox/folder spam, "
                    "atau kirim ulang link verifikasi di bawah."
                )
                return render(request, 'tasks/login.html', {
                    'username': username,
                    'show_resend_verification': True,
                })
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
        elif User.objects.filter(email=email).exists():
            # Sebelumnya TIDAK ada pengecekan ini sama sekali — siapapun
            # bisa daftar berkali-kali pakai email yang SAMA. Ini bikin
            # fitur "lupa password" & "kirim ulang verifikasi" jadi gak
            # bisa diandalkan (keduanya cari user berdasarkan email —
            # kalau ada 2+ akun dengan email sama, cuma yang PERTAMA
            # ketemu yang ke-proses, yang lain tidak kebagian).
            cache.set(throttle_key, attempts + 1, 60)
            messages.error(request, "Email itu sudah dipakai akun lain.")
            return render(request, 'tasks/register.html', sticky)
        else:
            user = User.objects.create(
                username=username,
                fullname=fullname,
                email=email,
                password=make_password(password),
                is_verified=False,
            )
            _send_verification_email(request, user)
            cache.delete(throttle_key)
            messages.success(
                request,
                "Registrasi berhasil! Cek email kamu (termasuk folder spam) "
                "untuk link verifikasi sebelum bisa login."
            )
            return redirect('login_page')

    return render(request, 'tasks/register.html')


def logout_view(request):
    # Sebelumnya logout bisa di-trigger lewat GET (link biasa), padahal
    # logout itu mengubah state (session). Konvensi keamanan web: aksi
    # yang mengubah state harus lewat POST, supaya tidak bisa di-trigger
    # diam-diam dari halaman lain (misal <img src=".../logout/"> di situs
    # jahat bisa otomatis nge-logout user tanpa mereka sadar/setuju).
    if request.method != 'POST':
        return redirect('index')
    request.session.pop('user_id', None)
    messages.success(request, "Kamu berhasil logout.")
    return redirect('index')


def verify_email_page(request, token):
    account_token = AccountToken.objects.filter(
        token=token, token_type='verify_email'
    ).select_related('user').first()

    if not account_token:
        messages.error(request, "Link verifikasi tidak valid.")
    elif account_token.used:
        messages.success(request, "Email kamu sudah pernah diverifikasi sebelumnya. Silakan login.")
    elif account_token.is_expired():
        messages.error(request, "Link verifikasi sudah kedaluwarsa. Minta link baru di bawah ini.")
        return render(request, 'tasks/login.html', {'show_resend_verification': True})
    else:
        account_token.user.is_verified = True
        account_token.user.save()
        account_token.used = True
        account_token.save()
        messages.success(request, "Email berhasil diverifikasi! Sekarang kamu bisa login.")

    return redirect('login_page')


def resend_verification_page(request):
    if request.method == 'POST':
        username_or_email = request.POST.get('identifier', '').strip()

        ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        throttle_key = f"resend_verif_throttle_{ip}"
        if cache.get(throttle_key):
            messages.error(request, "Tunggu sebentar sebelum minta kirim ulang lagi.")
            return redirect('login_page')
        cache.set(throttle_key, True, 60)

        user = User.objects.filter(
            db_models.Q(username=username_or_email) | db_models.Q(email=username_or_email)
        ).first()
        # Pesan SENGAJA generic — tidak membedakan "user tidak ada" vs
        # "sudah terverifikasi" vs "berhasil dikirim", supaya endpoint ini
        # tidak bisa dipakai buat nebak-nebak username/email mana yang
        # terdaftar di sistem (information disclosure).
        if user and not user.is_verified:
            _send_verification_email(request, user)
        messages.success(
            request,
            "Kalau akun dengan username/email itu ada dan belum terverifikasi, "
            "link verifikasi baru sudah dikirim."
        )
        return redirect('login_page')

    return render(request, 'tasks/login.html', {'show_resend_verification': True})


def forgot_password_page(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()

        ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        throttle_key = f"forgot_pwd_throttle_{ip}"
        if cache.get(throttle_key):
            messages.error(request, "Tunggu sebentar sebelum minta reset lagi.")
            return redirect('forgot_password_page')
        cache.set(throttle_key, True, 60)

        user = User.objects.filter(email=email).first()
        # Sama seperti resend verifikasi — pesan generic, tidak bocorin
        # apakah email itu terdaftar atau tidak.
        if user:
            _send_password_reset_email(request, user)
        messages.success(
            request,
            "Kalau email itu terdaftar, link reset password sudah dikirim. Cek inbox/spam kamu."
        )
        return redirect('login_page')

    return render(request, 'tasks/forgot_password.html')


def reset_password_page(request, token):
    account_token = AccountToken.objects.filter(
        token=token, token_type='reset_password'
    ).select_related('user').first()

    if not account_token or not account_token.is_valid():
        messages.error(request, "Link reset password tidak valid atau sudah kedaluwarsa. Minta link baru.")
        return redirect('forgot_password_page')

    if request.method == 'POST':
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if len(password) < 6:
            messages.error(request, "Password minimal 6 karakter.")
        elif password != confirm_password:
            messages.error(request, "Konfirmasi password tidak cocok.")
        else:
            account_token.user.password = make_password(password)
            account_token.user.save()
            account_token.used = True
            account_token.save()
            messages.success(request, "Password berhasil diubah! Silakan login dengan password baru.")
            return redirect('login_page')

    return render(request, 'tasks/reset_password.html', {'token': token})


def my_courses_page(request):
    user_id = request.session.get('user_id')
    if not user_id:
        messages.error(request, "Silakan login dulu untuk melihat kursus kamu.")
        return redirect('login_page')

    # Sebelumnya TIDAK ADA halaman buat lihat "kursus yang sudah saya
    # ambil" dalam satu tempat — user harus scroll-scroll homepage nyariin
    # kartu yang tombolnya "Buka Kursus". Halaman ini gabungin dashboard
    # kursus + sertifikat yang sudah didapat, mirip "My Learning" di
    # Udemy/Coursera.
    enrollments = (
        Enrollment.objects.filter(student_id=user_id, status='paid')
        .select_related('course', 'course__teacher')
        .prefetch_related('course__contents')
        .order_by('-id')
    )

    # Ambil SEMUA content_id yang sudah ditandai selesai oleh user ini
    # lewat SATU query, supaya tidak query berulang per-course (N+1) —
    # pola yang sama dipakai buat fix performa di homepage sebelumnya.
    done_content_ids = set(
        ContentProgress.objects.filter(user_id=user_id).values_list('content_id', flat=True)
    )

    enrolled_courses = []
    for enrollment in enrollments:
        course = enrollment.course
        all_contents = course.contents.all()  # sudah dari cache prefetch
        total = len(all_contents)
        done = sum(1 for c in all_contents if c.id in done_content_ids)
        course.progress_pct = int(done / total * 100) if total > 0 else 0
        course.total_content = total
        course.is_course_complete = total > 0 and course.progress_pct == 100
        # Lihat docstring _issue_certificate_if_complete: ini jaring
        # pengaman supaya sertifikat tetap ke-generate walau user gak
        # pernah balik ke halaman detail course-nya lagi setelah
        # menyelesaikan materi terakhir.
        _, just_issued = _issue_certificate_if_complete(user_id, course, course.progress_pct, total)
        if just_issued:
            messages.success(request, f"🎉 Selamat! Kamu menyelesaikan kursus '{course.name}' dan sertifikatnya sudah siap diunduh!")
        enrolled_courses.append(course)

    certificates = (
        Certificate.objects.filter(user_id=user_id)
        .select_related('course')
        .order_by('-issued_at')
    )

    return render(request, 'tasks/my_courses.html', {
        'enrolled_courses': enrolled_courses,
        'certificates': certificates,
    })


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

        # Kalau email DIGANTI, status "terverifikasi" otomatis batal —
        # email baru itu belum pernah benar-benar dikonfirmasi pemiliknya.
        # Tanpa ini, user bisa ganti ke email siapa saja dan sistem tetap
        # menganggapnya "terverifikasi" padahal email barunya gak pernah
        # diklik link apapun.
        email_changed = email != user.email
        if email_changed:
            user.is_verified = False

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

        if email_changed:
            _send_verification_email(request, user)
            messages.success(
                request,
                "Profil berhasil diperbarui. Email kamu berubah, jadi perlu "
                "diverifikasi ulang — cek inbox/spam ya."
            )
        else:
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