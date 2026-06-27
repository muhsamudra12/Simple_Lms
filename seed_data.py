import os
import django

# Configuration untuk menghubungkan skrip ke setting Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from django.contrib.auth.hashers import make_password
from tasks.models import (
    User, Course, CourseContent, Comment, Enrollment, ContentProgress, Certificate,
)


def run_seed():
    print("⏳ Sedang membersihkan data lama dan membuat data dummy baru...")

    # 1. Bersihkan data lama agar fresh — urutan sengaja dari "anak" ke
    # "induk" biar jelas, walau sebagian besar relasi di model sudah
    # CASCADE (jadi sebenarnya cukup hapus User & Course saja, tapi
    # ditulis lengkap di sini biar predictable kalau ada yang baca ulang).
    Certificate.objects.all().delete()
    ContentProgress.objects.all().delete()
    Enrollment.objects.all().delete()
    Comment.objects.all().delete()
    CourseContent.objects.all().delete()
    Course.objects.all().delete()
    User.objects.all().delete()

    # ─────────────────────────────────────────────────────────────
    # 2. USERS — Teachers & Students
    # Password di-hash dengan make_password() — JANGAN simpan plain text,
    # karena AUTH (login_user di tasks/api.py & login_page di views.py)
    # validasi pakai check_password() yang butuh format hash.
    #
    # is_verified=True SENGAJA diset manual buat hampir semua akun dummy
    # di sini — dibuat langsung lewat script, BUKAN lewat form registrasi
    # web biasa, jadi tidak pernah ada email verifikasi yang "sungguhan"
    # terkirim. Tanpa ini, akun dummy TIDAK BISA login di WEBSITE sama
    # sekali (login web sekarang mewajibkan email terverifikasi dulu).
    #
    # KECUALI satu akun (`siswa_belum_verifikasi`) yang SENGAJA dibuat
    # is_verified=False — buat langsung mendemokan gate "email belum
    # diverifikasi" di halaman login tanpa perlu daftar akun baru manual.
    # ─────────────────────────────────────────────────────────────
    teacher1 = User.objects.create(
        username="ajib_susanto", fullname="Ajib Susanto, M.Kom",
        email="ajib@dinus.ac.id", password=make_password("password123"),
        is_verified=True,
    )
    teacher2 = User.objects.create(
        username="ard_lab", fullname="Pak Ardytha",
        email="ardytha@dinus.ac.id", password=make_password("password123"),
        is_verified=True,
    )

    # Siti  -> bakal menyelesaikan SEMUA materi course0 -> trigger sertifikat otomatis
    # Budi  -> baru menyelesaikan SEBAGIAN materi course0 -> progress di tengah
    # Citra -> sengaja TIDAK enroll ke course apapun -> demo tombol "Ambil Kursus"
    # Dimas -> ikut ngisi kuota course3 (max_students=2) bareng Siti -> demo "Kuota Penuh"
    siti = User.objects.create(
        username="siti_rahma", fullname="Siti Rahma", email="siti.rahma@gmail.com",
        password=make_password("password123"), is_verified=True,
    )
    budi = User.objects.create(
        username="budi_pratama", fullname="Budi Pratama", email="budi.pratama@gmail.com",
        password=make_password("password123"), is_verified=True,
    )
    citra = User.objects.create(
        username="citra_dewi", fullname="Citra Dewi", email="citra.dewi@gmail.com",
        password=make_password("password123"), is_verified=True,
    )
    dimas = User.objects.create(
        username="dimas_anggara", fullname="Dimas Anggara", email="dimas.anggara@gmail.com",
        password=make_password("password123"), is_verified=True,
    )
    eka_unverified = User.objects.create(
        username="siswa_belum_verifikasi", fullname="Eka Wulandari", email="eka.wulandari@gmail.com",
        password=make_password("password123"), is_verified=False,
    )

    print(f"✅ User berhasil dibuat! Login web pakai username '{siti.username}' / password 'password123'.")
    print(f"   Akun '{eka_unverified.username}' SENGAJA belum verifikasi — buat demo gate verifikasi email di halaman login.")

    # ─────────────────────────────────────────────────────────────
    # 3. COURSES — 8 course (7 berbayar + 1 gratis), variasi kategori,
    # harga (termasuk semua rentang filter: gratis/<100rb/100-300rb/>300rb),
    # dan max_students (termasuk yang kuotanya sengaja kecil buat demo
    # "Kuota Penuh").
    # ─────────────────────────────────────────────────────────────
    courses_data = [
        {
            "name": "Pemrograman Django Ninja untuk Pemula",
            "description": "Belajar dasar-dasar pengembangan backend cepat menggunakan Django Ninja API framework.",
            "price": 150000, "category": "Backend Development", "max_students": 30,
            "image_url": "https://images.unsplash.com/photo-1515879218367-8466d910aaa4",
            "teacher": teacher1,
        },
        {
            "name": "Arsitektur Microservices dengan Docker & Python",
            "description": "Panduan mendalam membagi aplikasi monolithic menjadi microservices menggunakan Docker container.",
            "price": 350000, "category": "DevOps", "max_students": 20,
            "image_url": "https://images.unsplash.com/photo-1607799279861-4dd421887fb3",
            "teacher": teacher1,
        },
        {
            "name": "Dasar NoSQL Database dengan MongoDB",
            "description": "Mempelajari konsep dokumen terstruktur, instalasi via Docker compose, dan integrasi Compass.",
            "price": 125000, "category": "Database", "max_students": 25,
            "image_url": "https://images.unsplash.com/photo-1544383835-bda2bc66a55d",
            "teacher": teacher2,
        },
        {
            # max_students=2 SENGAJA kecil — diisi penuh di bawah (Siti +
            # Dimas) buat mendemokan tombol "Kuota Penuh" di homepage.
            "name": "Frontend Integrasi React.js & REST API",
            "description": "Menghubungkan antarmuka modern React dengan endpoints backend Django secara asinkronus menggunakan Fetch API.",
            "price": 200000, "category": "Frontend Development", "max_students": 2,
            "image_url": "https://images.unsplash.com/photo-1633356122544-f134324a6cee",
            "teacher": teacher2,
        },
        {
            "name": "Pengenalan Kriptografi & Keamanan Sisi Server",
            "description": "Mengamankan REST API menggunakan Bearer token, pembatasan throttling rates, dan hashing kredensial.",
            "price": 400000, "category": "Cyber Security", "max_students": 15,
            "image_url": "https://images.unsplash.com/photo-1550751827-4bd374c3f58b",
            "teacher": teacher1,
        },
        {
            "name": "Automated Unit Testing di Django Rest Framework",
            "description": "Menulis skenario pengujian otomatis untuk model, views, dan pembatasan constraint database.",
            "price": 95000, "category": "Backend Development", "max_students": 30,
            "image_url": "https://images.unsplash.com/photo-1516116211223-5c359a36298a",
            "teacher": teacher1,
        },
        {
            "name": "Analisis Citra Digital & AI Dasar",
            "description": "Implementasi segmentasi objek gambar menggunakan logika ambang batas thresholding dan edge detection.",
            "price": 500000, "category": "Artificial Intelligence", "max_students": 10,
            "image_url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe",
            "teacher": teacher2,
        },
        {
            # price=0 SENGAJA — buat mengetes opsi filter harga "Gratis" di homepage.
            "name": "Pengantar HTML & CSS untuk Pemula",
            "description": "Kelas gratis perkenalan struktur HTML, styling CSS dasar, dan flexbox — cocok buat yang baru mulai ngoding.",
            "price": 0, "category": "Web Development", "max_students": 50,
            "image_url": "https://images.unsplash.com/photo-1621839673705-6617adf9e890",
            "teacher": teacher1,
        },
    ]

    c = [Course.objects.create(**data) for data in courses_data]
    # c[0] Django Ninja | c[1] Microservices | c[2] MongoDB | c[3] React (kuota kecil)
    # c[4] Kriptografi  | c[5] Unit Testing  | c[6] AI       | c[7] HTML/CSS (gratis)
    print(f"✅ {len(c)} Data Course berhasil di-insert (termasuk 1 gratis & 1 kuota kecil)!")

    # ─────────────────────────────────────────────────────────────
    # 4. COURSE CONTENT — tiap course dapat beberapa materi. `duration_seconds`
    # diisi (dipakai buat hitung otomatis durasi preview gratis materi
    # pertama). `order` SENGAJA ditulis TIDAK URUT (lihat course0) buat
    # mendemokan bahwa urutan tampil ngikutin `order`, bukan urutan dibuat.
    # ─────────────────────────────────────────────────────────────
    def add_content(course, name, desc, duration, order):
        return CourseContent.objects.create(
            name=name, video_url="https://www.youtube.com/embed/dQw4w9WgXcQ",
            description=desc, course=course, duration_seconds=duration, order=order,
        )

    # Course 0 — Django Ninja (3 materi, order SENGAJA dibalik dari urutan dibuat)
    c0_content2 = add_content(c[0], "02. Instalasi Dependensi & Setup Django Ninja",
        "Langkah awal inisialisasi lingkungan virtual dan berkas kelas NinjaAPI.", 320, order=2)
    c0_content3 = add_content(c[0], "03. Membuat Endpoint CRUD Pertama",
        "Praktik langsung membuat endpoint GET/POST/PUT/DELETE dengan skema Pydantic.", 410, order=3)
    c0_content1 = add_content(c[0], "01. Pengenalan HTTP Methods & REST API Architecture",
        "Membahas dasar protokol stateless HTTP, verb types (GET, POST, PUT, DELETE).", 280, order=1)

    # Course 2 — MongoDB
    add_content(c[2], "01. Apa itu NoSQL dan Bedanya dengan SQL Relasional",
        "Penjelasan skema dinamis BSON dokumen dibandingkan baris kolom SQL kaku.", 300, order=1)
    add_content(c[2], "02. Instalasi MongoDB via Docker Compose",
        "Setup container MongoDB + Mongo Express buat eksplorasi data lewat browser.", 360, order=2)

    # Course 3 — React (kuota kecil)
    add_content(c[3], "01. Setup Project React & Axios",
        "Inisialisasi project React baru dan konfigurasi Axios buat konsumsi REST API.", 250, order=1)
    add_content(c[3], "02. Fetch Data dari Django Ninja ke Komponen React",
        "Menghubungkan useEffect & useState dengan endpoint backend secara asinkronus.", 400, order=2)

    # Course 4, 5, 6 — minimal 1 materi biar gak "Belum ada materi"
    add_content(c[4], "01. Hashing Password dengan bcrypt/Argon2",
        "Kenapa password gak boleh disimpan plain text, dan cara hashing yang aman.", 290, order=1)
    add_content(c[5], "01. Menulis Test Case Pertama dengan TestCase Django",
        "Setup test database, assertEqual, dan menjalankan `python manage.py test`.", 310, order=1)
    add_content(c[6], "01. Konsep Dasar Thresholding pada Citra Digital",
        "Mengubah citra grayscale jadi biner pakai ambang batas sederhana.", 340, order=1)

    # Course 7 — HTML/CSS (gratis, paling lengkap, 4 materi)
    add_content(c[7], "01. Struktur Dasar Dokumen HTML",
        "Tag head, body, heading, paragraph, dan cara browser merender HTML.", 240, order=1)
    add_content(c[7], "02. Styling dengan CSS — Selector & Box Model",
        "Margin, padding, border, dan cara kerja CSS selector & specificity.", 360, order=2)
    add_content(c[7], "03. Layout Modern dengan Flexbox",
        "Membuat layout responsif tanpa float, pakai justify-content & align-items.", 380, order=3)
    add_content(c[7], "04. Mini Project: Landing Page Sederhana",
        "Menggabungkan semua materi sebelumnya jadi satu halaman landing page utuh.", 420, order=4)

    print("✅ Course Content berhasil disematkan (lengkap dengan duration & urutan manual)!")

    # ─────────────────────────────────────────────────────────────
    # 5. COMMENTS — variasi rating (1-5) biar rata-rata & badge bintang
    # di kartu course kelihatan natural, bukan 5.0 semua. Course0 dikasih
    # >10 komentar khusus buat mendemokan PAGINATION komentar.
    # ─────────────────────────────────────────────────────────────
    def add_comment(course, nama, isi, rating):
        return Comment.objects.create(course=course, nama_komentator=nama, isi_komentar=isi, rating=rating)

    add_comment(c[0], "Andi S1 Informatika", "Materinya sangat padat dan mudah dipahami untuk tugas akhir UAS saya pak!", 5)
    add_comment(c[0], "Budi Kelompok 4", "Sistem Throttling-nya langsung berjalan waktu saya coba spam refresh via Postman.", 5)
    add_comment(c[0], "Rina Mahasiswa TI", "Lumayan, tapi penjelasan soal JWT-nya kecepatan menurut saya.", 3)
    for i in range(1, 9):
        add_comment(c[0], f"Mahasiswa Anonim {i}", f"Komentar tambahan ke-{i} buat tes pagination, materinya oke kok.", (i % 5) + 1)

    add_comment(c[2], "Wahyu Backend Dev", "Konsep BSON-nya jelas banget dijelasin, akhirnya ngerti bedanya sama SQL.", 5)
    add_comment(c[2], "Lestari", "Compass-nya agak ribet pas install pertama kali, tapi worth it.", 4)

    add_comment(c[3], "Fajar Frontend", "Axios + React-nya nyambung mulus sama backend Django Ninja, mantap!", 5)

    add_comment(c[6], "Dewi Vision", "Materinya berat tapi penjelasannya pelan-pelan, jadi gak nyerah di tengah.", 4)
    add_comment(c[6], "Yoga ML Enthusiast", "Pengen lebih banyak studi kasus nyata sih, tapi dasarnya udah solid.", 4)

    add_comment(c[7], "Pemula Banget", "Akhirnya nemu kelas gratis yang jelasin flexbox dengan cara yang masuk akal!", 5)
    add_comment(c[7], "Anak SMA Belajar Coding", "Mini project di materi 4 bikin makin pede nyoba sendiri di rumah.", 5)

    print("✅ Komentar ulasan (dengan variasi rating) berhasil di-generate!")

    # ─────────────────────────────────────────────────────────────
    # 6. ENROLLMENT + PROGRESS + SERTIFIKAT
    # Skenario yang sengaja dibentuk:
    #  - Siti  : enroll course0, SELESAIKAN SEMUA materi -> sertifikat otomatis
    #  - Budi  : enroll course0, selesaikan SEBAGIAN materi -> progress ~33%
    #  - Budi  : enroll course7 (gratis) juga, belum mulai sama sekali -> progress 0%
    #  - Siti & Dimas: enroll course3 (max_students=2) -> kuotanya PAS PENUH
    #  - Citra : SENGAJA tidak di-enroll ke apapun -> demo tombol "Ambil Kursus"
    # ─────────────────────────────────────────────────────────────
    Enrollment.objects.create(course=c[0], student=siti, status='paid')
    for content in [c0_content1, c0_content2, c0_content3]:
        ContentProgress.objects.create(user=siti, content=content)
    # Sertifikat di web/API biasanya ke-generate otomatis pas halaman detail
    # course dibuka (lihat _issue_certificate_if_complete di views.py) —
    # di seed script ini gak ada request HTTP yang lewat, jadi dibuatkan
    # manual langsung di sini supaya begitu database di-seed, sertifikatnya
    # SUDAH ADA tanpa perlu Siti buka halaman course-nya dulu.
    Certificate.objects.get_or_create(user=siti, course=c[0])

    Enrollment.objects.create(course=c[0], student=budi, status='paid')
    ContentProgress.objects.create(user=budi, content=c0_content1)  # 1 dari 3 materi -> ~33%

    Enrollment.objects.create(course=c[7], student=budi, status='paid')  # belum mulai sama sekali

    Enrollment.objects.create(course=c[3], student=siti, status='paid')
    Enrollment.objects.create(course=c[3], student=dimas, status='paid')  # genap 2/2 -> KUOTA PENUH

    print("✅ Enrollment, progress belajar, dan 1 sertifikat otomatis berhasil dibuat!")
    print(f"   Course '{c[3].name}' sengaja diisi PENUH (2/2) — coba buka homepage buat lihat tombol 'Kuota Penuh'.")
    print(f"   User '{citra.username}' SENGAJA belum ambil course apapun — buat demo tombol 'Ambil Kursus'.")

    print("\n🎉 SEEDING DATA SELESAI! Database kamu sudah siap diuji dengan skenario lengkap.")


if __name__ == "__main__":
    run_seed()
