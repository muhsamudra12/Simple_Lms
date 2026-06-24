# Tutorial Uji API Simple LMS dengan Postman

Dokumen ini panduan langkah-demi-langkah buat nguji REST API Simple LMS pakai Postman, sebagai bukti pengujian sesuai ketentuan UAS ("Uji minimal pakai Postman").

## 1. Persiapan

1. Pastikan project Django sudah jalan lokal:
   ```bash
   python manage.py runserver
   ```
   Server akan jalan di `http://127.0.0.1:8000`.

2. Install Postman (kalau belum ada) dari [postman.com/downloads](https://www.postman.com/downloads/).

3. Import file **`Simple-LMS-API.postman_collection.json`** ke Postman:
   - Buka Postman → klik **Import** (pojok kiri atas)
   - Pilih file `Simple-LMS-API.postman_collection.json`
   - Collection bernama **"Simple LMS API v2 - UAS"** akan muncul di sidebar kiri, sudah terbagi jadi 8 folder sesuai kategori endpoint.

> 💡 Collection ini sudah dikonfigurasi pakai **variable** `base_url` (default `http://127.0.0.1:8000/api/v2`) dan `jwt_token` (otomatis terisi setelah login). Jadi kamu tidak perlu ngetik ulang URL atau copy-paste token manual.

## 2. Setup ID Contoh (PENTING — jangan skip)

Collection ini pakai beberapa **variable** (`sample_teacher_id`, `sample_course_id`, `sample_student_id`) supaya request `Create Course`, `Create Content`, dll tidak hardcode angka sembarangan. Tapi ID asli di database kamu pasti **beda** dengan punya orang lain (tergantung data yang sudah ada). Jadi sebelum mulai testing, samakan dulu:

1. Jalankan request **"List Users"** (folder 3) → catat salah satu `id` di response, misal `id: 5`.
2. Jalankan request **"List Courses"** (folder 2) → catat salah satu `id` di response, misal `id: 8`.
3. Klik nama **collection** "Simple LMS API v2 - UAS" di sidebar kiri → tab **Variables** → isi `sample_teacher_id` dan `sample_course_id` dengan angka yang kamu catat tadi → **Save**.

> ⚠️ Endpoint **Delete** (Delete Comment, Delete Enrollment, Delete Content, Delete Course Member) itu pakai ID milik resource itu sendiri (misal ID komentar), **bukan** `course_id`. Selalu cek dulu ID yang benar lewat request List/Get di folder yang sama sebelum klik Delete.

## 3. Urutan Testing yang Direkomendasikan

### Langkah 1 — Register & Login (folder "1. Authentication")

1. Jalankan request **"Register User"**.
   - Harus dapat response `201 Created` dengan pesan "Registrasi berhasil!".
   - 📸 *Screenshot ini buat dokumentasi.*
2. Jalankan request **"Login (otomatis simpan token)"**.
   - Harus dapat response `200 OK` berisi `token` (JWT, formatnya 3 bagian dipisah titik).
   - Tab **Tests** di request ini otomatis menyimpan token itu ke variable `jwt_token` — cek di pojok kanan atas Postman (ikon mata 👁) untuk konfirmasi variable-nya sudah terisi.
   - 📸 *Screenshot response + screenshot tab Tests yang menunjukkan token tersimpan.*

### Langkah 2 — Coba endpoint publik (folder "2. Courses", "3. Users", dst)

1. Jalankan **"List Courses (pagination + filter)"** — endpoint ini publik, harus jalan tanpa perlu login (`200 OK`).
2. Coba ubah parameter `search` jadi nama kursus kamu, atau `sort_by=-price` buat lihat fitur filtering & sorting beraksi.

### Langkah 3 — Coba endpoint yang butuh AUTH (Bearer Token)

1. **Tanpa login dulu**, coba langsung jalankan **"Create Course (butuh token)"** di folder Courses.
   - Harus ditolak `401 Unauthorized` (karena belum ada token / token kosong).
   - 📸 *Screenshot ini penting — bukti AUTH benar-benar berfungsi menolak akses tanpa izin.*
2. Jalankan ulang request **Login** (langkah 1) supaya `jwt_token` terisi.
3. Jalankan lagi **"Create Course (butuh token)"** — sekarang harus berhasil `200 OK`.
   - 📸 *Screenshot response sukses, sandingkan dengan screenshot 401 sebelumnya sebagai bukti perbandingan.*

### Langkah 4 — Coba fitur Throttling (rate-limit)

1. Buka folder **"5. Comments"** → jalankan request **"Create Comment (publik, ada rate-limit)"**.
2. Klik tombol **Send** berkali-kali secara cepat (lebih dari 10 kali dalam 1 menit).
   - Request ke-11 dan seterusnya harus dapat response `429 Too Many Requests`.
   - 📸 *Screenshot response 429 ini — bukti throttling aktif.*

### Langkah 5 — Coba validasi bisnis (kuota kursus penuh)

1. Di folder **"6. Enrollments"**, jalankan **"Create Enrollment (butuh token)"** dengan `student_id` tertentu.
2. Ulangi dengan `student_id` lain sampai jumlah enrollment di kursus itu melebihi `max_students`-nya (cek/ubah dulu nilai `max_students` course tersebut lewat Django Admin kalau perlu, supaya gampang ditest, misal set ke 1).
   - Enrollment yang melebihi kuota harus ditolak `400` dengan pesan "Kursus ... sudah penuh".
   - 📸 *Screenshot pesan error ini.*

### Langkah 6 — Coba error handling kalkulator

1. Folder **"8. Hello & Calculator"** → jalankan **"Calculator - Divide by Zero"**.
   - Harus dapat response rapi `400 Bad Request` dengan pesan `"Tidak bisa dibagi 0"` — **bukan** `500 Internal Server Error` dengan traceback.
   - 📸 *Screenshot ini bagus buat menunjukkan error handling yang baik.*

### Langkah 7 — Cek dokumentasi Swagger (opsional, pelengkap)

Buka browser ke `http://127.0.0.1:8000/api/v2/docs` — ini dokumentasi otomatis (Swagger UI) dari semua endpoint yang sama. Bisa dipakai sebagai pelengkap bukti dokumentasi API selain Postman.

## 4. Checklist Screenshot buat Dokumentasi PDF

Supaya gampang nyusun dokumen nanti, kumpulin screenshot ini:

- [ ] Register berhasil (201)
- [ ] Login berhasil + token muncul (200)
- [ ] List courses publik (200)
- [ ] Create course **tanpa** token (401) — bukti AUTH jalan
- [ ] Create course **dengan** token (200) — perbandingan
- [ ] Comment ke-11 kena rate-limit (429)
- [ ] Enrollment ditolak karena kursus penuh (400)
- [ ] Kalkulator dibagi nol → 400 rapi (bukan 500)
- [ ] Swagger docs (`/api/v2/docs`) kebuka di browser

## 5. Troubleshooting

| Masalah | Solusi |
|---|---|
| Semua request kena `Could not get response` | Pastikan `python manage.py runserver` masih jalan di terminal |
| Login sukses tapi request lain tetap 401 | Cek variable `jwt_token` di Postman (ikon 👁 pojok kanan atas) — kalau kosong, jalankan ulang request Login |
| Register selalu gagal 400 "Username sudah digunakan" | Ganti `username` di body request jadi yang belum pernah dipakai |
| Mau test API yang sudah di-hosting (bukan localhost) | Ubah variable `base_url` di collection (klik collection → tab Variables) jadi URL hosting kamu, misal `https://nama-app.up.railway.app/api/v2` |
