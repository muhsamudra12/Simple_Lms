from django.urls import path
from . import views

urlpatterns = [
    # Akses localhost:8000 langsung merender daftar kursus (index.html) dengan context lengkap
    path('', views.index, name='index'),

    # Mengarah ke halaman statistik (stats.html) dengan context lengkap
    path('stats/', views.stats_view, name='stats'),

    # Mengarah ke halaman detail materi per-kursus (detail.html) dengan context lengkap
    path('course/<int:course_id>/', views.detail, name='course_detail'),

    # Login / Register / Logout untuk pengunjung website (session-based)
    path('login/', views.login_page, name='login_page'),
    path('register/', views.register_page, name='register_page'),
    path('logout/', views.logout_view, name='logout_view'),
    path('profile/', views.profile_page, name='profile_page'),

    # Verifikasi email & lupa password
    path('verify-email/<uuid:token>/', views.verify_email_page, name='verify_email_page'),
    path('resend-verification/', views.resend_verification_page, name='resend_verification_page'),
    path('forgot-password/', views.forgot_password_page, name='forgot_password_page'),
    path('reset-password/<uuid:token>/', views.reset_password_page, name='reset_password_page'),

    # Sertifikat — diakses lewat kode UUID (bukan ID urut), publik bisa
    # buka untuk keperluan verifikasi tanpa perlu login.
    path('certificate/<uuid:code>/', views.certificate_view, name='certificate_view'),
    path('certificate/<uuid:code>/download/', views.certificate_pdf, name='certificate_pdf'),
]
