"""Device-scoped push delivery without login, and persistent live incidents."""
import json
import os
import secrets
import base64
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, quote
from flask import request, session, jsonify, redirect


def init_notifications(app, root, read, write, lock, notify, load_customers):
    subscriptions_file = root / 'push_subscriptions.json'
    states_file = root / 'connection_incidents.json'

    def device_id():
        token = request.headers.get('X-Push-Device', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            return None
        return hashlib.sha256(token.encode()).hexdigest()

    def csrf():
        return bool(device_id()) and secrets.compare_digest(
            request.headers.get('X-CSRF-Token', ''), session.get('push_csrf', '!'))

    def configured():
        return all(os.environ.get(k) for k in ('VAPID_PRIVATE_KEY', 'VAPID_PUBLIC_KEY', 'VAPID_SUBJECT'))

    @app.route('/technician/login')
    def legacy_login():
        return redirect('/notifications')

    @app.route('/api/push/config')
    def push_config():
        if not device_id():
            return jsonify(error='Identitas perangkat belum tersedia'), 400
        session.setdefault('push_csrf', secrets.token_urlsafe(32))
        return jsonify(publicKey=os.environ.get('VAPID_PUBLIC_KEY', ''), configured=configured(), csrf=session['push_csrf'], endpoints=[r['subscription']['endpoint'] for r in read(subscriptions_file, []) if r.get('device_id') == device_id()], liveMonitoring=bool(os.environ.get('MIKROTIK_API_TOKEN')))

    @app.route('/api/push/subscription', methods=['POST', 'DELETE'])
    def push_subscription():
        if not csrf():
            return jsonify(error='Identitas perangkat atau CSRF tidak valid'), 403
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error='Body harus objek JSON'), 400
        endpoint = payload.get('endpoint', '')
        if not isinstance(endpoint, str) or len(endpoint) > 4096:
            return jsonify(error='Endpoint tidak valid'), 400
        try:
            parsed = urlparse(endpoint)
        except ValueError:
            return jsonify(error='Endpoint tidak valid'), 400
        # Only browser push services; prevent server-side requests to arbitrary hosts.
        host = parsed.hostname or ''
        if parsed.scheme != 'https' or parsed.netloc != host or parsed.username or not (
            host in ('fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com')
            or host.endswith('.notify.windows.com') or host.endswith('.push.apple.com')
        ):
            return jsonify(error='Endpoint push tidak didukung'), 400
        with lock:
            if request.method == 'POST' and not configured():
                return jsonify(error='VAPID belum lengkap'), 503
            rows = read(subscriptions_file, [])
            owner = next((r for r in rows if r['subscription']['endpoint'] == endpoint), None)
            if owner and owner.get('device_id') != device_id():
                # Legacy subscriptions may migrate only with possession of both keys.
                if owner.get('device_id') or owner['subscription'].get('keys') != payload.get('keys'):
                    return jsonify(error='Subscription milik perangkat lain'), 409
            rows = [r for r in rows if r['subscription']['endpoint'] != endpoint]
            if request.method == 'POST':
                keys = payload.get('keys', {})
                if not isinstance(keys, dict) or not all(isinstance(keys.get(k), str) and 10 < len(keys[k]) < 200 for k in ('auth', 'p256dh')):
                    return jsonify(error='Kunci subscription tidak valid'), 400
                try:
                    from cryptography.hazmat.primitives.asymmetric import ec
                    decode = lambda value: base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
                    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), decode(keys['p256dh']))
                    if len(decode(keys['auth'])) != 16:
                        raise ValueError('Invalid auth length')
                except (ValueError, TypeError):
                    return jsonify(error='Kunci subscription tidak valid'), 400
                rows.append({'device_id': device_id(), 'subscription': {'endpoint': endpoint, 'keys': keys}})
            write(subscriptions_file, rows)
        return jsonify(success=True)

    @app.route('/push-sw.js')
    def push_worker():
        return app.send_static_file('push-sw.js'), 200, {'Cache-Control': 'no-cache', 'Service-Worker-Allowed': '/'}

    @app.route('/api/push/test', methods=['POST'])
    def push_test():
        if not csrf():
            return jsonify(error='Identitas perangkat atau CSRF tidak valid'), 403
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error='Body harus objek JSON'), 400
        selected = [r for r in read(subscriptions_file, []) if
                    r.get('device_id') == device_id() and
                    r['subscription']['endpoint'] == payload.get('endpoint')]
        if not selected:
            return jsonify(error='Subscription belum terdaftar pada perangkat ini'), 404
        result = deliver({'id': 'test-' + secrets.token_hex(6),
                          'message': 'Notifikasi uji perangkat Monitoring JSS.'}, None,
                         'Monitoring JSS - Uji Notifikasi', '/notifications', selected)
        return jsonify(**result), 200 if result['sent'] else 502

    def deliver(notification, router, title, url, selected=None):
        result = {'sent': 0, 'failed': 0, 'expired': 0}
        if not configured():
            return dict(result, error='VAPID belum lengkap')
        try:
            from pywebpush import webpush, WebPushException
        except ImportError:
            return dict(result, error='pywebpush belum terpasang')
        for row in (read(subscriptions_file, []) if selected is None else selected):
            if selected is None and not row.get('device_id'):
                continue
            try:
                webpush(subscription_info=row['subscription'], data=json.dumps({
                    'title': title, 'body': notification['message'], 'url': url,
                    'tag': 'jss-' + str(notification['id'])}),
                    vapid_private_key=os.environ['VAPID_PRIVATE_KEY'],
                    vapid_claims={'sub': os.environ['VAPID_SUBJECT']}, timeout=5)
                result['sent'] += 1
            except WebPushException as exc:
                result['failed'] += 1
                if exc.response is not None and exc.response.status_code in (404, 410):
                    result['expired'] += 1
                    with lock:
                        rows = read(subscriptions_file, [])
                        write(subscriptions_file, [r for r in rows if
                              r['subscription']['endpoint'] != row['subscription']['endpoint']])
                else:
                    app.logger.warning('Pengiriman push perangkat gagal')
            except Exception:
                result['failed'] += 1
                app.logger.exception('Konfigurasi/pengiriman push gagal')
        return result

    def observe(router, incoming, now=None):
        now = now or datetime.now(timezone.utc)
        states = read(states_file, {})
        metadata = {str(r.get('user', '')).casefold(): r for r in load_customers() if r.get('router') == router}
        seen = set()
        for row in incoming:
            username = str(row.get('user', '')).strip()
            status = str(row.get('status', '')).upper()
            if not username or status not in ('ONLINE', 'OFFLINE'):
                continue
            key = json.dumps([router, username.casefold()])
            if key in seen:
                continue
            seen.add(key)
            state = states.get(key)
            if state is None:
                states[key] = {'status': status, 'last_seen': now.isoformat()}
                continue
            gap = (now - datetime.fromisoformat(state['last_seen'])).total_seconds()
            if gap < 0:
                continue
            if gap > int(os.environ.get('LIVE_SAMPLE_MAX_GAP_SECONDS', '360')) and not state.get('alerted'):
                state.pop('since', None)
                state['status'] = status
            meta = metadata.get(username.casefold(), {})
            name = meta.get('nama_asli') or username
            location = meta.get('lokasi') or '-'
            url = '/edit/' + quote(username, safe='')
            if status == 'OFFLINE':
                if state['status'] == 'ONLINE' or state.pop('pending_reset', False):
                    state['since'] = now.isoformat()
                if state.get('since') and not state.get('alerted') and (now - datetime.fromisoformat(state['since'])).total_seconds() >= 180:
                    notify(f'Gangguan: {name} ({username}), wilayah {location}. OFFLINE sejak {state["since"]}.', 'warning', meta.get('id'), username, router=router, title='Monitoring JSS — Pelanggan OFFLINE', target_url=url)
                    state['alerted'] = True
            elif state.get('since'):
                if state.get('alerted'):
                    duration = int((now - datetime.fromisoformat(state['since'])).total_seconds())
                    notify(f'Pulih: {name} ({username}), wilayah {location}. ONLINE pada {now.isoformat()}; durasi gangguan {duration} detik.', 'success', meta.get('id'), username, router=router, title='Monitoring JSS — Pelanggan ONLINE', target_url=url)
                    state['recovered_at'] = now.isoformat()
                    state['duration_seconds'] = duration
                state.pop('since', None)
                state.pop('alerted', None)
            if status == 'ONLINE':
                state.pop('pending_reset', None)
            state['status'] = status
            state['last_seen'] = now.isoformat()
        write(states_file, states)

    return deliver, observe
