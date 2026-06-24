import time
from typing import List, Optional
from functools import wraps
from ninja import NinjaAPI, Schema
from ninja.pagination import paginate, PageNumberPagination
from ninja.errors import HttpError
from django.contrib.auth.hashers import make_password, check_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.core.cache import cache
from tasks.models import User, Course, CourseContent, Comment, Enrollment, CourseMember

# ─────────────────────────────────────────────
# 🔐 JWT AUTH (django-ninja-simple-jwt)
# Memakai key pair RSA (jwt-signing.pem/.pub) yang sudah disiapkan
# di root project. Token asli (bukan UUID custom) sekarang diterbitkan
# saat login lewat get_access_token_for_user(), dan divalidasi otomatis
# oleh HttpJwtAuth — inilah yang bikin tombol "Authorize" di Swagger
# berfungsi dengan token JWT sungguhan.
from ninja_simple_jwt.auth.ninja_auth import HttpJwtAuth
from ninja_simple_jwt.jwt.token_operations import get_access_token_for_user

GlobalAuth = HttpJwtAuth

# Inisialisasi API v2
api = NinjaAPI(version="2", title="Simple LMS API v2", description="REST API Komplit untuk Simple LMS - Kebutuhan Proyek UAS")

# ─────────────────────────────────────────────
# ⏱️ CUSTOM THROTTLING DECORATOR
# Dipindah ke atas (sebelum endpoint apapun memakainya) supaya bisa
# dipasang di endpoint Authentication yang rawan brute-force.
# ─────────────────────────────────────────────
def simple_throttle(rate_limit=10, period=60):
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
            key = f"throttle_{ip}_{func.__name__}"
            requests = cache.get(key, [])
            now = time.time()
            requests = [req for req in requests if now - req < period]
            if len(requests) >= rate_limit:
                raise HttpError(429, "Too many requests.")
            requests.append(now)
            cache.set(key, requests, period)
            return func(request, *args, **kwargs)
        return wrapper
    return decorator

# ─────────────────────────────────────────────
# 🛡️ AUTH SCHEMAS & ENDPOINTS
# ─────────────────────────────────────────────
class RegisterInput(Schema):
    username: str
    fullname: str
    email: str
    password: str

class LoginInput(Schema):
    username: str
    password: str

class AuthOutput(Schema):
    message: str
    token: str = None

@api.post("/auth/register", tags=["Authentication"], response={201: AuthOutput, 400: AuthOutput})
@simple_throttle(rate_limit=5, period=60)
def register_user(request, data: RegisterInput):
    if User.objects.filter(username=data.username).exists():
        return 400, {"message": "Username sudah digunakan!"}
    User.objects.create(
        username=data.username,
        fullname=data.fullname,
        email=data.email,
        password=make_password(data.password),
    )
    return 201, {"message": "Registrasi berhasil! Silakan login."}

@api.post("/auth/login", tags=["Authentication"], response={200: AuthOutput, 401: AuthOutput})
@simple_throttle(rate_limit=5, period=60)
def login_user(request, data: LoginInput):
    user = User.objects.filter(username=data.username).first()
    if user is None or not check_password(data.password, user.password):
        return 401, {"message": "Username atau password salah!"}
    access_token, _ = get_access_token_for_user(user)
    return 200, {"message": "Login sukses!", "token": access_token}


# ─────────────────────────────────────────────
# 🔑 SCHEMAS DATA IN/OUT
# ─────────────────────────────────────────────
class UserOut(Schema):
    id: int
    username: str
    fullname: str
    email: str

class UserIn(Schema):
    username: str
    fullname: str
    email: str
    password: str

class UserUpdate(Schema):
    username: Optional[str] = None
    fullname: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None

# PERBAIKAN UTAMA: Tambahkan fullname ke dalam TeacherSchema
class TeacherSchema(Schema):
    id: int
    username: str
    fullname: str  # <--- Wajib ada agar javascript tidak crash
    email: str

