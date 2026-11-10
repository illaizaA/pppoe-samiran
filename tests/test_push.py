import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from flask import Flask
from threading import RLock
from notification_push import init_notifications

class IncidentTests(unittest.TestCase):
    def test_confirm_deduplicate_recover_and_ignore_import(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            def read(path, default):
                return json.loads(path.read_text()) if path.exists() else default
            def write(path, value):
                path.write_text(json.dumps(value))
            events = []
            def notify(*args, **kwargs):
                events.append((args, kwargs))
            _, observe = init_notifications(Flask(__name__), Path(directory), read, write, RLock(), notify, lambda: [])
            start = datetime.now(timezone.utc)
            def sample(status, seconds):
                observe('R', [{'user': 'u', 'status': status}], start + timedelta(seconds=seconds))
            sample('OFFLINE', 0)
            sample('OFFLINE', 190)
            self.assertEqual(events, [])
            sample('ONLINE', 200)
            sample('OFFLINE', 210)
            sample('OFFLINE', 389)
            self.assertEqual(events, [])
            sample('OFFLINE', 390)
            sample('OFFLINE', 400)
            self.assertEqual(len(events), 1)
            sample('ONLINE', 450)
            sample('ONLINE', 460)
            self.assertEqual(len(events), 2)
            self.assertIn('240 detik', events[-1][0][0])
            sample('OFFLINE', 470)
            sample('OFFLINE', 1000)
            self.assertEqual(len(events), 2)

import base64
import json
import os
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import secrets

class PushDeviceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.env = patch.dict(os.environ, {
            'SECRET_KEY': 'test-secret', 'VAPID_PUBLIC_KEY': 'public',
            'VAPID_PRIVATE_KEY': 'private', 'VAPID_SUBJECT': 'mailto:test@example.com',
            })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.app = Flask(__name__)
        self.app.secret_key = 'test-secret'
        self.app.testing = True
        self.app.template_folder = str(Path(__file__).resolve().parents[1] / 'templates')
        self.client = self.app.test_client()
        def read(path, default):
            return json.loads(path.read_text()) if path.exists() else default
        def write(path, value):
            path.write_text(json.dumps(value))
        self.deliver, self.observe = init_notifications(self.app, self.root, read, write, RLock(), lambda *a, **k: None, lambda: [])
        key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip('=')
        self.sub = {'endpoint': 'https://fcm.googleapis.com/fcm/send/test', 'keys': {'p256dh': encode(key), 'auth': encode(b'0123456789abcdef')}}

    def prepare_device(self):
        token = secrets.token_urlsafe(32)
        self.headers = {'X-Push-Device': token}
        response = self.client.get('/api/push/config', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.headers['X-CSRF-Token'] = response.get_json()['csrf']

    def subscribe(self):
        return self.client.post('/api/push/subscription', json=self.sub, headers=self.headers)

    def test_no_login_csrf_and_subscription_validation(self):
        self.assertEqual(self.client.get('/api/push/config').status_code, 400)
        self.assertEqual(self.client.post('/api/push/subscription', json=self.sub).status_code, 403)
        self.prepare_device()
        self.assertEqual(self.client.post('/api/push/subscription', json=self.sub).status_code, 403)
        for value in ([], 'not-json', {'endpoint': 'http://127.0.0.1:5000'}, {'endpoint': 'https://[bad'}):
            self.assertEqual(self.client.post('/api/push/subscription', json=value, headers=self.headers).status_code, 400)
        self.assertEqual(self.subscribe().status_code, 200)
        self.assertEqual(self.subscribe().status_code, 200)
        rows = json.loads((self.root / 'push_subscriptions.json').read_text())
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['device_id'])
        self.assertNotIn('account', rows[0])
        config = self.client.get('/api/push/config', headers=self.headers).get_json()
        self.assertNotIn('private', json.dumps(config))
        self.assertEqual(self.client.get('/technician/login').status_code, 302)

    def test_all_routers_and_device_owner(self):
        self.prepare_device()
        self.subscribe()
        with patch('pywebpush.webpush') as send:
            self.assertEqual(self.deliver({'id': 1, 'message': 'hello'}, 'R2', 'title', '/notifications')['sent'], 1)
            send.assert_called_once()
            send.reset_mock()
            self.assertEqual(self.deliver({'id': 1, 'message': 'hello'}, 'R1', 'title', '/notifications')['sent'], 1)
            send.assert_called_once()
        self.prepare_device()
        self.assertEqual(self.subscribe().status_code, 409)
        self.assertEqual(self.client.post('/api/push/test', json={'endpoint': self.sub['endpoint']}, headers=self.headers).status_code, 404)
        self.assertEqual(self.client.delete('/api/push/subscription', json=self.sub, headers=self.headers).status_code, 409)

    def test_test_delivery_expiry_and_unsubscribe(self):
        from pywebpush import WebPushException
        from requests import Response
        self.prepare_device()
        self.subscribe()
        with patch('pywebpush.webpush') as send:
            response = self.client.post('/api/push/test', json={'endpoint': self.sub['endpoint']}, headers=self.headers)
            self.assertEqual(response.get_json()['sent'], 1)
            send.assert_called_once()
        failed = Response()
        failed.status_code = 410
        with patch('pywebpush.webpush', side_effect=WebPushException('gone', response=failed)):
            result = self.deliver({'id': 1, 'message': 'hello'}, 'R1', 'title', '/notifications')
            self.assertEqual(result['expired'], 1)
        self.assertEqual(json.loads((self.root / 'push_subscriptions.json').read_text()), [])
        self.subscribe()
        self.assertEqual(self.client.delete('/api/push/subscription', json=self.sub, headers=self.headers).status_code, 200)
        self.assertEqual(json.loads((self.root / 'push_subscriptions.json').read_text()), [])

    def test_transient_failure_preserves_subscription(self):
        from pywebpush import WebPushException
        from requests import Response
        self.prepare_device()
        self.subscribe()
        failed = Response()
        failed.status_code = 503
        with patch('pywebpush.webpush', side_effect=WebPushException('unavailable', response=failed)):
            result = self.deliver({'id': 1, 'message': 'hello'}, 'R1', 'title', '/notifications')
            self.assertEqual(result['failed'], 1)
            self.assertEqual(result['expired'], 0)
        self.assertEqual(len(json.loads((self.root / 'push_subscriptions.json').read_text())), 1)

if __name__ == '__main__':
    unittest.main()
