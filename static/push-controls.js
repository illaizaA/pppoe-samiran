(async () => {
  const status = document.getElementById('push-status');
  const enable = document.getElementById('push-enable');
  const disable = document.getElementById('push-disable');
  const test = document.getElementById('push-test');
  const controls = [enable, disable, test];
  controls.forEach(button => button.disabled = true);
  let subscription = null;
  let active = false;
  let config;
  let deviceToken;
  const deviceHeaders = () => ({'X-Push-Device': deviceToken});
  const busy = () => controls.forEach(button => button.disabled = true);
  const refresh = () => {
    enable.disabled = active;
    disable.disabled = !subscription;
    test.disabled = !active;
    status.textContent = active ? 'Notifikasi aktif pada perangkat ini.' : `Belum aktif pada perangkat ini. Izin browser: ${Notification.permission}.`;
  };
  const request = async (url, method, payload) => {
    const response = await fetch(url, {method, headers: {...deviceHeaders(), 'Content-Type': 'application/json', 'X-CSRF-Token': config.csrf}, body: JSON.stringify(payload)});
    const body = await response.json();
    if (!response.ok) throw Error(body.error || (body.expired ? 'Subscription kedaluwarsa. Nonaktifkan lalu aktifkan kembali.' : 'Layanan push belum menerima pesan; coba lagi.'));
    return body;
  };
  try {
    deviceToken = localStorage.getItem('jss-push-device');
    if (!deviceToken || !/^[A-Za-z0-9_-]{43}$/.test(deviceToken)) {
      const bytes = crypto.getRandomValues(new Uint8Array(32));
      deviceToken = btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
      localStorage.setItem('jss-push-device', deviceToken);
    }
    const response = await fetch('/api/push/config', {headers: deviceHeaders()});
    if (!response.ok) throw Error('Gagal memuat konfigurasi perangkat.');
    config = await response.json();
    document.getElementById('push-monitoring-status').textContent = config.liveMonitoring ? 'Deteksi gangguan: token MikroTik sudah dikonfigurasi.' : 'Deteksi gangguan belum aktif: token MikroTik belum dikonfigurasi. Uji perangkat tetap bisa digunakan.';
    if (!window.isSecureContext || !('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) throw Error('Gunakan http://localhost:5081 pada komputer ini atau HTTPS; browser harus mendukung Web Push.');
    if (!config.configured) throw Error('Konfigurasi VAPID belum lengkap. Jalankan setup notifikasi pada server.');
    const registration = await navigator.serviceWorker.register('/push-sw.js');
    await navigator.serviceWorker.ready;
    subscription = await registration.pushManager.getSubscription();
    active = !!subscription && config.endpoints.includes(subscription.endpoint);
    refresh();
    enable.onclick = async () => {
      busy();
      try {
        if (await Notification.requestPermission() !== 'granted') throw Error('Izin ditolak. Ubah izin notifikasi pada pengaturan browser.');
        const key = config.publicKey.replace(/-/g, '+').replace(/_/g, '/');
        const bytes = Uint8Array.from(atob(key + '='.repeat((4 - key.length % 4) % 4)), c => c.charCodeAt(0));
        subscription = subscription || await registration.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: bytes});
        await request('/api/push/subscription', 'POST', subscription.toJSON());
        active = true;
        refresh();
      } catch (error) {refresh(); status.textContent = error.message;}
    };
    disable.onclick = async () => {
      busy();
      try {
        await request('/api/push/subscription', 'DELETE', subscription.toJSON());
        active = false;
        if (!await subscription.unsubscribe()) throw Error('Server sudah menonaktifkan push; subscription browser tidak ditemukan. Muat ulang halaman.');
        subscription = null;
        refresh();
      } catch (error) {refresh(); status.textContent = error.message;}
    };
    test.onclick = async () => {
      busy();
      try {
        await request('/api/push/test', 'POST', {endpoint: subscription.endpoint});
        refresh();
        status.textContent = 'Pesan uji diterima layanan push. Periksa notifikasi Windows/HP; penerimaan layanan belum membuktikan tampil di perangkat.';
      } catch (error) {refresh(); status.textContent = error.message;}
    };
  } catch (error) {status.textContent = error.message;}
})();
