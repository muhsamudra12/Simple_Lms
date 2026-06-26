from django.test import TestCase, Client
from .models import User, Course, CourseMember, CourseContent, Enrollment, Comment, Certificate, AccountToken
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.contrib.auth.hashers import make_password, check_password

# === 1. UJI MODEL COURSE ===
class CourseModelTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create(username='teacher1', fullname='Teacher One', email='t1@mail.com', password='admin')
        self.course = Course.objects.create(
            name="Pemrograman Django",
            description="Belajar Django",
            price=150000,
            teacher=self.teacher
        )

    def test_course_creation(self):
        course = Course.objects.get(name="Pemrograman Django")
        self.assertEqual(course.price, 150000)
        self.assertEqual(course.teacher.username, 'teacher1')


# === 2. UJI MODEL COURSE MEMBER ===
class CourseMemberModelTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create(username='teacher1', fullname='Teacher One', email='t1@mail.com', password='admin')
        self.student = User.objects.create(username='student1', fullname='Student One', email='s1@mail.com', password='admin')
        self.course = Course.objects.create(name="Pemrograman Django", description="Belajar Django", price=150000, teacher=self.teacher)

    def test_course_member_creation(self):
        member = CourseMember.objects.create(
            course_id=self.course,
            user_id=self.student, 
            roles='std'
        )
        self.assertEqual(member.user_id.username, 'student1')
        self.assertEqual(member.roles, 'std')


# === 3. UJI MODEL KONTEN KURSUS ===
class CourseContentModelTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create(username='teacher1', fullname='Teacher One', email='t1@mail.com', password='admin')
        self.course = Course.objects.create(name="Pemrograman Django", description="Belajar Django", price=150000, teacher=self.teacher)

    def test_course_content_creation(self):
        content = CourseContent.objects.create(
            name="Pengenalan Django",
            course=self.course,  # <-- UBAH DI SINI (Hilangkan '_id')
            description="Materi dasar tentang Django"
        )
        self.assertEqual(content.course.name, "Pemrograman Django") # <-- UBAH JUGA DI SINI (Hilangkan '_id')
        self.assertEqual(content.name, "Pengenalan Django")


# === 4. UJI QUERY FILTERING BERDASARKAN DOSEN ===
class CourseQueryTest(TestCase):
    def setUp(self):
        self.teacher1 = User.objects.create(username='teacher1', fullname='Teacher One', email='t1@mail.com', password='admin')
        self.teacher2 = User.objects.create(username='teacher2', fullname='Teacher Two', email='t2@mail.com', password='admin')
        Course.objects.create(name="Django", description="Belajar Django", price=100000, teacher=self.teacher1)
        Course.objects.create(name="Flask", description="Belajar Flask", price=100000, teacher=self.teacher2)

    def test_course_retrieval_by_teacher(self):
        courses = Course.objects.filter(teacher=self.teacher1)
        self.assertEqual(courses.count(), 1)
        self.assertEqual(courses.first().name, "Django")


# === 5. UJI VALIDASI INPUT DATA ===
class CourseValidationTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create(username='teacher1', fullname='Teacher One', email='t1@mail.com', password='admin')

    def test_invalid_price(self):
        # PERBAIKAN: test ini sebelumnya bernama "test_invalid_price" tapi
        # isinya malah memastikan harga NEGATIF berhasil tersimpan (bukan
        # ditolak) — kebalikan dari maksud namanya, dan beda pola dengan
        # test_empty_name di bawah yang benar mengetes PENOLAKAN data
        # tidak valid lewat full_clean(). Sekarang Course.price pakai
        # PositiveIntegerField (lihat models.py), jadi harga negatif
        # seharusnya memang DITOLAK, bukan diterima.
        course = Course(
            name="Pemrograman Django",
            description="Belajar Django",
            price=-10000,
            teacher=self.teacher
        )
        with self.assertRaises(ValidationError):
            course.full_clean()

    def test_empty_name(self):
        course = Course(
            name="", 
            description="Belajar Django",
            price=100000,
            teacher=self.teacher
        )
        with self.assertRaises(ValidationError):
            course.full_clean()


