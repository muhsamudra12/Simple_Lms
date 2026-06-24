from django.urls import path
from . import views

urlpatterns = [
    # Akses localhost:8000 langsung merender daftar kursus (index.html) dengan context lengkap
    path('', views.index, name='index'),

    # Mengarah ke halaman statistik (stats.html) dengan context lengkap
    path('stats/', views.stats_view, name='stats'),

    # Mengarah ke halaman detail materi per-kursus (detail.html) dengan context lengkap
    path('course/<int:course_id>/', views.detail, name='course_detail'),
]
