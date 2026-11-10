# Web Push Monitoring JSS — tanpa login

Panduan lokal: NOTIFIKASI-LOKAL.md. Buka http://localhost:5081/notifications dan aktifkan notifikasi perangkat sekali. Tidak memerlukan login atau akun teknisi. Semua perangkat yang diaktifkan menerima notifikasi penting dari seluruh router.

## Alur
add_notification tetap menyimpan ke notifications.json existing dan mengirim push melalui pywebpush. Subscription disimpan pada push_subscriptions.json dengan hash identitas perangkat acak yang disimpan browser pada localStorage. Sesi cookie hanya untuk perlindungan CSRF. Perangkat hanya boleh mengubah, menghapus, dan menguji subscription miliknya. Subscription legacy akun tidak menerima pengiriman sampai didaftarkan ulang dengan bukti kunci yang sama.

/api/update-pppoe menerima data router dengan token. Baseline ONLINE berasal dari MikroTik; impor CSV tidak memicu insiden. OFFLINE terkonfirmasi minimal 180 detik pada sampel berikutnya menghasilkan satu peringatan. Sampel ONLINE berikutnya menghasilkan pemulihan dan durasi gangguan. Tidak perlu klik atau membuka dashboard. Data terputus tidak dianggap semua pelanggan OFFLINE. Kandidat belum terkonfirmasi direset bila jeda sampel melebihi LIVE_SAMPLE_MAX_GAP_SECONDS (default 360 detik). State disimpan dalam connection_incidents.json.

Daftar lengkap sesi aktif harus diberi snapshot_type=active_sessions. Hanya pada mode tersebut username pelanggan router yang tidak tercantum dianggap OFFLINE. Payload parsial tidak boleh memakai penanda ini. Gunakan polling 30–60 detik untuk mendekati konfirmasi 3 menit. Waktu insiden memakai waktu penerimaan server UTC.

Edit PPPoE tetap menyimpan notifikasi antrean. Callback clear-queue hanya menghapus antrean; belum memverifikasi nilai aktual router, sehingga tidak dibuat klaim sukses penerapan.

## Konfigurasi
Instal requirements, kemudian jalankan python scripts/setup_notifications.py. Pasangan VAPID yang sudah ada dipertahankan. Rahasia berada di luar repository dan dimuat melalui pointer .local-config-path atau environment JSS_CONFIG_FILE yang menunjuk JSON eksternal. Environment eksplisit diprioritaskan. File .env tidak dibaca otomatis.

Konfigurasi: SECRET_KEY, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY (path PEM eksternal), VAPID_SUBJECT (kontak mailto: atau HTTPS), MIKROTIK_API_TOKEN (samakan dengan script router), PUBLIC_BASE_URL, dan PORT (lokal 5081). Tidak memerlukan TECHNICIAN_ACCOUNTS_JSON atau LOGIN-LOKAL.txt. Jangan simpan private key/token di frontend atau repository. Cadangkan rahasia lokal di folder Temp ke direktori permanen sebelum deploy.

## Operasional
HTTP 404/410 dari layanan push menghapus subscription; kegagalan sementara mempertahankannya dan mencatat log. Pengiriman sinkron memakai timeout 5 detik per perangkat; belum ada retry background. Gunakan satu proses/worker karena penyimpanan JSON memakai lock dalam proses.

Saat deploy, gunakan HTTPS. Origin localhost dan domain produksi memerlukan aktivasi perangkat masing-masing. Browser dan OS harus mengizinkan notifikasi. Penerimaan layanan push belum membuktikan penampilan pada perangkat. Hak akses monitoring existing tidak berubah: siapa pun yang bisa membuka halaman dapat mengaktifkan perangkatnya.

## Verifikasi
python -m unittest discover -s tests -v menguji aktivasi tanpa login, CSRF, kepemilikan subscription, unsubscribe, expired subscription, kegagalan sementara, dan insiden otomatis tanpa browser/klik. Penampilan perangkat nyata perlu diuji setelah izin diberikan.

Referensi: https://github.com/web-push-libs/pywebpush
