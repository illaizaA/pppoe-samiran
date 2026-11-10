"""Read-only RouterOS snapshots. No API traffic before service confirmation."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
import json
import os
from pathlib import Path
import socket
import ssl
import tempfile


class RouterError(Exception):
    """Safe error text, never raw API arguments/credentials."""


@dataclass(frozen=True)
class RouterConfig:
    key: str
    host: str
    port: int
    name: str
    username: str = 'monitoring'
    password: str = field(default='', repr=False)
    transport: str = 'unknown'
    confirmed: bool = False
    secure_network: bool = False
    allow_plaintext: bool = False
    ca_file: str = ''
    tls_name: str = ''
    timeout: float = 5

    @classmethod
    def from_env(cls, key):
        defaults = {
            'samiran': ('202.169.238.26', '6100', 'ROUTER SAMIRAN-NGAGLIK'),
            'candipetak': ('111.92.166.99', '8101', 'ROUTER CANDI'),
        }
        host, port, name = defaults[key]
        prefix = 'MIKROTIK_' + key.upper() + '_'
        get = lambda name, default='': os.environ.get(prefix + name, default).strip()
        return cls(key=key, host=get('HOST', host), port=int(get('PORT', port)),
                   name=get('NAME', name), username=get('USERNAME', 'monitoring'),
                   password=os.environ.get(prefix + 'PASSWORD', ''),
                   transport=get('TRANSPORT', 'unknown').lower(),
                   confirmed=get('SERVICE_CONFIRMED', 'false').lower() == 'true',
                   secure_network=get('SECURE_NETWORK', 'false').lower() == 'true',
                   ca_file=get('CA_FILE'), tls_name=get('TLS_SERVER_NAME'),
                   timeout=float(os.environ.get('MIKROTIK_TIMEOUT_SECONDS', '5')))


def probe(config):
    """TCP + passive banner only. No login, TLS, Winbox, or API command sent."""
    result = {'router': config.key, 'host': config.host, 'port': config.port,
              'protocol': 'UNCONFIRMED', 'api_authenticated': False}
    try:
        with socket.create_connection((config.host, config.port), timeout=config.timeout) as conn:
            result['tcp'] = 'OPEN'
            conn.settimeout(min(config.timeout, 1))
            try:
                result['passive_bytes'] = len(conn.recv(128))
            except socket.timeout:
                result['passive_bytes'] = 0
    except OSError as error:
        result.update(tcp='FAILED', error=type(error).__name__, errno=error.errno)
    result['message'] = 'TCP bukan bukti RouterOS API. Konfirmasikan service/port API-SSL atau API via VPN kepada teknisi.'
    return result


def _connection(config):
    if not config.confirmed or config.transport not in ('api', 'api-ssl'):
        raise RouterError('SERVICE_UNCONFIRMED: port belum dikonfirmasi sebagai RouterOS API/API-SSL; tidak mencoba autentikasi. Jika Winbox, minta port API kepada teknisi.')
    if config.username != 'monitoring':
        raise RouterError('CONFIG: gunakan akun monitoring read-only, bukan admin.')
    if not config.password:
        raise RouterError('CONFIG: password router belum diisi pada .env lokal.')
    if config.transport == 'api' and not config.secure_network and not config.allow_plaintext:
        raise RouterError('SECURITY: gunakan API-SSL/VPN, atau opsi --allow-plaintext jika memang memilih API biasa tanpa enkripsi.')
    from librouteros import connect
    kwargs = dict(host=config.host, port=config.port, username=config.username,
                  password=config.password, timeout=config.timeout, encoding='UTF-8')
    if config.transport == 'api-ssl':
        context = ssl.create_default_context(cafile=config.ca_file or None)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        kwargs['ssl_wrapper'] = partial(context.wrap_socket, server_hostname=config.tls_name or config.host)
    return connect(**kwargs)


def _read(api, command, fields):
    # Whitelist prevents this service from issuing configuration changes.
    allowed = {'/system/identity/print', '/ppp/secret/print', '/ppp/active/print'}
    if command not in allowed or 'password' in fields:
        raise RouterError('READ_ONLY: command/field ditolak.')
    rows = list(api(command, **{'.proplist': ','.join(fields)}))
    if any(not isinstance(row, dict) for row in rows):
        raise RouterError('INCOMPLETE: format respons router tidak valid.')
    return [{key: row[key] for key in fields if key in row} for row in rows]


def fetch_snapshot(config, connector=None):
    api = None
    phase = 'connect'
    try:
        api = (connector or _connection)(config)
        phase = 'read'
        identities = _read(api, '/system/identity/print', ('name',))
        if len(identities) != 1 or not identities[0].get('name'):
            raise RouterError('INCOMPLETE: identitas router tidak tersedia.')
        secrets = _read(api, '/ppp/secret/print', ('name', 'service'))
        active = _read(api, '/ppp/active/print', ('name', 'service', 'address', 'caller-id', 'uptime'))
        registered = set()
        for row in secrets:
            if not row.get('name') or row.get('service') not in ('any', 'pppoe'):
                if row.get('service') not in ('any', 'pppoe', None):
                    continue
                raise RouterError('INCOMPLETE: akun PPP tidak memiliki nama/service.')
            registered.add(str(row['name']))
        sessions = {}
        for row in active:
            if row.get('service') not in ('pppoe',):
                if row.get('service') is None:
                    raise RouterError('INCOMPLETE: sesi PPP tidak memiliki service.')
                continue
            if not row.get('name') or not row.get('address'):
                raise RouterError('INCOMPLETE: sesi PPPoE tanpa nama/IP.')
            # Multiple sessions for the same exact username still mean ONLINE.
            sessions.setdefault(str(row['name']), row)
        rows = []
        for username in sorted(registered | set(sessions)):
            session = sessions.get(username)
            rows.append({'user': username, 'status': 'ONLINE' if session else 'OFFLINE',
                         'ip': session.get('address', '-') if session else '-',
                         'mac': session.get('caller-id', '-') if session else '-',
                         'uptime': session.get('uptime', '-') if session else '-'})
        return {'router': config.name, 'router_key': config.key,
                'router_identity': identities[0]['name'], 'source': 'routeros_api',
                'snapshot_type': 'pppoe_accounts', 'snapshot_complete': True,
                'collected_at': datetime.now(timezone.utc).isoformat(), 'pppoe': rows}
    except RouterError:
        raise
    except ssl.SSLCertVerificationError:
        raise RouterError('TLS_CERTIFICATE: sertifikat/hostname tidak dipercaya. Atur CA_FILE/TLS_SERVER_NAME yang benar; verifikasi TLS tetap aktif.') from None
    except (socket.timeout, TimeoutError):
        raise RouterError('TIMEOUT: router tidak merespons sebelum batas waktu.') from None
    except OSError:
        raise RouterError('NETWORK_TLS: koneksi jaringan/TLS gagal; periksa port, firewall, VPN, CA dan sertifikat.') from None
    except Exception as error:
        # Do not expose exception contents: some libraries include request words.
        name = type(error).__name__
        if name in ('TrapError', 'MultiTrapError', 'FatalError'):
            if phase == 'connect':
                raise RouterError('AUTH: autentikasi API ditolak; periksa user/password serta hak API akun monitoring.') from None
            raise RouterError('READ_DENIED: pembacaan API ditolak/tidak lengkap; periksa hak read akun monitoring.') from None
        raise RouterError('PROTOCOL: respons bukan API yang valid atau library tidak tersedia; tidak mencoba protokol lain.') from None
    finally:
        if api is not None:
            try:
                api.close()
            except Exception:
                pass


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.' + path.name, suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
