# JSON dummy untuk notifikasi otomatis

Data ini khusus simulasi dengan router `ROUTER DUMMY NOTIFIKASI` dan dua username berawalan `dummy-notifikasi-`. Nama, alamat, dan koordinat merupakan data uji. Tidak ada instruksi perubahan router fisik.

## Persiapan

Pastikan Flask berjalan di http://localhost:5081 dan perangkat sudah diaktifkan pada halaman Notifikasi. Jalankan perintah berikut di PowerShell dari folder proyek:

```powershell
$dummyBase = 'http://localhost:5081'
$dummyConfigPath = (Get-Content -LiteralPath '.local-config-path' -Raw).Trim()
$dummyConfig = Get-Content -LiteralPath $dummyConfigPath -Raw | ConvertFrom-Json
$dummyHeaders = @{ 'X-API-Token' = $dummyConfig.MIKROTIK_API_TOKEN }

function Send-DummyStatus([string]$FileName) {
    $dummyBody = Get-Content -LiteralPath (Join-Path 'examples/notifikasi-dummy' $FileName) -Raw
    Invoke-RestMethod -Uri "$dummyBase/api/update-pppoe" -Method Post -Headers $dummyHeaders -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($dummyBody))
}
```

Jika environment `MIKROTIK_API_TOKEN` server berbeda dari file konfigurasi, gunakan token yang aktif pada server untuk header. Jangan membagikan token tersebut.

## 1. Masukkan identitas pelanggan uji

File `00-pelanggan-import.json` dapat diimpor melalui fitur impor pelanggan existing dengan mode **gabung/merge**. Alternatif PowerShell:

```powershell
$dummyCustomers = Get-Content -LiteralPath 'examples/notifikasi-dummy/00-pelanggan-import.json' -Raw
Invoke-RestMethod -Uri "$dummyBase/api/import-customers?mode=merge" -Method Post -Headers $dummyHeaders -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($dummyCustomers))
```

Impor ini hanya menambahkan identitas nama/wilayah. Status impor bukan bukti koneksi dan tidak memicu notifikasi gangguan.

## 2. Kirim baseline ONLINE

```powershell
Send-DummyStatus '01-online.json'
```

Andi dan Budi ONLINE. Pengiriman pertama membangun baseline; belum ada gangguan.

## 3. Simulasikan Andi OFFLINE

```powershell
Send-DummyStatus '02-offline.json'
```

Catat waktunya. Kirim perintah OFFLINE yang sama sekitar setiap 60 detik. Setelah minimal 180 detik dari kiriman OFFLINE pertama, kirim sekali lagi. Contoh jadwal kiriman: detik 0, 60, 120, dan 185.

Pada kiriman terakhir tersebut, backend membuat satu notifikasi gangguan dan mengirim push ke perangkat aktif. Budi tetap ONLINE. Kirim OFFLINE lagi untuk memeriksa bahwa notifikasi tidak berulang. Tidak perlu menekan tombol uji atau membuka dashboard selama proses ini.

Jangan mengganti timestamp JSON untuk mempercepat konfirmasi: deteksi memakai waktu penerimaan server. Jangan mengubah ambang 3 menit untuk tes ini. Jeda sampel lebih dari 360 detik mereset kandidat yang belum dikonfirmasi.

## 4. Simulasikan pemulihan

```powershell
Send-DummyStatus '03-pulih-online.json'
```

Backend membuat notifikasi pemulihan Andi, waktu pulih, dan durasi gangguan. Kirim kembali file yang sama untuk memeriksa bahwa pemulihan tidak berulang.

Ketiga file status dikirim ke endpoint update; mengimpornya sebagai file pelanggan tidak menguji jalur gangguan otomatis. File dummy ini hanya untuk lingkungan lokal, bukan bukti kondisi MikroTik nyata.
