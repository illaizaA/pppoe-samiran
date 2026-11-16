"""Generate fresh Web Push credentials and write them into the project .env."""
import argparse
import base64
import os
from pathlib import Path
import re
import secrets
import tempfile
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


PROJECT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT / '.env'
PRIVATE_KEY_FILE = PROJECT / 'runtime' / 'secrets' / 'vapid_private.pem'


def env_value(text, name):
    pattern = re.compile(r'^\s*(?:export\s+)?' + re.escape(name) + r'\s*=\s*(.*?)\s*$', re.M)
    matches = pattern.findall(text)
    if not matches:
        return ''
    value = matches[-1].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value.split(' #', 1)[0].strip()


def put_env_values(text, values):
    lines = text.splitlines()
    found = set()
    output = []
    pattern = re.compile(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=')
    for line in lines:
        match = pattern.match(line)
        name = match.group(1) if match else None
        if name in values:
            output.append(f'{name}={values[name]}')
            found.add(name)
        else:
            output.append(line)
    if output and output[-1].strip():
        output.append('')
    for name, value in values.items():
        if name not in found:
            output.append(f'{name}={value}')
    return '\n'.join(output).rstrip() + '\n'


def validate_subject(subject):
    if not isinstance(subject, str) or '\n' in subject or '\r' in subject:
        raise ValueError('VAPID subject harus berupa mailto:email atau URL HTTPS.')
    if subject.startswith('mailto:') and subject[7:].strip():
        return
    parsed = urlparse(subject)
    if parsed.scheme == 'https' and parsed.hostname:
        return
    raise ValueError('VAPID subject harus berupa mailto:email atau URL HTTPS.')


def atomic_write(path, content, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile('wb', dir=path.parent, prefix='.setup-', delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def setup(subject, force=False):
    validate_subject(subject)
    current_env = ENV_FILE.read_text(encoding='utf-8') if ENV_FILE.exists() else ''
    existing_key_values = (
        env_value(current_env, 'VAPID_PUBLIC_KEY'),
        env_value(current_env, 'VAPID_PRIVATE_KEY_FILE'),
        env_value(current_env, 'VAPID_PRIVATE_KEY'),
    )
    if not force and (any(existing_key_values) or PRIVATE_KEY_FILE.exists()):
        raise ValueError(
            'VAPID key sudah ada. Setup dihentikan agar subscription tidak rusak. '
            'Gunakan --force hanya jika memang ingin merotasi pasangan key.'
        )

    key = ec.generate_private_key(ec.SECP256R1())
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_bytes = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    public_key = base64.urlsafe_b64encode(public_bytes).decode('ascii').rstrip('=')

    values = {
        'VAPID_PUBLIC_KEY': public_key,
        'VAPID_PRIVATE_KEY_FILE': PRIVATE_KEY_FILE.relative_to(PROJECT).as_posix(),
        'VAPID_SUBJECT': subject,
    }
    if not env_value(current_env, 'SECRET_KEY'):
        values['SECRET_KEY'] = secrets.token_urlsafe(48)

    # Keep the private key out of the repository's tracked source and write it
    # before the .env points to it. The .env and PEM are both ignored locally.
    atomic_write(PRIVATE_KEY_FILE, private_pem)
    updated_env = put_env_values(current_env, values)
    atomic_write(ENV_FILE, updated_env.encode('utf-8'))
    return values


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subject', required=True,
                        help='Kontak VAPID, contoh mailto:admin@domainanda.com')
    parser.add_argument('--force', action='store_true',
                        help='Rotasi pasangan VAPID yang sudah ada; perangkat perlu didaftarkan ulang')
    args = parser.parse_args()
    try:
        result = setup(args.subject, force=args.force)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f".env diperbarui: {ENV_FILE}")
    print(f"Private key tersimpan: {result['VAPID_PRIVATE_KEY_FILE']} (jangan dibagikan)")
    print(f"VAPID_PUBLIC_KEY={result['VAPID_PUBLIC_KEY']}")
    print(f"VAPID_SUBJECT={result['VAPID_SUBJECT']}")
    print('Jalankan ulang server Flask, lalu aktifkan notifikasi dari halaman /notifications.')
