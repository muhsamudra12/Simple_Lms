import os
import django

# Configuration untuk menghubungkan skrip ke setting Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from django.contrib.auth.hashers import make_password
from tasks.models import User, Course, CourseContent, Comment

def run_seed():
    print("⏳ Sedang membersihkan data lama dan membuat data dummy baru...")
    
    # 1. Bersihkan data lama agar fresh
    Comment.objects.all().delete()
    CourseContent.objects.all().delete()
    Course.objects.all().delete()
    User.objects.all().delete()

    # 2. Buat Data Users / Teachers / Students
    # Password di-hash dengan make_password() — JANGAN simpan plain text,
    # karena AUTH (login_user di tasks/api.py) sekarang validasi pakai
    # check_password() yang butuh format hash, bukan teks polos.
    teacher1 = User.objects.create(
        username="ajib_susanto",
        fullname="Ajib Susanto, M.Kom",
        email="ajib@dinus.ac.id",
        password=make_password("password123"),
    )
    
    teacher2 = User.objects.create(
        username="ard_lab",
        fullname="Pak Ardytha",
        email="ardytha@dinus.ac.id",
        password=make_password("password123"),
    )

    print(f"✅ User berhasil dibuat! Login lewat /api/v2/auth/login dengan username '{teacher1.username}' & password 'password123' untuk dapat token JWT.")

    # 3. Buat Data Kategori & Kursus (Courses) - Total 7 Data untuk tes Pagination (> 5)
    courses_data = [
        {
            "name": "Pemrograman Django Ninja untuk Pemula",
            "description": "Belajar dasar-dasar pengembangan backend cepat menggunakan Django Ninja API framework.",
            "price": 150000,
            "category": "Backend Development",
            "image_url": "https://images.unsplash.com/photo-1515879218367-8466d910aaa4",
            "teacher": teacher1
        },
        {
            "name": "Arsitektur Microservices dengan Docker & Python",
            "description": "Panduan mendalam membagi aplikasi monolithic menjadi microservices menggunakan Docker container.",
            "price": 350000,
            "category": "DevOps",
            "image_url": "https://images.unsplash.com/photo-1607799279861-4dd421887fb3",
            "teacher": teacher1
        },
        {
            "name": "Dasar NoSQL Database dengan MongoDB",
            "description": "Mempelajari konsep dokumen terstruktur, instalasi via Docker compose, dan integrasi Compass.",
            "price": 125000,
            "category": "Database",
            "image_url": "https://images.unsplash.com/photo-1544383835-bda2bc66a55d",
            "teacher": teacher2
        },
        {
            "name": "Frontend Integrasi React.js & REST API",
            "description": "Menghubungkan antarmuka modern React dengan endpoints backend Django secara asinkronus menggunakan Fetch API.",
            "price": 200000,
            "category": "Frontend Development",
            "image_url": "https://images.unsplash.com/photo-1633356122544-f134324a6cee",
            "teacher": teacher2
        },
        {
            "name": "Pengenalan Kriptografi & Keamanan Sisi Server",
            "description": "Mengamankan REST API menggunakan Bearer token, pembatasan throttling rates, dan hashing kredensial.",
            "price": 400000,
            "category": "Cyber Security",
            "image_url": "https://images.unsplash.com/photo-1550751827-4bd374c3f58b",
            "teacher": teacher1
        },
        {
            "name": "Automated Unit Testing di Django Rest Framework",
            "description": "Menulis skenario pengujian otomatis untuk model, views, dan pembatasan constraint database.",
            "price": 95000,
            "category": "Backend Development",
            "image_url": "https://images.unsplash.com/photo-1516116211223-5c359a36298a",
            "teacher": teacher1
        },
        {
            "name": "Analisis Citra Digital & AI Dasar",
            "description": "Implementasi segmentasi objek gambar menggunakan logika ambang batas thresholding dan edge detection.",
            "price": 500000,
            "category": "Artificial Intelligence",
            "image_url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe",
            "teacher": teacher2
        },
    ]

    created_courses = []
    for c in courses_data:
        course = Course.objects.create(**c)
        created_courses.append(course)
    
    print("✅ 7 Data Courses Dummy berhasil di-insert!")

    # 4. Buat Data Konten Materi Materi Video (CourseContent)
    CourseContent.objects.create(
        name="01. Pengenalan HTTP Methods & REST API Architecture",
        video_url="https://www.youtube.com/embed/dQw4w9WgXcQ",
        description="Membahas dasar protokol stateless HTTP, verb types (GET, POST, PUT, DELETE).",
        course=created_courses[0]
    )
    CourseContent.objects.create(
        name="02. Instalasi Dependensi & Setup Django Ninja",
        video_url="https://www.youtube.com/embed/dQw4w9WgXcQ",
        description="Langkah awal inisialisasi lingkungan virtual dan berkas kelas NinjaAPI.",
        course=created_courses[0]
    )
    CourseContent.objects.create(
        name="01. Apa itu NoSQL dan Bedanya dengan SQL Relasional",
        video_url="https://www.youtube.com/embed/dQw4w9WgXcQ",
        description="Penjelasan skema dinamis BSON dokumen dibandingkan baris kolom SQL kaku.",
        course=created_courses[2]
    )
    print("✅ Data Course Content berhasil disematkan!")

    # 5. Buat Data Komentar Ulasan (Comments)
    Comment.objects.create(
        course=created_courses[0],
        nama_komentator="Andi S1 Informatika",
        isi_komentar="Materinya sangat padat dan mudah dipahami untuk tugas akhir UAS saya pak!"
    )
    Comment.objects.create(
        course=created_courses[0],
        nama_komentator="Budi Kelompok 4",
        isi_komentar="Sistem Throttling-nya langsung berjalan waktu saya coba spam refresh via postman."
    )
    print("✅ Komentar ulasan berhasil di-generate!")
    print("\n🎉 SEEDING DATA SELESAI Sempurna! Database Anda sudah siap diuji.")

if __name__ == "__main__":
    run_seed()