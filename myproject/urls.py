from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
# Pastikan kedua instance diimport jika posisinya terpisah
from tasks.api import api as api_v1  # Mengarah ke engine lama / Pertemuan 10
# dari tasks.api_v2 import api as api_v2 # <- Aktifkan & sesuaikan baris ini jika file API v2 kamu dipisah

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('tasks.urls')),                           # Menangani halaman Beranda langsung (localhost:8000)
    path('silk/', include('silk.urls', namespace='silk')),     # Menangani Silk Profiler

    # ─── ROUTING ENDPOINT SWAGGER & REST API ───
    path('api/v1/', api_v1.urls),                              # Tetap mempertahankan fitur UTS lama / Pertemuan 10
    path('api/v2/', api_v1.urls),                              # Sementara diarahkan ke instance aktif kamu agar tidak 404
]

# Serve MEDIA (foto profil upload user). Sengaja TIDAK digate `if settings.DEBUG`
# seperti pola umum Django — project ini skalanya kecil dan belum pakai
# object storage/CDN terpisah, jadi Django sendiri yang serve file media
# baik di lokal maupun production.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
