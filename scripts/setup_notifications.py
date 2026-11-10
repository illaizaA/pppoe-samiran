"""Create persistent local push credentials; never print private keys/passwords."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import tempfile

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

PROJECT = Path(__file__).resolve().parents[1]


def setup(directory, subject):
    directory = directory.resolve()
    if directory == PROJECT or PROJECT in directory.parents:
        raise ValueError('Pilih penyimpanan rahasia di luar folder proyek.')
    directory.mkdir(parents=True, exist_ok=True)
    config_path = directory / 'notifications.json'
    if config_path.exists():
        # Preserve VAPID keys, accounts, and subscriptions across repeated setup.
        values = json.loads(config_path.read_text(encoding='utf-8'))
        if not Path(values['VAPID_PRIVATE_KEY']).is_file():
            raise ValueError('Private key hilang. Pulihkan backup; jangan rotasi tanpa subscription ulang.')
    else:
        key = ec.generate_private_key(ec.SECP256R1())
        private_path = directory / 'vapid-private.pem'
        with private_path.open('xb') as handle:
            handle.write(key.private_bytes(serialization.Encoding.PEM,
                         serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        os.chmod(private_path, 0o600)
        public = key.public_key().public_bytes(serialization.Encoding.X962,
                                               serialization.PublicFormat.UncompressedPoint)
        values = {
            'SECRET_KEY': secrets.token_urlsafe(48),
            'VAPID_PUBLIC_KEY': base64.urlsafe_b64encode(public).decode().rstrip('='),
            'VAPID_PRIVATE_KEY': str(private_path), 'VAPID_SUBJECT': subject,
            'PUBLIC_BASE_URL': 'http://localhost:5081', 'PORT': '5081',
            'MIKROTIK_API_TOKEN': secrets.token_urlsafe(32),
        }
        config_path.write_text(json.dumps(values, indent=2), encoding='utf-8')
        os.chmod(config_path, 0o600)
    if not values.get('MIKROTIK_API_TOKEN'):
        values['MIKROTIK_API_TOKEN'] = secrets.token_urlsafe(32)
        config_path.write_text(json.dumps(values, indent=2), encoding='utf-8')
    (directory / 'TOKEN-MIKROTIK.txt').write_text(values['MIKROTIK_API_TOKEN'], encoding='utf-8')
    os.chmod(directory / 'TOKEN-MIKROTIK.txt', 0o600)
    (PROJECT / '.local-config-path').write_text(str(config_path), encoding='utf-8')
    return config_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path,
                        default=Path(tempfile.gettempdir()) / 'jss-monitoring-local-secrets')
    parser.add_argument('--subject', default='mailto:admin@localhost')
    args = parser.parse_args()
    config = setup(args.directory, args.subject)
    print(f'Konfigurasi siap: {config}')
    print('Jalankan: python app.py; buka http://localhost:5081/notifications')
