#!/bin/sh
# Script start container — dipisah dari Dockerfile CMD supaya expansi
# variable $PORT TERJAMIN jalan, apapun cara platform hosting (Railway,
# Render, dll) menjalankan container-nya (lewat shell atau langsung exec).
# Shebang #!/bin/sh di baris pertama memastikan OS selalu menjalankan
# script ini lewat shell, sehingga ${PORT:-8000} pasti ter-expand.
set -e

# jwt-signing.pem/.pub SENGAJA tidak ikut di-commit ke git (lihat
# .gitignore) karena itu private key. Artinya begitu deploy dari GitHub,
# file ini PASTI tidak ada di server — kalau tidak di-generate ulang di
# sini, semua fitur login akan crash 500 (FileNotFoundError). Generate
# otomatis kalau belum ada; kalau platform hosting punya persistent
# volume, key ini akan tetap ada di deploy berikutnya (tidak digenerate
# ulang setiap saat, supaya token lama tidak langsung invalid semua).
if [ ! -f jwt-signing.pem ]; then
    echo "jwt-signing.pem belum ada, membuat key pair baru..."
    python manage.py make_jwt_key
fi

echo "Menjalankan migrasi database..."
python manage.py migrate --noinput

echo "Mengumpulkan static files..."
python manage.py collectstatic --noinput

echo "Menjalankan Gunicorn di port ${PORT:-8000}..."
exec gunicorn myproject.wsgi:application --bind "0.0.0.0:${PORT:-8000}"
