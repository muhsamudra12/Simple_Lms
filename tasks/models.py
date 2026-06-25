# tasks/models.py
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

    def save(self, *args, **kwargs):
        # Tegakkan kuota max_students — sebelumnya field ini ada di model
        # tapi tidak pernah benar-benar dicek di manapun, jadi siswa bisa
        # terus mendaftar walau kursus sudah penuh.
        if self.pk is None:
            current_count = Enrollment.objects.filter(course=self.course).count()
            if current_count >= self.course.max_students:
                raise ValidationError(
                    f"Kursus '{self.course.name}' sudah penuh "
                    f"(maksimal {self.course.max_students} peserta)."
                )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.username} → {self.course.name} ({self.status})"