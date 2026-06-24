FROM python:3.12-slim

# Install library pendukung untuk PostgreSQL
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Default start command — dipakai kalau platform hosting (Railway/Render/dll)
# build & jalankan Dockerfile ini LANGSUNG tanpa docker-compose. Untuk dev
# lokal via `docker-compose up`, command ini di-override oleh docker-compose.yml.
# Gunicorn dipakai (bukan `manage.py runserver`) karena ini WSGI server yang
# memang ditujukan untuk production, bukan server pengembangan.
CMD sh -c "python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn myproject.wsgi:application --bind 0.0.0.0:${PORT:-8000}"