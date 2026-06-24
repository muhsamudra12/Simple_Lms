#!/bin/sh
# Script start container — dipisah dari Dockerfile CMD supaya expansi
# variable $PORT TERJAMIN jalan, apapun cara platform hosting (Railway,
# Render, dll) menjalankan container-nya (lewat shell atau langsung exec).
# Shebang #!/bin/sh di baris pertama memastikan OS selalu menjalankan
# script ini lewat shell, sehingga ${PORT:-8000} pasti ter-expand.
set -e

echo "Menjalankan migrasi database..."
python manage.py migrate --noinput

echo "Mengumpulkan static files..."
python manage.py collectstatic --noinput

echo "Menjalankan Gunicorn di port ${PORT:-8000}..."
exec gunicorn myproject.wsgi:application --bind "0.0.0.0:${PORT:-8000}"