# === 6. UJI CONSTRAINT PENDAFTARAN (ENROLLMENT) ===
class EnrollmentTestCase(TestCase):
    def setUp(self):
        self.teacher = User.objects.create(username='teacher1', fullname='Teacher One', email='t1@mail.com', password='admin')
        self.student = User.objects.create(username='student1', fullname='Student One', email='s1@mail.com', password='admin')
        self.course = Course.objects.create(
            name="Pemrograman Python",
            description="Kursus Python",
            price=50000,
            teacher=self.teacher
        )

    def test_enrollment_success(self):
        enrollment = Enrollment.objects.create(
            course=self.course,
            student=self.student,
            status='paid'
        )
        self.assertEqual(enrollment.course.name, "Pemrograman Python")
        self.assertEqual(enrollment.student.username, "student1")

    def test_duplicate_enrollment(self):
        Enrollment.objects.create(
            course=self.course,
            student=self.student,
            status='paid'
        )
        with self.assertRaises(IntegrityError):
            Enrollment.objects.create(
                course=self.course,
                student=self.student,
                status='pending'
            )

    def test_course_full(self):
        self.course.max_students = 1
        self.course.save()

        Enrollment.objects.create(
            course=self.course,
            student=self.student,
            status='paid'
        )

        student2 = User.objects.create(username='student2', fullname='Student Two', email='s2@mail.com', password='admin')
        enrollment2 = Enrollment(
            course=self.course,
            student=student2,
            status='paid'
        )

        with self.assertRaises(ValidationError):
            enrollment2.save()

        # Pastikan enrollment yang ditolak benar-benar tidak tersimpan
        self.assertEqual(Enrollment.objects.filter(course=self.course).count(), 1)


# ═════════════════════════════════════════════════════════════
# 🌐 API-LEVEL TESTS (django-ninja TestClient)
# Test sebelumnya hanya menguji model secara langsung. Test di bawah
# ini menguji lewat endpoint API sungguhan — termasuk validasi AUTH,
# error handling, dan response status code — sesuai yang benar-benar
# diakses oleh frontend/Postman.
# ═════════════════════════════════════════════════════════════
from ninja.testing import TestClient
from tasks.api import api as ninja_api

client = TestClient(ninja_api)


class AuthApiTest(TestCase):
    def test_register_then_login_success(self):
        r = client.post("/auth/register", json={
            "username": "api_test_user", "fullname": "API Test",
            "email": "apitest@mail.com", "password": "rahasia123"
        })
        self.assertEqual(r.status_code, 201)

        r2 = client.post("/auth/login", json={
            "username": "api_test_user", "password": "rahasia123"
        })
        self.assertEqual(r2.status_code, 200)
        token = r2.json()["token"]
        # Token JWT asli punya 3 segmen dipisah titik (header.payload.signature)
        self.assertEqual(token.count("."), 2)

    def test_login_wrong_password_rejected(self):
        client.post("/auth/register", json={
            "username": "api_test_user2", "fullname": "API Test 2",
            "email": "apitest2@mail.com", "password": "rahasia123"
        })
        r = client.post("/auth/login", json={
            "username": "api_test_user2", "password": "passwordsalah"
        })
        self.assertEqual(r.status_code, 401)

    def test_password_stored_hashed_not_plaintext(self):
        client.post("/auth/register", json={
            "username": "api_test_user3", "fullname": "API Test 3",
            "email": "apitest3@mail.com", "password": "rahasia123"
        })
        user = User.objects.get(username="api_test_user3")
        self.assertNotEqual(user.password, "rahasia123")
        self.assertTrue(user.password.startswith("pbkdf2_"))


class CourseApiAuthTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create(
            username="course_api_teacher", fullname="Teacher", email="t@mail.com",
            password="x"
        )

    def test_create_course_requires_auth(self):
        r = client.post("/courses", json={
            "name": "Kursus Tanpa Auth", "description": "desc",
            "price": 10000, "teacher_id": self.teacher.id
        })
        self.assertEqual(r.status_code, 401)

    def test_create_course_with_valid_token_succeeds(self):
        client.post("/auth/register", json={
            "username": "course_api_user", "fullname": "User",
            "email": "u@mail.com", "password": "rahasia123"
        })
        login = client.post("/auth/login", json={
            "username": "course_api_user", "password": "rahasia123"
        })
        token = login.json()["token"]

        r = client.post(
            "/courses",
            json={"name": "Kursus Dengan Auth", "description": "desc", "price": 10000, "teacher_id": self.teacher.id},
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["name"], "Kursus Dengan Auth")


