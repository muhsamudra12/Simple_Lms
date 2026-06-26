from django.contrib import admin
from django.contrib.auth.hashers import make_password, identify_hasher
from django.utils.html import format_html
from django.db.models import Sum, Count, Q
from .models import User, Course, CourseContent, Comment, CourseMember, Enrollment, ContentProgress, Certificate, AccountToken
# Impor library import_export
from import_export import resources
from import_export.admin import ImportExportModelAdmin

# ── Branding Admin Panel ─────────────────────────────────────
admin.site.site_header = "LMS Academy — Admin Panel"
admin.site.site_title = "LMS Academy Admin"
admin.site.index_title = "Dashboard Administrasi Simple LMS"

# ── Dashboard Ringkasan ───────────────────────────────────────
# Sebelumnya halaman utama Admin cuma nampilin daftar model standar
# Django (User, Course, dst) tanpa ringkasan apa-apa — admin harus buka
# satu-satu buat tau total siswa, revenue, atau course paling populer.
#
# Caranya: "monkey-patch" method `index()` milik `admin.site` (instance
# AdminSite global yang dipakai semua `@admin.register`) supaya nyisipin
# data statistik ke `extra_context` sebelum render halaman index bawaan
# Django — pendekatan standar buat nambah dashboard TANPA harus ganti
# seluruh AdminSite atau bikin halaman terpisah.
_original_admin_index = admin.site.index


def _admin_index_with_stats(request, extra_context=None):
    extra_context = extra_context or {}

    total_courses = Course.objects.count()
    total_students = User.objects.count()
    total_teachers = Course.objects.values('teacher_id').distinct().count()
    paid_enrollments = Enrollment.objects.filter(status='paid')
    total_enrollments = paid_enrollments.count()
    pending_enrollments = Enrollment.objects.filter(status='pending').count()

    # Revenue kasar — SEKADAR ESTIMASI dari harga course x jumlah
    # enrollment status 'paid'. BUKAN angka transaksi sungguhan, karena
    # project ini belum terhubung ke payment gateway apapun — "ambil
    # kursus" langsung set status 'paid' tanpa pembayaran real.
    revenue = paid_enrollments.aggregate(total=Sum('course__price'))['total'] or 0

    popular_courses = (
        Course.objects.annotate(enrolled_count=Count('enrollments', filter=Q(enrollments__status='paid')))
        .order_by('-enrolled_count')[:5]
    )

    extra_context['dashboard_stats'] = {
        'total_courses': total_courses,
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_enrollments': total_enrollments,
        'pending_enrollments': pending_enrollments,
        'revenue': revenue,
        'popular_courses': popular_courses,
    }
    return _original_admin_index(request, extra_context)


admin.site.index = _admin_index_with_stats

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
    list_display = ('fullname', 'username', 'email', 'is_verified', 'profile_image_preview')
    list_filter = ('is_verified',)
    search_fields = ('fullname', 'username', 'email')
    actions = ['verify_manually']

    def profile_image_preview(self, obj):
        if obj.profile_image:
            return format_html('<img src="{}" style="height:32px;width:32px;border-radius:50%;object-fit:cover;" />', obj.profile_image.url)
        return "—"
    profile_image_preview.short_description = "Foto"

    @admin.action(description="Verifikasi email secara manual (kalau SMTP belum di-setup/email gak ke-deliver)")
    def verify_manually(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, f"{updated} user berhasil di-verifikasi manual.")


# ── CourseContent (Inline di dalam Course) ─────────────────
class CourseContentInline(admin.TabularInline):
    model = CourseContent
    extra = 1
    fields = ('order', 'name', 'video_url', 'duration_seconds', 'description')
    ordering = ['order', 'id']


# ── Enrollment (Inline read-only di dalam Course) ───────────
# Sebelumnya admin harus pindah ke menu "Enrollments" terpisah dan
# filter manual buat lihat siapa aja yang sudah ambil kursus tertentu.
# Sengaja DIBUAT READ-ONLY (gak bisa tambah/hapus/edit dari sini) supaya
# pengelolaan beneran tetap lewat menu Enrollments (yang sudah ada
# validasi kuota dkk) — inline ini cuma buat "lihat sekilas", bukan ganti
# fungsi menu aslinya.
class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0
    fields = ('student', 'status')
    readonly_fields = ('student', 'status')
    verbose_name = "Peserta Terdaftar"
    verbose_name_plural = "Peserta Terdaftar (read-only — kelola lewat menu Enrollments)"

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ── Course ────────────────────────────────────────────────
@admin.register(Course)
class CourseAdmin(ImportExportModelAdmin): 
    list_display = ('name', 'teacher', 'category', 'price', 'max_students')
    list_filter = ('category',)
    search_fields = ('name', 'description')
    inlines = [CourseContentInline, EnrollmentInline]


