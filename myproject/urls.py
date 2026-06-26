from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve as static_serve
from tasks.views import robots_txt, sitemap_xml
# Pastikan kedua instance diimport jika posisinya terpisah
from tasks.api import api as api_v1  # Mengarah ke engine lama / Pertemuan 10
# dari tasks.api_v2 import api as api_v2 # <- Aktifkan & sesuaikan baris ini jika file API v2 kamu dipisah

urlpatterns = [
    path('admin/', admin.site.urls),
    path('robots.txt', robots_txt, name='robots_txt'),
    path('sitemap.xml', sitemap_xml, name='sitemap_xml'),
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
#
# PENTING: helper `django.conf.urls.static.static()` TIDAK BISA dipakai di sini
# walau kelihatannya pas — helper itu, di dalam source code Django-nya sendiri,
# otomatis return [] (alias tidak generate route apa-apa) kalau DEBUG=False.
# Itu sebabnya foto profil 404 / broken image di production (Railway, DEBUG=False)
# padahal upload-nya sendiri sukses. Makanya di sini route-nya didaftarkan manual
# pakai view `serve` langsung, supaya jalan terus baik DEBUG True maupun False.
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', static_serve, {'document_root': settings.MEDIA_ROOT}),
]
