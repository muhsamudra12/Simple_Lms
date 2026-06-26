# tasks/models.py
import uuid
from django.db import models
from django.core.exceptions import ValidationError

#Model untuk User/Admin
class User(models.Model):
    username = models.CharField(max_length=50, unique=True) 
    fullname = models.CharField(max_length=100)
    email = models.EmailField()
    password = models.CharField(max_length=128)
    token = models.CharField(max_length=255, null=True, blank=True) 
    profile_image = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
    is_verified = models.BooleanField(
        default=False,
        verbose_name="Email Terverifikasi",
        help_text="User wajib klik link verifikasi yang dikirim ke email sebelum bisa login di web.",
    )

    def __str__(self): 
        return self.fullname

# Model untuk data Utama Kursus
class Course(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.IntegerField()
    image_url = models.URLField(default="https://placehold.co/600x400/0a0f2c/ffffff?text=LMS")
    category = models.CharField(max_length=50, default="Umum")
    teacher = models.ForeignKey(User, on_delete=models.CASCADE)  # Relasi ke User
    max_students = models.IntegerField(default=100)  # Jumlah maksimum peserta
    def __str__(self): return self.name

# Model untuk Konten Video Materi
class CourseContent(models.Model):
    name = models.CharField(max_length=200)
    video_url = models.URLField(help_text="Masukkan link embed YouTube")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='contents')  # Relasi ke Course
    description = models.TextField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Durasi Video (detik)",
        help_text=(
            "Opsional. Isi total durasi video dalam detik (misal video 5:25 "
            "= 325 detik). Kalau diisi, durasi preview gratis materi pertama "
            "dihitung OTOMATIS sebagai persentase dari angka ini (lihat "
            "PREVIEW_PERCENTAGE di views.py). Kalau dikosongkan, dipakai "
            "durasi preview default (PREVIEW_DEFAULT_SECONDS)."
        ),
    )

    class Meta:
        # Sebelumnya TIDAK ada ordering eksplisit, jadi urutan materi
        # bisa berbeda-beda tergantung database (tidak konsisten) — ini
        # juga jadi masalah baru sejak materi pertama dijadikan "preview
        # gratis": tanpa urutan pasti, materi mana yang jadi gratis bisa
        # berubah-ubah tiap kali halaman dibuka. Diurutkan oleh `id`
        # (urutan dibuat) supaya konsisten.
        ordering = ['id']

    def __str__(self):
        # Sebelumnya model ini TIDAK punya __str__ sama sekali, jadi Django
        # Admin nampilin representasi default Python yang generic ("CourseContent
        # object (2)") — baik di header tiap baris inline materi di halaman
        # Course, maupun di dropdown autocomplete (misal pas pilih materi di
        # Admin ContentProgress). Sekarang nampilin nama materi yang sebenarnya.
        return f"{self.name} ({self.course.name})"

    def save(self, *args, **kwargs):
        if "watch?v=" in self.video_url:
            video_id = self.video_url.split("v=")[1].split("&")[0]
            self.video_url = f"https://www.youtube.com/embed/{video_id}"
        elif "youtu.be/" in self.video_url:
            video_id = self.video_url.split("youtu.be/")[1].split("?")[0]
            self.video_url = f"https://www.youtube.com/embed/{video_id}"
        super().save(*args, **kwargs)


# Model untuk Komentar pada Kursus
class Comment(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='comments'  
    )
    nama_komentator = models.CharField(max_length=100, verbose_name="Nama")
    isi_komentar = models.TextField(verbose_name="Komentar")
    rating = models.PositiveSmallIntegerField(
        default=5,
        choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5')],
        verbose_name="Rating",
        help_text="Rating 1-5 bintang.",
    )
    dibuat_pada = models.DateTimeField(auto_now_add=True, verbose_name="Waktu Komentar")

    class Meta:
        ordering = ['-dibuat_pada'] 
        verbose_name = "Komentar"
        verbose_name_plural = "Daftar Komentar"

    def __str__(self):
        return f"{self.nama_komentator} → {self.course.name} ({self.dibuat_pada.strftime('%d %b %Y %H:%M')})"
    
    # Model untuk Anggota Kursus (CourseMember)
