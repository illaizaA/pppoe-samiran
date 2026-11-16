# Web Push Monitoring PPPoE Samiran

Panduan setup lokal: `NOTIFIKASI-LOKAL.md`. Jalankan `python scripts/setup_notifications.py --subject "mailto:email-anda@domain.com"` untuk membuat pasangan VAPID baru di `.env`. Buka `http://localhost:5081/notifications` dan aktifkan notifikasi perangkat; tidak perlu memasukkan kode. Setiap browser/perangkat harus didaftarkan sendiri.

## Alur

`add_notification` tetap menyimpan ke `notifications.json` dan mengirim push melalui pywebpush. Subscription disimpan pada `push_subscriptions.json` dengan hash identitas perangkat acak yang disimpan browser pada localStorage. Cookie sesi melindungi CSRF. Identitas perangkat membatasi perubahan, penghapusan, dan uji subscription pada perangkat pemiliknya. Aktivasi perangkat tidak memerlukan kode enrollment.

`/api/update-pppoe` menerima data router dengan token MikroTik. Untuk snapshot `source=routeros_api`, snapshot pertama membangun baseline; perubahan status diringkas ke notifikasi dan push setelah terlihat pada dua snapshot berturut-turut (`PPPOE_STATUS_CONFIRMATIONS`, default 2). Data terputus tidak dianggap semua pelanggan OFFLINE, dan perubahan pelanggan yang tidak ditemukan dalam snapshot lengkap tetap UNKNOWN. Kandidat ringkasan direset bila jeda sampel melebihi `LIVE_SAMPLE_MAX_GAP_SECONDS` (default 360 detik); state tersimpan di `pppoe_status_snapshots.json`.

Peringatan ringkasan status dikirim sebelum detail insiden. ONLINE yang berlanjut menjadi OFFLINE minimal 180 detik membuat satu catatan gangguan pelanggan; sampel ONLINE berikutnya membuat catatan pemulihan dan durasinya. Jika tidak ada snapshot router sukses selama `MIKROTIK_HEARTBEAT_TIMEOUT_SECONDS` (default 180 detik), monitor backend mengirim satu peringatan Gangguan MikroTik. Peringatan berulang diaktifkan kembali setelah snapshot baru diterima. Pemeriksa berjalan pada proses `python app.py`; Flask dan poller harus tetap hidup.

Daftar lengkap sesi aktif harus diberi `snapshot_type=active_sessions`. Hanya pada mode tersebut username pelanggan router yang tidak tercantum dianggap OFFLINE. Payload parsial tidak boleh memakai penanda ini. Gunakan polling 30–60 detik untuk mendekati konfirmasi 3 menit. Waktu insiden memakai waktu penerimaan server UTC.

Edit PPPoE tetap menyimpan notifikasi antrean. Callback clear-queue hanya menghapus antrean; belum memverifikasi nilai aktual router, sehingga tidak dibuat klaim sukses penerapan.

## Konfigurasi

Install requirements, lalu jalankan setup sesuai langkah di `NOTIFIKASI-LOKAL.md`. Script membuat key baru dan menolak menimpa pasangan yang sudah ada. Gunakan `--force` hanya untuk rotasi yang disengaja. `.env` dibaca otomatis sebelum Flask diinisialisasi. `VAPID_PRIVATE_KEY_FILE` menunjuk PEM lokal (`runtime/secrets/vapid_private.pem`); `VAPID_PUBLIC_KEY` dan `VAPID_SUBJECT` melengkapi VAPID. `MIKROTIK_API_TOKEN` dipakai untuk autentikasi API router. `PUBLIC_BASE_URL` diatur sesuai origin saat deploy.

Private key dan `.env` jangan disimpan di repository atau frontend. Perubahan VAPID memerlukan subscription ulang pada browser yang pernah diaktifkan. Pengaturan fallback lama melalui `.local-config-path` atau `JSS_CONFIG_FILE` tetap dibaca untuk nilai yang belum diatur pada environment.

## Operasional

HTTP 404/410 dari layanan push menghapus subscription; kegagalan sementara mempertahankannya dan mencatat log. Push rutin dikirim melalui pool dua worker dengan timeout 5 detik per perangkat; belum ada retry durable. Gunakan satu proses/worker karena penyimpanan JSON memakai lock dalam proses.

Saat deploy, gunakan HTTPS. Origin localhost dan domain produksi memerlukan aktivasi perangkat masing-masing. Browser dan OS harus mengizinkan notifikasi. Penerimaan layanan push belum membuktikan penampilan pada perangkat.

## Verifikasi

`python -m unittest discover -s tests -v` menguji aktivasi, CSRF, kepemilikan subscription, unsubscribe, expired subscription, kegagalan sementara, dan insiden otomatis. Penampilan perangkat nyata perlu diuji setelah izin diberikan.

Referensi: https://github.com/web-push-libs/pywebpush
