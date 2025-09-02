NotifyEmailWA
==================================================
Sistem monitoring email berbasis IMAP yang mengirimkan notifikasi pesan baru beserta lampiran ke WhatsApp melalui API WhatsApp Web.js.

Ringkasan
--------------------------------------------------
NotifyEmailWA memantau akun email BPS melalui protokol IMAP dan mengirimkan notifikasi pesan baru ke grup atau personal WhatsApp. File lampiran email diunduh sementara, dikirim via WhatsApp, lalu dihapus dari server lokal. Sistem ini mendukung banyak akun email sekaligus dengan pemrosesan paralel.

Fitur
--------------------------------------------------
- Multi-akun email (konfigurasi via config.json)
- Monitoring folder email tertentu dengan mode IDLE (real-time)
- Kirim notifikasi pesan baru ke WhatsApp (grup atau personal)
- Kirim lampiran email (pdf, docx, zip, gambar, dsb.) ke WhatsApp
- Menyimpan log aktivitas di folder logs/
- Menyimpan state waktu terakhir diproses (last_time.json) agar tidak duplikasi
- Menangani koneksi terputus dan auto-reconnect
- API WhatsApp berbasis Express.js dengan whatsapp-web.js

Struktur Direktori
--------------------------------------------------
NotifyEmailWA/
├── email_checker.py          # Skrip utama monitoring email
├── config.json               # Konfigurasi akun email dan folder
├── last_time.json            # Catatan timestamp terakhir tiap folder
├── attachments/              # Folder lampiran sementara
├── logs/                     # Log aktivitas
└── whatsapp-bot/             # Backend WhatsApp API (Node.js)

Konfigurasi Email (config.json)
--------------------------------------------------
Contoh struktur config.json:
[
  {
    "email": "user@bps.go.id",
    "password": "password",
    "group_id": "120363xxxx@g.us",
    "personal_id": "628xxxxxx@c.us",
    "folders": [
      {"name": "INBOX", "target": "group"},
      {"name": "Sent", "target": "personal"}
    ]
  }
]

Komponen Utama
--------------------------------------------------
1) email_checker.py
   - Memantau email via IMAPClient
   - Mengunduh lampiran dan mengirim ke API WhatsApp
   - Memperbarui last_time.json untuk menghindari notifikasi ulang

2) whatsapp-bot/index.js
   - Server Node.js dengan Express
   - Endpoint REST API:
       - /status (GET) → status bot
       - /send (POST) → kirim pesan teks
       - /file (POST) → kirim file/lampiran
   - Menggunakan whatsapp-web.js dengan LocalAuth untuk sesi persisten
   - Log aktivitas ke logs/history.log

Ketergantungan
--------------------------------------------------
Python:
- imapclient
- requests
- email (builtin)
- pathlib, json, threading, concurrent.futures

Node.js:
- whatsapp-web.js
- express
- multer
- qrcode-terminal

Setup Python
--------------------------------------------------
pip install imapclient requests

Setup Node.js
--------------------------------------------------
cd whatsapp-bot
npm install express whatsapp-web.js multer qrcode-terminal

Cara Menjalankan
--------------------------------------------------
1) Siapkan config.json berisi akun email, password, dan folder target.
2) Jalankan WhatsApp bot (Node.js):
   node index.js
3) Pindai QR code untuk login WhatsApp Web.js.
4) Jalankan email checker (Python):
   python email_checker.py
5) Bot akan memantau email, mengirim notifikasi pesan baru dan lampiran ke WhatsApp sesuai konfigurasi.

Struktur Log
--------------------------------------------------
- email_checker.log → Aktivitas Python
- history.log → Aktivitas Node.js (WA bot)

Keamanan
--------------------------------------------------
- Jangan commit config.json dan credentials ke repo publik.
- Gunakan password aplikasi atau mekanisme token bila memungkinkan.
- Lindungi server dari akses tidak sah (firewall, autentikasi API).

Lisensi
--------------------------------------------------
Tambahkan lisensi sesuai kebutuhan (MIT, Apache 2.0, dsb.).