class CalculatorApiTest(TestCase):
    def test_divide_by_zero_returns_400_not_500(self):
        r = client.post("/calc", json={"nilai1": 10, "operator": "/", "nilai2": 0})
        self.assertEqual(r.status_code, 400)

    def test_unknown_operator_returns_400_not_500(self):
        r = client.post("/calc", json={"nilai1": 10, "operator": "%", "nilai2": 2})
        self.assertEqual(r.status_code, 400)

    def test_normal_calculation_succeeds(self):
        r = client.post("/calc", json={"nilai1": 10, "operator": "+", "nilai2": 5})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["hasil"], 15)


class EnrollmentApiTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create(username="enroll_api_teacher", fullname="T", email="t2@mail.com", password="x")
        self.course = Course.objects.create(
            name="Kursus Penuh API", description="desc", price=10000,
            teacher=self.teacher, max_students=1
        )

        client.post("/auth/register", json={
            "username": "enroll_api_auth", "fullname": "Auth User",
            "email": "auth@mail.com", "password": "rahasia123"
        })
        token_resp = client.post("/auth/login", json={"username": "enroll_api_auth", "password": "rahasia123"})
        self.headers = {"Authorization": f"Bearer {token_resp.json()['token']}"}

        client.post("/auth/register", json={
            "username": "enroll_api_auth2", "fullname": "Auth User 2",
            "email": "auth2@mail.com", "password": "rahasia123"
        })
        token_resp2 = client.post("/auth/login", json={"username": "enroll_api_auth2", "password": "rahasia123"})
        self.headers2 = {"Authorization": f"Bearer {token_resp2.json()['token']}"}

    def test_enrollment_uses_authenticated_user_not_manual_input(self):
        """
        Sebelumnya endpoint ini menerima student_id manual di body — artinya
        siapapun yang punya token bisa mendaftarkan ORANG LAIN. Sekarang
        siswa yang terdaftar harus otomatis sama dengan pemilik token,
        terlepas dari apapun yang dikirim di body.
        """
        r = client.post("/enrollments", json={"course_id": self.course.id, "status": "paid"}, headers=self.headers)
        self.assertEqual(r.status_code, 200)
        auth_user = User.objects.get(username="enroll_api_auth")
        self.assertEqual(r.json()["student_id"], auth_user.id)

    def test_enrollment_rejected_when_course_full(self):
        r1 = client.post("/enrollments", json={"course_id": self.course.id, "status": "paid"}, headers=self.headers)
        self.assertEqual(r1.status_code, 200)

        # User KEDUA (token berbeda) mencoba daftar ke kursus yang sama,
        # yang kuotanya cuma 1 dan sudah terisi oleh user pertama.
        r2 = client.post("/enrollments", json={"course_id": self.course.id, "status": "paid"}, headers=self.headers2)
        self.assertEqual(r2.status_code, 400)

    def test_cannot_delete_other_users_enrollment(self):
        r1 = client.post("/enrollments", json={"course_id": self.course.id, "status": "paid"}, headers=self.headers)
        enrollment_id = r1.json()["id"]

        # User KEDUA coba hapus enrollment milik user PERTAMA -> harus ditolak
        r2 = client.delete(f"/enrollments/{enrollment_id}", headers=self.headers2)
        self.assertEqual(r2.status_code, 403)


