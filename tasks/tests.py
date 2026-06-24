from django.test import TestCase
from .models import User, Course, CourseMember, CourseContent, Enrollment
from django.core.exceptions import ValidationError
from django.db import IntegrityError

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
        course = Course(
            name="Pemrograman Django",
            description="Belajar Django",
            price=-10000,
            teacher=self.teacher
        )
        course.save()
        retrieved_course = Course.objects.get(pk=course.pk)
        self.assertEqual(retrieved_course.price, -10000)

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
        self.student = User.objects.create(username="enroll_api_student", fullname="S", email="s2@mail.com", password="x")
        self.course = Course.objects.create(
            name="Kursus Penuh API", description="desc", price=10000,
            teacher=self.teacher, max_students=1
        )
        login = client.post("/auth/register", json={
            "username": "enroll_api_auth", "fullname": "Auth User",
            "email": "auth@mail.com", "password": "rahasia123"
        })
        token_resp = client.post("/auth/login", json={"username": "enroll_api_auth", "password": "rahasia123"})
        self.headers = {"Authorization": f"Bearer {token_resp.json()['token']}"}

    def test_enrollment_rejected_when_course_full(self):
        r1 = client.post("/enrollments", json={"course_id": self.course.id, "student_id": self.student.id, "status": "paid"}, headers=self.headers)
        self.assertEqual(r1.status_code, 200)

        student2 = User.objects.create(username="enroll_api_student2", fullname="S2", email="s3@mail.com", password="x")
        r2 = client.post("/enrollments", json={"course_id": self.course.id, "student_id": student2.id, "status": "paid"}, headers=self.headers)
        self.assertEqual(r2.status_code, 400)