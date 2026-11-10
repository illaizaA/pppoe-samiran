# Integrasi pull MikroTik pada aplikasi existing

Backend Flask tetap memakai penyimpanan JSON existing. Poller terpisah memakai librouteros dan hanya mengirim tiga perintah print: identity, PPP secret (name/service saja), dan PPP active. Password PPPoE tidak diminta. Tidak ada operasi tambah/ubah/hapus akun atau disconnect.

## Hasil pemeriksaan dan penerapan lokal

Samiran telah terverifikasi melalui API port 8728 dengan akun monitoring. Pilihan operator adalah API biasa langsung dengan `--allow-plaintext`; opsi ini eksplisit dan tidak mengubah konfigurasi TLS. Candipetak port 8101 hanya terkonfirmasi TCP terbuka; jenis service dan autentikasi belum dikonfirmasi, sehingga konfigurasi default masih unknown dan tidak dilakukan login paksa.

Nama router pada impor ternyata kelompok wilayah. Snapshot Samiran berisi 717 akun: 614 cocok persis dengan data impor lintas 15 kelompok wilayah; 103 akun belum diimpor dilewati. Dua nama yang hanya berbeda kapitalisasi tidak dianggap username sama. Data impor tetap 626 pelanggan. Nama, alamat, ID, paket, kelompok wilayah, dan koordinat dipertahankan. Dua belas pelanggan yang tidak ditemukan tidak dijadikan OFFLINE. Jumlah snapshot dan hasil kecocokan dapat berubah pada pengambilan berikutnya.

Pembaruan pertama sudah diterapkan ke data lokal setelah backup pada runtime/backups/before-samiran-*. Tidak ada perubahan ke router. Nama sumber fisik disimpan terpisah sebagai source_router_key dan source_router_identity.

## Perintah

Instal: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`

Jalankan website: `.\.venv\Scripts\python.exe app.py` (PORT lokal 5081).

Ambil JSON saja, tanpa mengubah monitoring:

```powershell
.\.venv\Scripts\python.exe ambil_pppoe.py samiran --allow-plaintext
```

Ambil snapshot baru, simpan hasil_json/samiran_pppoe.json, dan perbarui website:

```powershell
.\.venv\Scripts\python.exe ambil_pppoe.py samiran --allow-plaintext --sync
```

Polling 60 detik di terminal kedua:

```powershell
.\.venv\Scripts\python.exe ambil_pppoe.py samiran --allow-plaintext --sync --watch
```

Ctrl+C menghentikan poller. Interval diatur MIKROTIK_POLL_INTERVAL_SECONDS pada .env. Global file lock runtime/mikrotik-poller.lock menolak poller/manual kedua yang bersamaan. Scheduler tidak dimulai pada import Flask, sehingga tidak tergandakan oleh worker/reloader. Jalankan satu proses backend untuk penyimpanan JSON existing. Untuk produksi, jalankan satu poller sebagai service/task terpisah; jangan menjalankan watch di setiap worker.

Candipetak: gunakan positional `candipetak` setelah teknisi mengonfirmasi service/port API dan .env disesuaikan. Jangan menandai port Winbox sebagai API. Poller saat ini memilih satu router per proses dan memakai lock global; hentikan poller Samiran sebelum tes manual Candipetak. Polling gabungan dua router belum diaktifkan pada tahap Samiran ini.

## Perlindungan data

Mode --sync memerlukan MIKROTIK_API_TOKEN yang sama di poller/backend dan memeriksa capability routeros_api_v1 sebelum mengirim. Ini mencegah snapshot masuk ke endpoint versi lama yang belum memahami pemetaan. .env dibaca otomatis; nilai environment proses menang. Konfigurasi rahasia eksternal lokal dipakai sebagai fallback untuk nilai kosong. Restart Flask setelah perubahan kode/.env.

Endpoint existing /api/update-pppoe menerima source=routeros_api, snapshot_type=pppoe_accounts, snapshot_complete=true, collected_at dengan zona waktu, dan identitas router. Kedua pembacaan akun/sesi wajib selesai sebelum file JSON diganti secara atomik. Snapshot parsial, stale, replay, username ganda, status invalid, dan field password ditolak. Snapshot lebih tua dari 180 detik harus ditarik ulang.

Username dicocokkan persis ke pelanggan existing. Username ambigu tidak diperbarui. Kepemilikan sumber yang sudah ditetapkan tidak boleh ditimpa oleh router fisik lain: akun yang ternyata ada di Samiran dan Candipetak harus diverifikasi/pemetaan sumbernya ditetapkan sebelum dialihkan. Kelompok wilayah CANDI tidak otomatis membuktikan router fisik Candipetak.

Jika pengambilan gagal, JSON sukses terakhir dipertahankan dan endpoint /api/router-health menandai STALE. Status pelanggan terakhir tidak diubah menjadi OFFLINE. Setelah 180 detik tanpa pembaruan valid, freshness API/UI juga otomatis menjadi STALE. UNKNOWN berarti belum ada pembuktian koneksi live atau akun tidak ditemukan pada snapshot lengkap. Status ONLINE/OFFLINE tetap nilai terakhir; baca bersama data_quality dan last_live_update.

## Notifikasi

Snapshot awal hanya membangun baseline. ONLINE terkonfirmasi lalu OFFLINE minimal 3 menit melalui pembaruan valid menghasilkan satu gangguan; ONLINE kembali menghasilkan pemulihan. Metadata notifikasi diambil per kelompok wilayah asli. Kegagalan router mereset kandidat gangguan yang belum terkonfirmasi. Tab dashboard tidak perlu dibuka, tetapi Flask dan poller harus tetap berjalan. Web Push tetap membutuhkan aktivasi perangkat dan localhost/HTTPS.

## Pemeriksaan

Lihat /admin, /dashboard, peta, /api/pppoes dan /api/router-health. API pelanggan memiliki source_router_key, source_router_identity, last_live_update, dan data_quality. Banner website menampilkan freshness per sumber router.

23 pengujian lulus sebelum penerapan lokal: regresi fitur existing, mapping lintas wilayah, metadata/koordinat, unknown/ambiguous usernames, konflik sumber, snapshot parsial/kedaluwarsa/replay, pembacaan terputus, pengiriman push, dan penanganan STALE. Pembacaan Samiran dan penerapan ke 626 pelanggan lokal juga diverifikasi tanpa perubahan metadata. Autentikasi/pembacaan Candipetak dan penampilan push perangkat nyata belum diuji.