class CourseMember(models.Model):
    course_id = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='members')
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_memberships')
    roles = models.CharField(max_length=10, choices=[('std', 'Student'), ('tch', 'Teacher')], default='std')

    def __str__(self):
        return f"{self.user_id.username} di {self.course_id.name}"


# Model untuk Pendaftaran Siswa (Enrollment)
class Enrollment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('paid', 'Paid')], default='pending')

    class Meta:
        # Constraint agar satu siswa tidak mendaftar di kelas yang sama berkali-kali
        unique_together = ('course', 'student')

    def _check_capacity(self):
        if self.pk is None:
            current_count = Enrollment.objects.filter(course=self.course).count()
            if current_count >= self.course.max_students:
                raise ValidationError(
                    f"Kursus '{self.course.name}' sudah penuh "
                    f"(maksimal {self.course.max_students} peserta)."
                )

    def clean(self):
        # clean() dipanggil otomatis oleh Django Admin (lewat ModelForm.full_clean())
        # SEBELUM proses save() — jadi kalau kuota penuh, errornya tampil rapi
        # sebagai form error di Admin, bukan crash 500 Internal Server Error.
        super().clean()
        self._check_capacity()

    def save(self, *args, **kwargs):
        # Pengecekan ini tetap dipertahankan di save() sebagai jaring pengaman
        # untuk jalur yang TIDAK lewat ModelForm (misal endpoint API yang
        # langsung panggil .save() tanpa full_clean()).
        self._check_capacity()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.username} → {self.course.name} ({self.status})"


# Model untuk progress per-materi (video) — pengganti sistem lama yang
# cuma disimpan di session browser (hilang kalau ganti device/clear
# cookie, dan tidak bisa dilihat/diedit lewat Admin). Sekarang setiap
# video yang ditandai selesai oleh seorang user benar-benar tersimpan
# di database, terhubung ke akun User aslinya.
class ContentProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='content_progress')
    content = models.ForeignKey(CourseContent, on_delete=models.CASCADE, related_name='progress_records')
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Satu user cuma bisa punya satu record selesai per materi (tidak dobel)
        unique_together = ('user', 'content')

    def __str__(self):
        return f"{self.user.username} selesai '{self.content.name}'"


# Model untuk Sertifikat penyelesaian kursus.
#
# Sengaja disimpan permanen di database (bukan di-generate ulang on-the-fly
# tiap kali halaman dibuka) supaya:
# 1. Tanggal "Diterbitkan" konsisten — selalu tanggal PERTAMA KALI kursus
#    diselesaikan, bukan ikut berubah kalau halaman di-refresh.
# 2. Punya kode verifikasi (`code`) yang permanen & bisa dibagikan
#    (misal ke HRD perusahaan) untuk membuktikan sertifikat itu asli,
#    tanpa orang lain perlu login dulu.

class Certificate(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='certificates')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='certificates')
    code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Satu user cuma bisa punya satu sertifikat per kursus (tidak dobel
        # kalau misal toggle materi selesai/belum-selesai berkali-kali).
        unique_together = ('user', 'course')

    def __str__(self):
        return f"Sertifikat {self.user.fullname} — {self.course.name}"


# Model token sekali-pakai buat link yang dikirim ke email user — dipakai
# untuk DUA keperluan (verifikasi email & reset password) lewat satu model
# yang sama (`token_type` yang bedain), daripada bikin 2 model nyaris
# identik terpisah.
class AccountToken(models.Model):
    TOKEN_TYPES = [
        ('verify_email', 'Verifikasi Email'),
        ('reset_password', 'Reset Password'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='account_tokens')
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    token_type = models.CharField(max_length=20, choices=TOKEN_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    def is_expired(self):
        from django.utils import timezone
        # Link verifikasi email berlaku lebih lama (24 jam, kasih waktu
        # cek inbox) dibanding link reset password (1 jam — lebih sensitif
        # kalau ke-intip orang lain di inbox yang sama).
        hours = 1 if self.token_type == 'reset_password' else 24
        return timezone.now() > self.created_at + timezone.timedelta(hours=hours)

    def is_valid(self):
        return not self.used and not self.is_expired()

    def __str__(self):
        return f"{self.get_token_type_display()} — {self.user.username}"