# Menyiapkan Web Push lokal

## Buat pasangan VAPID baru

Jalankan dari PowerShell di folder project `C:\laragon\www\pppoe-samiran`. Pakai alamat email yang benar untuk `--subject`; jangan gunakan alamat contoh `admin@domainanda.com`.

```powershell
& .\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
& .\.venv\Scripts\python.exe .\scripts\setup_notifications.py `
  --subject "mailto:email-anda@domain.com"
```

Perintah ini membuat **pasangan VAPID baru** dan menulis konfigurasinya ke `.env`; private key disimpan di `runtime/secrets/vapid_private.pem` dan tidak dicetak ke terminal. Terminal menampilkan public key. Aktivasi perangkat tidak memerlukan kode enrollment.

Script menolak menimpa pasangan key yang sudah ada agar subscription aktif tidak rusak tanpa sengaja. Untuk rotasi yang memang disengaja, tambahkan `--force`:

```powershell
& .\.venv\Scripts\python.exe .\scripts\setup_notifications.py `
  --subject "mailto:email-anda@domain.com" --force
```

Rotasi membuat pasangan key baru. Perangkat perlu diaktifkan ulang. Jangan membagikan private key.

## Aktifkan perangkat

1. Jalankan ulang server setelah `.env` diperbarui:

   ```powershell
   & .\.venv\Scripts\python.exe .\app.py
   ```

2. Buka `http://localhost:5081/notifications` di Chrome atau Edge.
3. Tekan **Aktifkan Notifikasi**, lalu izinkan notifikasi browser.
4. Tekan **Kirim Notifikasi Uji** untuk memeriksa perangkat.

Tidak perlu memasukkan kode aktivasi. Setiap perangkat/browser cukup diaktifkan sendiri. `localhost` dan domain HTTPS produksi adalah origin berbeda, jadi keduanya perlu aktivasi masing-masing.

## Push otomatis dari router

`MIKROTIK_API_TOKEN` tetap dipakai router untuk mengirim snapshot dan berbeda dari key VAPID. Aktivasi push browser tidak memakai token router.

Untuk snapshot `source=routeros_api`, snapshot pertama membangun baseline. Perubahan status yang terlihat pada dua snapshot berurutan (default `PPPOE_STATUS_CONFIRMATIONS=2`) membuat ringkasan push online/offline. Setelah OFFLINE berlanjut minimal 180 detik, backend juga mencatat detail gangguan pelanggan. Saat kembali ONLINE, histori mencatat pemulihan dan durasinya. Impor CSV tidak memicu insiden. Jika router tidak mengirim snapshot, backend tidak menebak bahwa semua pelanggan OFFLINE.

Jika router yang pernah tersinkron tidak mengirim snapshot sukses selama batas `MIKROTIK_HEARTBEAT_TIMEOUT_SECONDS` (default 180 detik), backend mengirim satu push **Gangguan MikroTik**. Monitor berjalan selama proses `python app.py` hidup. Untuk daftar lengkap sesi aktif, payload harus menyertakan `snapshot_type: "active_sessions"`; hanya pada mode itu username router yang tidak tercantum dianggap OFFLINE.

## Konfigurasi dan penyimpanan

File `.env` dan `runtime/secrets/vapid_private.pem` tidak masuk repository. Pertahankan keduanya sebagai rahasia dan buat backup aman sebelum pindah server. Saat deploy, pakai HTTPS, salin private key ke lokasi rahasia permanen, lalu atur `VAPID_PRIVATE_KEY_FILE` ke path key tersebut dan isi `PUBLIC_BASE_URL` dengan origin HTTPS.

Jika sebelumnya menjalankan setup lama yang membuat `%TEMP%\jss-monitoring-local-secrets\notifications.json`, file tersebut tidak dipakai untuk key baru selama field VAPID di `.env` sudah terisi. Tidak perlu menghapusnya untuk menyelesaikan setup.

Penampilan notifikasi Windows juga bergantung pada izin browser dan pengaturan OS. Pesan bahwa layanan push menerima kiriman belum menjamin OS menampilkannya, misalnya saat Do Not Disturb aktif.
