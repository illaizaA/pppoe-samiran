# Menjalankan notifikasi lokal

Setup sudah dijalankan pada komputer ini. Kunci VAPID dan token berada di luar proyek:

`%TEMP%\jss-monitoring-local-secrets\`

- `notifications.json`: konfigurasi yang dimuat otomatis sebelum Flask dibuat.
- `vapid-private.pem`: private key, jangan dibagikan atau diunggah ke repository.
- `TOKEN-MIKROTIK.txt`: token untuk script router lokal.

File `.local-config-path` hanya menyimpan lokasi konfigurasi dan masuk .gitignore. Environment server yang diatur secara eksplisit tetap diprioritaskan atas file konfigurasi.

## Tes perangkat Windows

1. Jalankan `START-LOKAL.bat` atau `python app.py`.
2. Buka **http://localhost:5081/notifications** melalui Chrome/Edge.
3. Tekan **Aktifkan Notifikasi** sekali, lalu izinkan notifikasi browser. Tidak perlu login.
4. Tombol **Kirim Notifikasi Uji** hanya mengecek perangkat, tidak mengubah pelanggan atau antrean MikroTik.

Sesudah aktif, pemberitahuan gangguan dikirim **otomatis oleh backend**. Tidak perlu menekan tombol uji, membuka halaman, atau menunggu refresh dashboard. Subscription terikat perangkat/browser, bukan akun. Semua perangkat yang diaktifkan menerima notifikasi penting semua router. Gunakan Nonaktifkan Notifikasi untuk menghentikan pengiriman.

Pengujian API dan logika otomatis telah dilakukan. Penampilan notifikasi Windows nyata tetap perlu persetujuan izin browser pada perangkat Anda. Pesan bahwa layanan push menerima pengiriman belum menjamin OS menampilkan notifikasi (misalnya saat Do Not Disturb aktif).

## Sumber deteksi otomatis

Backend menerima sampel dari `/api/update-pppoe` dengan `X-API-Token` sesuai TOKEN-MIKROTIK.txt. Setup lokal sekarang menyiapkan token; jangan menyalin token ke frontend. Script MikroTik harus menggunakan token yang sama, termasuk saat mengambil/menghapus antrean.

Pelanggan yang berstatus ONLINE dari sampel valid, kemudian OFFLINE terkonfirmasi minimal 180 detik pada sampel berikutnya, memicu notifikasi otomatis. Sampel ONLINE berikutnya memicu pemulihan. Impor CSV tidak memicu insiden. Jika router tidak mengirim data sama sekali, backend tidak menebak bahwa seluruh pelanggan OFFLINE.

Untuk daftar lengkap sesi aktif, payload harus menyertakan `snapshot_type: "active_sessions"`. Hanya pada mode tersebut pelanggan router yang tidak tercantum dianggap OFFLINE. Contoh:

```json
{"router":"NAMA ROUTER PERSIS","snapshot_type":"active_sessions","pppoe":[{"user":"username-pppoe","status":"ONLINE"}]}
```

Kirim tiap 30–60 detik untuk konfirmasi mendekati 3 menit. Jangan memberi penanda snapshot lengkap jika pengiriman sebenarnya hanya sebagian data. Gunakan alamat server lokal yang dapat dijangkau MikroTik untuk API; localhost hanya untuk browser pada komputer server.

## Saat deploy HTTPS

Unggah source dan instal requirements. Salin konfigurasi dan pasangan VAPID ke direktori rahasia permanen di server, sesuaikan path private key, VAPID_SUBJECT, PUBLIC_BASE_URL, . Set `JSS_CONFIG_FILE` menunjuk file tersebut. Pertahankan pasangan VAPID; jangan generate ulang pada setiap startup.

Folder Temp dapat dibersihkan Windows: cadangkan rahasia ini ke lokasi permanen yang aksesnya dibatasi sebelum deploy. Tidak ada akun atau login tambahan. Siapa pun yang memiliki akses halaman dapat mengaktifkan notifikasi pada perangkatnya. File LOGIN-LOKAL.txt dari setup lama tidak digunakan.

Browser pada domain HTTPS memerlukan aktivasi subscription sendiri karena origin berbeda dari localhost. Sesuaikan token dan URL pengiriman di script MikroTik dengan server deploy.

Penyimpanan JSON memakai lock dalam satu proses; gunakan satu worker. Pengiriman sinkron memiliki timeout 5 detik per perangkat dan belum memiliki retry background. Detail: WEB-PUSH.md.