class CourseOut(Schema):
    id: int
    name: str
    description: str
    price: int
    image_url: str
    category: str
    teacher: TeacherSchema

class CourseIn(Schema):
    name: str
    description: str
    price: int
    image_url: str = "https://via.placeholder.com/600x400?text=No+Image"
    category: str = "Umum"
    teacher_id: int

class CourseUpdate(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    teacher_id: Optional[int] = None

class CourseContentOut(Schema):
    id: int
    name: str
    video_url: str
    description: Optional[str] = None
    course_id: int

class CourseContentIn(Schema):
    name: str
    video_url: str
    description: Optional[str] = None
    course_id: int

class CommentOut(Schema):
    id: int
    course_id: int
    nama_komentator: str
    isi_komentar: str

class CommentIn(Schema):
    course_id: int
    nama_komentator: str
    isi_komentar: str

class RegisterIn(Schema):
    username: str
    password: str
    email: str
    first_name: str
    last_name: str

class RegisterOut(Schema):
    id: int
    username: str
    email: str
    first_name: str
    last_name: str

class CalcIn(Schema):
    nilai1: int
    operator: str
    nilai2: int

class CalcOut(Schema):
    nilai1: int
    nilai2: int
    operator: str
    hasil: float


# ─────────────────────────────────────────────
# ⚙️ HELLO & CALCULATOR ENDPOINTS
# ─────────────────────────────────────────────
@api.get("/hello", tags=["Hello"])
def hello_get(request, name: str = "World"): return {"message": f"Hello, {name}!"}

@api.post("/hello", tags=["Hello"])
def hello_post(request, name: str = "World"): return {"message": f"Hello, {name}! (POST)"}

@api.get("/calc/{nilai1}/{opr}/{nilai2}", tags=["Calc"], response=CalcOut)
def calculator_get(request, nilai1: int, opr: str, nilai2: int):
    try:
        return CalcOut(nilai1=nilai1, nilai2=nilai2, operator=opr, hasil=_hitung(nilai1, opr, nilai2))
    except ValueError as e:
        raise HttpError(400, str(e))

@api.post("/calc", tags=["Calc"], response=CalcOut)
def calculator_post(request, payload: CalcIn):
    try:
        return CalcOut(nilai1=payload.nilai1, nilai2=payload.nilai2, operator=payload.operator, hasil=_hitung(payload.nilai1, payload.operator, payload.nilai2))
    except ValueError as e:
        raise HttpError(400, str(e))

def _hitung(nilai1, operator, nilai2):
    if operator == "+": return nilai1 + nilai2
    elif operator == "-": return nilai1 - nilai2
    elif operator == "*": return nilai1 * nilai2
    elif operator == "/":
        if nilai2 == 0: raise ValueError("Tidak bisa dibagi 0")
        return nilai1 / nilai2
    else: raise ValueError("Operator tidak dikenal")


# ─────────────────────────────────────────────
# 🔥 CORE COURSE ENDPOINTS (PAGINASI AMAN)
# ─────────────────────────────────────────────
@api.get("/courses", tags=["Courses"], summary="List Courses", response=List[CourseOut])
@paginate(PageNumberPagination, per_page=5)
def list_courses(request, search: Optional[str] = None, price: Optional[str] = None, sort_by: Optional[str] = "id"):
    """Daftar kursus tanpa custom throttle agar frontend lokal tidak terblokir limit."""
    queryset = Course.objects.select_related('teacher').all()
    if search:
        queryset = queryset.filter(name__icontains=search)
    if price:
        # price diterima sebagai str (bukan int) supaya query string kosong
        # seperti ?price= tidak langsung crash 422 sebelum sempat dicek —
        # baru di-parsing manual di sini, dan diabaikan kalau bukan angka.
        try:
            queryset = queryset.filter(price=int(price))
        except ValueError:
            pass

    if sort_by in ["name", "price", "-price", "id"]:
        queryset = queryset.order_by(sort_by)
    else:
        queryset = queryset.order_by("id")
    return queryset

@api.get("/courses/{course_id}", tags=["Courses"], response=CourseOut)
def get_course(request, course_id: int): return get_object_or_404(Course, id=course_id)

@api.post("/courses", tags=["Courses"], response=CourseOut, auth=GlobalAuth())
def create_course(request, payload: CourseIn):
    teacher = get_object_or_404(User, id=payload.teacher_id)
    return Course.objects.create(name=payload.name, description=payload.description, price=payload.price, image_url=payload.image_url, category=payload.category, teacher=teacher)

@api.put("/courses/{course_id}", tags=["Courses"], response=CourseOut, auth=GlobalAuth())
def update_course(request, course_id: int, payload: CourseUpdate):
    course = get_object_or_404(Course, id=course_id)
    for attr, value in payload.dict(exclude_none=True).items():
        if attr == "teacher_id": course.teacher = get_object_or_404(User, id=value)
        else: setattr(course, attr, value)
    course.save()
    return course

@api.delete("/courses/{course_id}", tags=["Courses"], auth=GlobalAuth())
def delete_course(request, course_id: int):
    get_object_or_404(Course, id=course_id).delete()
    return {"success": True, "message": f"Course {course_id} berhasil dihapus"}


# ─────────────────────────────────────────────
# 👤 USER, CONTENT, & COMMENT ENDPOINTS
# ─────────────────────────────────────────────
@api.get("/users", tags=["Users"], response=List[UserOut])
def list_users(request): return list(User.objects.all())

@api.get("/users/{user_id}", tags=["Users"], response=UserOut)
def get_user(request, user_id: int): return get_object_or_404(User, id=user_id)

@api.delete("/users/{user_id}", tags=["Users"], auth=GlobalAuth())
def delete_user(request, user_id: int):
    get_object_or_404(User, id=user_id).delete()
    return {"success": True}

@api.get("/contents", tags=["Contents"], response=List[CourseContentOut])
def list_contents(request): return list(CourseContent.objects.all())

@api.post("/contents", tags=["Contents"], response=CourseContentOut, auth=GlobalAuth())
def create_content(request, payload: CourseContentIn):
    course = get_object_or_404(Course, id=payload.course_id)
    return CourseContent.objects.create(name=payload.name, video_url=payload.video_url, description=payload.description, course=course)

@api.delete("/contents/{content_id}", tags=["Contents"], auth=GlobalAuth())
def delete_content(request, content_id: int):
    get_object_or_404(CourseContent, id=content_id).delete()
    return {"success": True, "message": f"Materi {content_id} berhasil dihapus"}

@api.get("/comments", tags=["Comments"], response=List[CommentOut])
def list_comments(request): return list(Comment.objects.all())

@api.post("/comments", tags=["Comments"], response=CommentOut)
@simple_throttle(rate_limit=10, period=60)
def create_comment(request, payload: CommentIn):
    course = get_object_or_404(Course, id=payload.course_id)
    return Comment.objects.create(course=course, nama_komentator=payload.nama_komentator, isi_komentar=payload.isi_komentar)

@api.delete("/comments/{comment_id}", tags=["Comments"], auth=GlobalAuth())
def delete_comment(request, comment_id: int):
    """Moderasi — hapus komentar (misal spam atau tidak pantas). Butuh auth."""
    get_object_or_404(Comment, id=comment_id).delete()
    return {"success": True, "message": f"Komentar {comment_id} berhasil dihapus"}


# ─────────────────────────────────────────────
# 🎓 ENROLLMENT ENDPOINTS
# Sebelumnya model Enrollment sudah ada (lengkap dengan constraint unique
# & kuota max_students), tapi belum ada endpoint API sama sekali untuk
# benar-benar memakainya.
# ─────────────────────────────────────────────
class EnrollmentOut(Schema):
    id: int
    course_id: int
    student_id: int
    status: str

class EnrollmentIn(Schema):
    course_id: int
    student_id: int
    status: Optional[str] = "pending"

@api.get("/enrollments", tags=["Enrollments"], response=List[EnrollmentOut])
def list_enrollments(request, course_id: Optional[int] = None):
    queryset = Enrollment.objects.all()
    if course_id is not None:
        queryset = queryset.filter(course_id=course_id)
    return list(queryset)

@api.post("/enrollments", tags=["Enrollments"], response={200: EnrollmentOut, 400: AuthOutput}, auth=GlobalAuth())
def create_enrollment(request, payload: EnrollmentIn):
    course = get_object_or_404(Course, id=payload.course_id)
    student = get_object_or_404(User, id=payload.student_id)
    try:
        enrollment = Enrollment(course=course, student=student, status=payload.status)
        enrollment.save()
        return 200, enrollment
    except ValidationError as e:
        return 400, {"message": str(e.message) if hasattr(e, "message") else str(e)}
    except IntegrityError:
        return 400, {"message": "Siswa ini sudah terdaftar di kursus tersebut."}

@api.delete("/enrollments/{enrollment_id}", tags=["Enrollments"], auth=GlobalAuth())
def delete_enrollment(request, enrollment_id: int):
    """Batalkan pendaftaran siswa (misal salah daftar atau refund). Butuh auth."""
    get_object_or_404(Enrollment, id=enrollment_id).delete()
    return {"success": True, "message": f"Enrollment {enrollment_id} berhasil dihapus"}


# ─────────────────────────────────────────────
# 👥 COURSE MEMBER ENDPOINTS
# Sebelumnya model ini sudah ada (lengkap dengan admin), tapi belum
# punya endpoint API sama sekali — jadi data "siapa pengajar/siswa
# resmi di kursus ini" tidak bisa diakses dari luar admin panel.
# ─────────────────────────────────────────────
class CourseMemberOut(Schema):
    id: int
    course_id: int
    user_id: int
    roles: str

    # PENTING: di model CourseMember, field FK-nya sendiri literally
    # bernama `course_id` dan `user_id` (bukan `course`/`user`), jadi
    # `getattr(obj, 'course_id')` otomatis mengembalikan OBJEK Course,
    # bukan integer — beda dengan model lain seperti CourseContent yang
    # field FK-nya bernama `course` (sehingga `course_id` otomatis jadi
    # raw integer id bawaan Django). Tanpa resolver ini, endpoint akan
    # error 500 karena Pydantic dapat objek padahal expect int.
    @staticmethod
    def resolve_course_id(obj):
        return obj.course_id_id

    @staticmethod
    def resolve_user_id(obj):
        return obj.user_id_id

class CourseMemberIn(Schema):
    course_id: int
    user_id: int
    roles: str = "std"

@api.get("/course-members", tags=["Course Members"], response=List[CourseMemberOut])
def list_course_members(request, course_id: Optional[int] = None):
    queryset = CourseMember.objects.all()
    if course_id is not None:
        queryset = queryset.filter(course_id=course_id)
    return list(queryset)

@api.post("/course-members", tags=["Course Members"], response=CourseMemberOut, auth=GlobalAuth())
def create_course_member(request, payload: CourseMemberIn):
    course = get_object_or_404(Course, id=payload.course_id)
    user = get_object_or_404(User, id=payload.user_id)
    return CourseMember.objects.create(course_id=course, user_id=user, roles=payload.roles)

@api.delete("/course-members/{member_id}", tags=["Course Members"], auth=GlobalAuth())
def delete_course_member(request, member_id: int):
    get_object_or_404(CourseMember, id=member_id).delete()
    return {"success": True, "message": f"Course member {member_id} berhasil dihapus"}