# ═════════════════════════════════════════════════════════════
# 🔓 ENROLLMENT GATING DI WEBSITE (bukan API)
# Sebelumnya siapapun yang login bisa langsung akses materi tanpa
# benar-benar "mengambil" course-nya dulu — gap ini sudah ditutup,
# test di bawah memastikan gap itu TIDAK kembali muncul di masa depan.
# ═════════════════════════════════════════════════════════════
class WebEnrollmentGatingTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create(
            username='web_enr_teacher', fullname='Teacher Web', email='webteacher@mail.com',
            password=make_password('admin'),
        )
        self.student = User.objects.create(
            username='web_enr_student', fullname='Student Web', email='webstudent@mail.com',
            password=make_password('admin'), is_verified=True,
        )
        self.course = Course.objects.create(
            name="Kursus Gating Test", description="d", price=50000,
            teacher=self.teacher, max_students=1,
        )
        self.content1 = CourseContent.objects.create(
            name="Materi 1", video_url="https://www.youtube.com/embed/aaa", course=self.course,
        )
        self.content2 = CourseContent.objects.create(
            name="Materi 2", video_url="https://www.youtube.com/embed/bbb", course=self.course,
        )
        self.client = Client()
        session = self.client.session
        session['user_id'] = self.student.id
        session.save()
        self.client.cookies['sessionid'] = session.session_key

    def test_guest_sees_preview_not_redirected_to_login(self):
        """Guest (belum login) harus BISA buka halaman detail (preview), bukan langsung di-redirect ke login."""
        guest = Client()
        resp = guest.get(f'/course/{self.course.id}/')
        self.assertEqual(resp.status_code, 200)

    def test_only_first_content_playable_before_enrollment(self):
        """Sebelum enroll, cuma materi PERTAMA yang videonya bisa diputar (preview gratis)."""
        resp = self.client.get(f'/course/{self.course.id}/')
        body = resp.content.decode()
        self.assertIn('youtube.com/embed/aaa', body)       # materi pertama: terbuka
        self.assertNotIn('youtube.com/embed/bbb', body)    # materi kedua: terkunci

    def test_toggle_content_blocked_before_enrollment(self):
        """Tandai-selesai materi harus ditolak kalau belum enroll, walau lewat POST langsung (skip UI)."""
        from .models import ContentProgress
        self.client.post(f'/course/{self.course.id}/', {'toggle_content': '1', 'content_id': self.content1.id})
        self.assertFalse(ContentProgress.objects.filter(content=self.content1).exists())

    def test_ambil_kursus_creates_enrollment_and_unlocks_content(self):
        """Klik 'Ambil Kursus' harus bikin Enrollment status paid, dan langsung membuka semua materi."""
        self.client.post(f'/course/{self.course.id}/', {'ambil_kursus': '1'})
        enrollment = Enrollment.objects.get(course=self.course, student=self.student)
        self.assertEqual(enrollment.status, 'paid')

        resp = self.client.get(f'/course/{self.course.id}/')
        self.assertIn('youtube.com/embed/bbb', resp.content.decode())  # materi kedua sekarang terbuka

    def test_ambil_kursus_rejected_when_full(self):
        """Kursus dengan max_students=1 yang sudah terisi harus menolak enrollment kedua."""
        other_student = User.objects.create(
            username='web_enr_other', fullname='Other', email='other@mail.com', password=make_password('admin'),
        )
        Enrollment.objects.create(course=self.course, student=other_student, status='paid')

        self.client.post(f'/course/{self.course.id}/', {'ambil_kursus': '1'})
        self.assertFalse(Enrollment.objects.filter(course=self.course, student=self.student).exists())

    def test_cannot_enroll_twice(self):
        self.client.post(f'/course/{self.course.id}/', {'ambil_kursus': '1'})
        self.client.post(f'/course/{self.course.id}/', {'ambil_kursus': '1'})
        self.assertEqual(Enrollment.objects.filter(course=self.course, student=self.student).count(), 1)