# ── CourseContent ─────────────────────────────────────────
@admin.register(CourseContent)
class CourseContentAdmin(ImportExportModelAdmin):
    list_display = ('name', 'order', 'course', 'duration_seconds')
    list_display_links = ('name',)
    list_editable = ('order',)
    list_filter = ('course',)
    search_fields = ('name',)


# ── Comment ───────────────────────────────────────────────
@admin.register(Comment)
class CommentAdmin(ImportExportModelAdmin):
    list_display = ('nama_komentator', 'course', 'rating', 'isi_komentar_singkat', 'dibuat_pada')
    list_filter = ('rating', 'course', 'dibuat_pada')
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


# ── ContentProgress (Progress Materi per User) ──────────────
# Sebelumnya status "selesai kursus" cuma disimpan di session browser,
# jadi sama sekali tidak bisa dilihat/diedit lewat Admin. Sekarang
# datanya benar-benar di database, jadi bisa di-manage langsung di sini
# (misal kalau ada siswa yang minta ditandai selesai manual oleh admin).
@admin.register(ContentProgress)
class ContentProgressAdmin(ImportExportModelAdmin):
    list_display = ('user', 'content', 'get_course', 'completed_at')
    list_filter = ('content__course', 'completed_at')
    search_fields = ('user__username', 'user__fullname', 'content__name', 'content__course__name')
    autocomplete_fields = ['user', 'content']

    def get_course(self, obj):
        return obj.content.course
    get_course.short_description = 'Kursus'


# ── Certificate (Sertifikat Penyelesaian Kursus) ────────────
# Read-only di sisi field `code` & `issued_at` — kedua field ini
# di-generate otomatis (UUID + auto_now_add) dan tidak boleh diubah
# manual lewat Admin, supaya kode verifikasi tidak bisa diutak-atik.
@admin.register(Certificate)
class CertificateAdmin(ImportExportModelAdmin):
    list_display = ('user', 'course', 'code', 'issued_at')
    list_filter = ('course', 'issued_at')
    search_fields = ('user__username', 'user__fullname', 'course__name', 'code')
    readonly_fields = ('code', 'issued_at')
    autocomplete_fields = ['user', 'course']


# ── AccountToken (link verifikasi email / reset password) ──
# Berguna terutama selama EMAIL_BACKEND belum diset ke SMTP asli
# (masih console backend) — admin bisa lihat token di sini lalu bangun
# link manual (/verify-email/<token>/ atau /reset-password/<token>/)
# buat dikirim manual ke user kalau perlu, tanpa harus ngorek-ngorek log.
@admin.register(AccountToken)
class AccountTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token_type', 'token', 'used', 'created_at')
    list_filter = ('token_type', 'used')
    search_fields = ('user__username', 'user__email', 'token')
    readonly_fields = ('token', 'created_at')
    autocomplete_fields = ['user']

    def save_model(self, request, obj, form, change):
        # Sebelumnya: nge-centang "used" manual di sini CUMA mengubah field
        # `used` doang — TIDAK benar-benar memverifikasi email user (beda
        # dengan kalau user klik link aslinya, yang sekaligus set
        # `user.is_verified = True`). Ini bikin bingung: admin centang
        # "used", tapi user tetap gak bisa login karena dianggap "belum
        # diverifikasi". Sekarang disamakan behaviour-nya: centang "used"
        # pada token verifikasi email = otomatis verifikasi user-nya juga,
        # sama seperti efek mengklik link verifikasi yang sesungguhnya.
        was_used_before = False
        if change and obj.pk:
            was_used_before = AccountToken.objects.filter(pk=obj.pk, used=True).exists()

        super().save_model(request, obj, form, change)

        if obj.token_type == 'verify_email' and obj.used and not was_used_before:
            obj.user.is_verified = True
            obj.user.save()
            self.message_user(request, f"Email milik '{obj.user.username}' otomatis ikut diverifikasi.")