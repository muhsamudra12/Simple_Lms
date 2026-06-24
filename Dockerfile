FROM python:3.12-slim

# Install library pendukung untuk PostgreSQL
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x start.sh

EXPOSE 8000

# Pakai exec form (array) + script start.sh terpisah supaya expansi
# variable $PORT terjamin jalan apapun cara platform hosting invoke
# container ini (lihat start.sh untuk detail).
CMD ["./start.sh"]