# ═════════════════════════════════════════════════════════════
# 🏆 SERTIFIKAT
# ═════════════════════════════════════════════════════════════
class CertificateTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create(
            username='cert_teacher', fullname='Teacher Cert', email='certteacher@mail.com', password=make_password('admin'),
        )
        self.student = User.objects.create(
            username='cert_student', fullname='Student Cert', email='certstudent@mail.com',
            password=make_password('admin'), is_verified=True,
        )
        self.course = Course.objects.create(
            name="Kursus Sertifikat Test", description="d", price=50000, teacher=self.teacher, max_students=10,
        )
        self.content = CourseContent.objects.create(
            name="Satu-satunya Materi", video_url="https://www.youtube.com/embed/ccc", course=self.course,
        )
        Enrollment.objects.create(course=self.course, student=self.student, status='paid')
        self.client = Client()
        session = self.client.session
        session['user_id'] = self.student.id
        session.save()
        self.client.cookies['sessionid'] = session.session_key

    def test_certificate_issued_on_100_percent_completion(self):
        self.assertFalse(Certificate.objects.filter(user=self.student, course=self.course).exists())
        self.client.post(f'/course/{self.course.id}/', {'toggle_content': '1', 'content_id': self.content.id}, follow=True)
        self.assertTrue(Certificate.objects.filter(user=self.student, course=self.course).exists())

    def test_certificate_not_duplicated_on_toggle_back_and_forth(self):
        self.client.post(f'/course/{self.course.id}/', {'toggle_content': '1', 'content_id': self.content.id}, follow=True)
        self.client.post(f'/course/{self.course.id}/', {'toggle_content': '1', 'content_id': self.content.id}, follow=True)
        self.client.post(f'/course/{self.course.id}/', {'toggle_content': '1', 'content_id': self.content.id}, follow=True)
        self.assertEqual(Certificate.objects.filter(user=self.student, course=self.course).count(), 1)

    def test_certificate_verification_page_public_no_login_required(self):
        self.client.post(f'/course/{self.course.id}/', {'toggle_content': '1', 'content_id': self.content.id}, follow=True)
        certificate = Certificate.objects.get(user=self.student, course=self.course)

        public_client = Client()  # tanpa session sama sekali
        resp = public_client.get(f'/certificate/{certificate.code}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.student.fullname, resp.content.decode())

    def test_certificate_pdf_downloadable(self):
        self.client.post(f'/course/{self.course.id}/', {'toggle_content': '1', 'content_id': self.content.id}, follow=True)
        certificate = Certificate.objects.get(user=self.student, course=self.course)

        resp = self.client.get(f'/certificate/{certificate.code}/download/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')

    def test_certificate_still_issued_via_my_courses_page(self):
        """
        Regression test: sebelumnya sertifikat HANYA ke-generate lewat
        halaman detail course. Kalau user menyelesaikan materi terakhir
        lalu langsung ke halaman 'Kursus Saya' (tanpa follow redirect
        balik ke detail), sertifikat tidak pernah benar-benar dibuat
        walau halaman itu menampilkan course sebagai 100% selesai.
        """
        self.client.post(f'/course/{self.course.id}/', {'toggle_content': '1', 'content_id': self.content.id})  # TANPA follow
        self.assertFalse(Certificate.objects.filter(user=self.student, course=self.course).exists())

        self.client.get('/kursus-saya/')
        self.assertTrue(Certificate.objects.filter(user=self.student, course=self.course).exists())

    def test_certificate_still_issued_via_homepage(self):
        """Regression test yang sama, tapi lewat homepage (bukan 'Kursus Saya')."""
        self.client.post(f'/course/{self.course.id}/', {'toggle_content': '1', 'content_id': self.content.id})  # TANPA follow
        self.assertFalse(Certificate.objects.filter(user=self.student, course=self.course).exists())

        self.client.get('/')
        self.assertTrue(Certificate.objects.filter(user=self.student, course=self.course).exists())


# ═════════════════════════════════════════════════════════════
# ✉️ VERIFIKASI EMAIL & LUPA PASSWORD
# ═════════════════════════════════════════════════════════════
class EmailVerificationTest(TestCase):
    def test_new_user_is_unverified_by_default(self):
        user = User.objects.create(username='unverif_user', fullname='X', email='x@mail.com', password=make_password('admin'))
        self.assertFalse(user.is_verified)

    def test_register_via_web_sends_verification_token(self):
        client = Client()
        client.post('/register/', {
            'username': 'webreg_user', 'fullname': 'Web Reg', 'email': 'webreg@mail.com', 'password': 'rahasia123',
        })
        user = User.objects.get(username='webreg_user')
        self.assertFalse(user.is_verified)
        self.assertTrue(AccountToken.objects.filter(user=user, token_type='verify_email').exists())

    def test_login_blocked_until_verified(self):
        client = Client()
        client.post('/register/', {
            'username': 'blocked_user', 'fullname': 'Blocked', 'email': 'blocked@mail.com', 'password': 'rahasia123',
        })
        resp = client.post('/login/', {'username': 'blocked_user', 'password': 'rahasia123'})
        self.assertIsNone(client.session.get('user_id'))
        self.assertIn('belum diverifikasi', resp.content.decode())

    def test_login_succeeds_after_verification(self):
        client = Client()
        client.post('/register/', {
            'username': 'verified_user', 'fullname': 'Verified', 'email': 'verified@mail.com', 'password': 'rahasia123',
        })
        user = User.objects.get(username='verified_user')
        token = AccountToken.objects.get(user=user, token_type='verify_email')

        client.get(f'/verify-email/{token.token}/')
        user.refresh_from_db()
        self.assertTrue(user.is_verified)

        client2 = Client()
        client2.post('/login/', {'username': 'verified_user', 'password': 'rahasia123'})
        self.assertIsNotNone(client2.session.get('user_id'))

    def test_verification_token_cannot_be_reused(self):
        user = User.objects.create(username='replay_user', fullname='Replay', email='replay@mail.com', password=make_password('admin'))
        token = AccountToken.objects.create(user=user, token_type='verify_email')

        client = Client()
        client.get(f'/verify-email/{token.token}/')
        client.get(f'/verify-email/{token.token}/')  # dipakai lagi

        token.refresh_from_db()
        self.assertTrue(token.used)
        # Tidak crash dan user tetap berstatus verified (bukan ke-toggle balik)
        user.refresh_from_db()
        self.assertTrue(user.is_verified)

    def test_existing_users_grandfathered_as_verified(self):
        """User yang dibuat manual (seperti lewat seed_data/admin) HARUS tetap bisa login web tanpa verifikasi tambahan."""
        user = User.objects.create(
            username='grandfather_user', fullname='Old User', email='old@mail.com',
            password=make_password('admin'), is_verified=True,
        )
        client = Client()
        client.post('/login/', {'username': 'grandfather_user', 'password': 'admin'})
        self.assertIsNotNone(client.session.get('user_id'))


class PasswordResetTest(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            username='resetpwd_user', fullname='Reset Pwd', email='resetpwd@mail.com',
            password=make_password('passwordlama'), is_verified=True,
        )

    def test_forgot_password_creates_token(self):
        client = Client()
        client.post('/forgot-password/', {'email': 'resetpwd@mail.com'})
        self.assertTrue(AccountToken.objects.filter(user=self.user, token_type='reset_password').exists())

    def test_reset_password_changes_password_and_allows_login(self):
        token = AccountToken.objects.create(user=self.user, token_type='reset_password')
        client = Client()
        client.post(f'/reset-password/{token.token}/', {
            'password': 'passwordbaru456', 'confirm_password': 'passwordbaru456',
        })
        self.user.refresh_from_db()
        self.assertTrue(check_password('passwordbaru456', self.user.password))
        self.assertFalse(check_password('passwordlama', self.user.password))

    def test_reset_password_mismatch_rejected(self):
        token = AccountToken.objects.create(user=self.user, token_type='reset_password')
        client = Client()
        client.post(f'/reset-password/{token.token}/', {
            'password': 'abc123', 'confirm_password': 'beda456',
        })
        token.refresh_from_db()
        self.assertFalse(token.used)
        self.user.refresh_from_db()
        self.assertTrue(check_password('passwordlama', self.user.password))  # password lama tidak berubah

    def test_used_reset_token_cannot_be_reused(self):
        token = AccountToken.objects.create(user=self.user, token_type='reset_password')
        client = Client()
        client.post(f'/reset-password/{token.token}/', {'password': 'abc123', 'confirm_password': 'abc123'})

        # Coba pakai token yang sama buat reset KEDUA kali ke password lain
        resp = client.post(f'/reset-password/{token.token}/', {'password': 'xyz789', 'confirm_password': 'xyz789'})
        self.user.refresh_from_db()
        self.assertTrue(check_password('abc123', self.user.password))  # tetap password dari reset PERTAMA


# ═════════════════════════════════════════════════════════════
# ⭐ RATING KOMENTAR
# ═════════════════════════════════════════════════════════════
class CommentRatingTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create(username='rating_teacher', fullname='T', email='rt@mail.com', password=make_password('admin'))
        self.course = Course.objects.create(name="Kursus Rating Test", description="d", price=10000, teacher=self.teacher, max_students=10)

    def test_comment_rating_defaults_to_5_if_not_specified(self):
        comment = Comment.objects.create(course=self.course, nama_komentator='A', isi_komentar='ok')
        self.assertEqual(comment.rating, 5)

    def test_web_comment_form_saves_chosen_rating(self):
        client = Client()
        client.post(f'/course/{self.course.id}/', {
            'kirim_komentar': '1', 'nama_komentator': 'Budi', 'isi_komentar': 'Mantap', 'rating': '3',
        })
        comment = Comment.objects.get(nama_komentator='Budi')
        self.assertEqual(comment.rating, 3)

    def test_rating_out_of_range_clamped(self):
        client = Client()
        client.post(f'/course/{self.course.id}/', {
            'kirim_komentar': '1', 'nama_komentator': 'Citra', 'isi_komentar': 'Test', 'rating': '99',
        })
        comment = Comment.objects.get(nama_komentator='Citra')
        self.assertEqual(comment.rating, 5)  # diclamp ke maksimal 5