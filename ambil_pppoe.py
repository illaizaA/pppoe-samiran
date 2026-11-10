"""Ambil snapshot read-only tanpa mengubah database monitoring."""
import argparse
from dataclasses import replace
from pathlib import Path
import os
import time

import requests
from filelock import FileLock, Timeout

from local_config import load_config
from mikrotik_service import RouterConfig, RouterError, fetch_snapshot, atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('router', choices=['samiran', 'candipetak'])
    parser.add_argument('--allow-plaintext', action='store_true',
                        help='Izinkan API biasa tanpa enkripsi sesuai pilihan operator; bukan menonaktifkan verifikasi TLS.')
    parser.add_argument('--sync', action='store_true', help='Perbarui pelanggan existing melalui backend website.')
    parser.add_argument('--watch', action='store_true', help='Ulangi polling pada interval .env; bukan scheduler di Flask.')
    parser.add_argument('--website-url', default=None, help='Default MIKROTIK_MONITOR_URL atau http://127.0.0.1:5081')
    args = parser.parse_args()
    load_config()
    root = Path(__file__).resolve().parent
    interval = float(os.environ.get('MIKROTIK_POLL_INTERVAL_SECONDS', '60'))
    if interval < 10:
        parser.error('Interval minimal 10 detik.')
    url = (args.website_url or os.environ.get('MIKROTIK_MONITOR_URL', 'http://127.0.0.1:5081')).rstrip('/')
    (root / 'runtime').mkdir(exist_ok=True)
    try:
        with FileLock(str(root / 'runtime' / 'mikrotik-poller.lock'), timeout=0):
            while True:
                started = time.monotonic()
                code = collect(args, url)
                if not args.watch:
                    return code
                time.sleep(max(1, interval - (time.monotonic() - started)))
    except Timeout:
        print('Poller lain sedang berjalan. Hentikan poller tersebut sebelum menjalankan manual.')
        return 1
    except KeyboardInterrupt:
        print('Polling dihentikan.')
        return 0


def collect(args, url):
    headers = {'X-API-Token': os.environ.get('MIKROTIK_API_TOKEN', '')}
    if args.sync:
        if not headers['X-API-Token']:
            print('Gagal: MIKROTIK_API_TOKEN backend belum dikonfigurasi.')
            return 1
        try:
            capabilities = requests.get(url + '/api/router-health', timeout=10)
            if capabilities.status_code != 200 or capabilities.json().get('integration') != 'routeros_api_v1':
                print('Gagal: backend belum mendukung pemetaan sumber router. Restart Flask dengan kode terbaru.')
                return 1
        except (requests.RequestException, ValueError):
            print('Gagal: website tidak dapat diakses. Jalankan/restart Flask dan periksa --website-url.')
            return 1
    try:
        config = RouterConfig.from_env(args.router)
        config = replace(config, allow_plaintext=args.allow_plaintext)
        print(f'Membaca PPPoE {args.router} melalui {config.host}:{config.port} (read-only)...')
        snapshot = fetch_snapshot(config)
        output = Path(__file__).resolve().parent / 'hasil_json' / f'{args.router}_pppoe.json'
        atomic_json(output, snapshot)
    except RouterError as error:
        print(f'Gagal: {error}')
        if args.sync:
            try:
                requests.post(url + '/api/router-health', headers=headers,
                              json={'router_key': args.router, 'error_code': str(error).split(':', 1)[0]}, timeout=10)
            except requests.RequestException:
                print('Status kegagalan belum dapat disampaikan ke website.')
        return 1
    except (ValueError, OSError):
        print('Gagal: konfigurasi lokal atau penyimpanan JSON tidak valid/tidak dapat diakses.')
        return 1
    online = sum(row['status'] == 'ONLINE' for row in snapshot['pppoe'])
    print(f'Berhasil. ONLINE: {online}; OFFLINE: {len(snapshot["pppoe"]) - online}.')
    print(f'JSON: {output}')
    if args.sync:
        try:
            response = requests.post(url + '/api/update-pppoe', json=snapshot, headers=headers, timeout=60)
            if response.status_code != 200:
                print(f'Sinkronisasi ditolak backend (HTTP {response.status_code}); periksa konfigurasi atau waktu snapshot.')
                return 1
            report = response.json()['report']
            print(f'Website: {report["updated"]} pelanggan diperbarui; '
                  f'{report["not_imported"]} akun belum diimpor dilewati; '
                  f'{report["conflicts"]} konflik sumber dilewati.')
        except (requests.RequestException, ValueError, KeyError):
            print('Respons sinkronisasi tidak terkonfirmasi. Periksa dashboard sebelum mencoba lagi.')
            return 1
    else:
        print('Database website dan konfigurasi router tidak diubah. Gunakan --sync untuk memperbarui website.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
