from django.contrib import admin
from django.contrib.auth.hashers import make_password, identify_hasher
from django.utils.html import format_html
from .models import User, Course, CourseContent, Comment, CourseMember, Enrollment
# Impor library import_export
from import_export import resources
from import_export.admin import ImportExportModelAdmin

# ── Branding Admin Panel ─────────────────────────────────────
admin.site.site_header = "LMS Academy — Admin Panel"
admin.site.site_title = "LMS Academy Admin"
admin.site.index_title = "Dashboard Administrasi Simple LMS"

# ── User ──────────────────────────────────────────────────
class UserResource(resources.ModelResource):
    """
    Tanpa ini, import CSV lewat tombol "Import" di admin akan menyimpan
    kolom password APA ADANYA (plain text) — bypass total dari hashing
    yang sudah diterapkan di endpoint register/login. before_import_row
    di-hash di sini supaya jalur CSV ikut aman juga.
    """
    class Meta:
        model = User
        # profile_image (ImageField) di-exclude dari CSV import/export —
        # file gambar tidak bisa direpresentasikan sebagai teks CSV biasa.
        # Import/export CSV cuma untuk data teks (username, fullname, dst).
        exclude = ('profile_image',)

    def before_import_row(self, row, **kwargs):
        password = row.get('password')
        if password:
            try:
                identify_hasher(password)
                # Sudah berupa hash yang valid, tidak perlu diapa-apakan.
            except ValueError:
                row['password'] = make_password(password)


@admin.register(User)
class UserAdmin(ImportExportModelAdmin):
    resource_classes = [UserResource]
    list_display = ('fullname', 'username', 'email', 'profile_image_preview')
    search_fields = ('fullname', 'username', 'email')

    def profile_image_preview(self, obj):
        if obj.profile_image:
            return format_html('<img src="{}" style="height:32px;width:32px;border-radius:50%;object-fit:cover;" />', obj.profile_image.url)
        return "—"
    profile_image_preview.short_description = "Foto"


# ── CourseContent (Inline di dalam Course) ─────────────────
class CourseContentInline(admin.TabularInline):
    model = CourseContent
    extra = 1
    fields = ('name', 'video_url', 'description')


# ── Course ────────────────────────────────────────────────
@admin.register(Course)
class CourseAdmin(ImportExportModelAdmin): 
    list_display = ('name', 'teacher', 'category', 'price', 'max_students')
    list_filter = ('category',)
    search_fields = ('name', 'description')
    inlines = [CourseContentInline]


# ── CourseContent ─────────────────────────────────────────
@admin.register(CourseContent)
class CourseContentAdmin(ImportExportModelAdmin):
    list_display = ('name', 'course')
    search_fields = ('name',)


# ── Comment ───────────────────────────────────────────────
@admin.register(Comment)
class CommentAdmin(ImportExportModelAdmin):
    list_display = ('nama_komentator', 'course', 'isi_komentar_singkat', 'dibuat_pada')
    list_filter = ('course', 'dibuat_pada')
    search_fields = ('nama_komentator', 'isi_komentar', 'course__name')
    ordering = ('-dibuat_pada',)
    readonly_fields = ('dibuat_pada',)

    def isi_komentar_singkat(self, obj):
        return obj.isi_komentar[:60] + ('...' if len(obj.isi_komentar) > 60 else '')
    isi_komentar_singkat.short_description = 'Komentar'


# ── CourseMember (Pengajar/Murid di tiap kursus) ───────────
@admin.register(CourseMember)
class CourseMemberAdmin(ImportExportModelAdmin):
    list_display = ('user_id', 'course_id', 'roles')
    list_filter = ('roles', 'course_id')
    search_fields = ('user_id__username', 'user_id__fullname', 'course_id__name')


# ── Enrollment (Pendaftaran Siswa) ──────────────────────────
@admin.register(Enrollment)
class EnrollmentAdmin(ImportExportModelAdmin):
    list_display = ('student', 'course', 'status')
    list_filter = ('status', 'course')
    search_fields = ('student__username', 'student__fullname', 'course__name')