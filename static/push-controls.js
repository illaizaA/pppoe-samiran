(async () => {
  const status = document.getElementById('push-status');
  const enable = document.getElementById('push-enable');
  const disable = document.getElementById('push-disable');
  const controls = [enable, disable];
  controls.forEach(button => button.disabled = true);

  let config = null;
  let deviceToken = null;
  let registration = null;
  let subscription = null;
  let active = false;
  let keyChanged = false;

  const deviceHeaders = () => ({'X-Push-Device': deviceToken});
  const busy = () => controls.forEach(button => button.disabled = true);
  const refresh = () => {
    enable.disabled = !config?.configured || active;
    disable.disabled = !subscription;
    if (keyChanged) {
      status.textContent = 'Pasangan VAPID berubah. Aktifkan ulang notifikasi pada perangkat ini.';
    } else {
      const permission = 'Notification' in window ? Notification.permission : 'belum diperiksa';
      status.textContent = active ? 'Notifikasi aktif pada perangkat ini.' : `Belum aktif pada perangkat ini. Izin browser: ${permission}.`;
    }
  };
  const checkBrowserSupport = () => {
    if (!window.isSecureContext) {
      throw Error('Notifikasi perangkat belum bisa digunakan melalui HTTP. Buka dashboard melalui HTTPS untuk mengaktifkannya. Histori notifikasi tetap bisa dilihat di halaman ini.');
    }
    if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
      throw Error('Browser ini belum mendukung notifikasi perangkat (Web Push).');
    }
  };
  const ensureDeviceToken = () => {
    deviceToken = localStorage.getItem('jss-push-device');
    if (!deviceToken || !/^[A-Za-z0-9_-]{43}$/.test(deviceToken)) {
      const bytes = crypto.getRandomValues(new Uint8Array(32));
      deviceToken = btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
      localStorage.setItem('jss-push-device', deviceToken);
    }
  };
  const initialize = async () => {
    checkBrowserSupport();
    if (!deviceToken) ensureDeviceToken();
    if (!config) {
      const response = await fetch('/api/push/config', {headers: deviceHeaders()});
      if (!response.ok) throw Error('Gagal memuat konfigurasi perangkat.');
      config = await response.json();
      document.getElementById('push-monitoring-status').textContent = config.liveMonitoring
        ? 'Deteksi gangguan: token MikroTik sudah dikonfigurasi.'
        : 'Deteksi gangguan belum aktif: token MikroTik belum dikonfigurasi.';
    }
    if (!config.configured) throw Error('Konfigurasi VAPID belum lengkap. Jalankan python scripts/setup_notifications.py pada server.');
    if (!registration) {
      registration = await navigator.serviceWorker.register('/push-sw.js');
      await navigator.serviceWorker.ready;
      subscription = await registration.pushManager.getSubscription();
      keyChanged = !!subscription && !subscriptionUsesCurrentKey(subscription);
      active = !!subscription && !keyChanged && config.endpoints.includes(subscription.endpoint);
    }
  };
  const request = async (url, method, payload) => {
    const response = await fetch(url, {
      method,
      headers: {...deviceHeaders(), 'Content-Type': 'application/json', 'X-CSRF-Token': config.csrf},
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) throw Error(body.error || (body.expired ? 'Subscription kedaluwarsa. Nonaktifkan lalu aktifkan kembali.' : 'Layanan push belum menerima pesan; coba lagi.'));
    return body;
  };
  const vapidBytes = () => {
    const key = config.publicKey.replace(/-/g, '+').replace(/_/g, '/');
    return Uint8Array.from(atob(key + '='.repeat((4 - key.length % 4) % 4)), c => c.charCodeAt(0));
  };
  const subscriptionUsesCurrentKey = value => {
    const actual = value?.options?.applicationServerKey;
    if (!actual) return false;
    const expected = vapidBytes();
    const bytes = new Uint8Array(actual);
    return bytes.length === expected.length && bytes.every((byte, index) => byte === expected[index]);
  };

  enable.onclick = async () => {
    busy();
    try {
      await initialize();
      if (await Notification.requestPermission() !== 'granted') throw Error('Izin ditolak. Ubah izin notifikasi pada pengaturan browser.');
      if (subscription && !subscriptionUsesCurrentKey(subscription)) {
        if (config.endpoints.includes(subscription.endpoint)) {
          await request('/api/push/subscription', 'DELETE', subscription.toJSON());
        }
        await subscription.unsubscribe();
        subscription = null;
      }
      subscription = subscription || await registration.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: vapidBytes()});
      await request('/api/push/subscription', 'POST', subscription.toJSON());
      keyChanged = false;
      active = true;
      refresh();
    } catch (error) {
      refresh();
      status.textContent = error.message;
    }
  };

  disable.onclick = async () => {
    busy();
    try {
      await initialize();
      if (config.endpoints.includes(subscription.endpoint)) {
        await request('/api/push/subscription', 'DELETE', subscription.toJSON());
      }
      active = false;
      if (!await subscription.unsubscribe()) throw Error('Server sudah menonaktifkan push; subscription browser tidak ditemukan. Muat ulang halaman.');
      subscription = null;
      keyChanged = false;
      refresh();
    } catch (error) {
      refresh();
      status.textContent = error.message;
    }
  };

  try {
    await initialize();
    refresh();
  } catch (error) {
    refresh();
    status.textContent = error.message;
  }
})();
