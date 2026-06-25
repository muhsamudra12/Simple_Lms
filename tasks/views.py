from django.shortcuts import render, get_object_or_404, redirect
from .models import Course, Comment, User
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.core.paginator import Paginator
from django.core.cache import cache
from django.db.models import Avg, Max, Min, Count
from django.db.models.functions import Cast
from django.db import models as db_models
from django.shortcuts import render


def index(request):
    query = request.GET.get('q')
    courses = Course.objects.select_related('teacher').all()

    if query:
        courses = courses.filter(name__icontains=query)

    # Pagination — sebelumnya semua kursus di-load sekaligus tanpa batas,
    # jadi kalau jumlah kursus terus bertambah, halaman beranda makin
    # berat. 9 kursus per halaman (pas untuk grid 3 kolom x 3 baris).
    paginator = Paginator(courses, 9)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    completed_courses = request.session.get('completed_courses', [])

    return render(request, 'tasks/index.html', {
        'courses': page_obj,
        'page_obj': page_obj,
        'query': query,
        'completed_courses': completed_courses
    })


def detail(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    comments = course.comments.all()

    if request.method == "POST":

        # ── Selesaikan Kursus ─────────────────────────────────
        if 'selesaikan' in request.POST:
            completed_courses = request.session.get('completed_courses', [])
            if course.id not in completed_courses:
                completed_courses.append(course.id)
                request.session['completed_courses'] = completed_courses
                request.session.modified = True
            messages.success(request, f"Selamat! Anda telah menyelesaikan kursus {course.name}.")
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
                Comment.objects.create(
                    course=course,
                    nama_komentator=nama,
                    isi_komentar=isi
                )
                cache.set(throttle_key, True, 10)  # 1 komentar / 10 detik per IP
                messages.success(request, "Komentar berhasil dikirim!")

            return redirect('course_detail', course_id=course.id)

    return render(request, 'tasks/detail.html', {
        'course': course,
        'comments': comments,
    })


def stats_view(request):
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