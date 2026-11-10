// Show whether connection states came from a recent physical-router snapshot.
(() => {
  const banner = document.createElement('aside');
  banner.setAttribute('role', 'status');
  banner.style.cssText = 'box-sizing:border-box;width:95%;margin:10px auto;padding:12px 18px;background:#f1f5f9;color:#334155;border:1px solid #cbd5e1;border-radius:12px;font:14px/1.6 system-ui,sans-serif;';
  const refresh = async () => {
    try {
      const response = await fetch('/api/router-health');
      if (!response.ok) return;
      const body = await response.json();
      if (body.integration !== 'routeros_api_v1') return;
      const labels = {samiran: 'Samiran', candipetak: 'Candipetak'};
      banner.textContent = 'Sumber data MikroTik: ' + Object.entries(body.routers).map(([key, value]) => {
        const time = value.last_success ? ' · terakhir berhasil ' + new Date(value.last_success).toLocaleString('id-ID') : '';
        return (labels[key] || key) + ': ' + value.status + time;
      }).join(' | ') + '. STALE/UNKNOWN berarti status koneksi belum terverifikasi terbaru; status terakhir dipertahankan.';
      if (!banner.isConnected) document.body.prepend(banner);
    } catch (_) { /* Existing dashboard stays available when the health endpoint is unavailable. */ }
  };
  refresh();
  setInterval(refresh, 60000);
})();
