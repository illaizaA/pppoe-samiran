"""Validate and map physical-router snapshots onto existing customer metadata."""
from collections import defaultdict
from datetime import datetime, timezone
import os


def utc(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Timestamp wajib menyertakan zona waktu.')
    return parsed.astimezone(timezone.utc)


def plan_snapshot(snapshot, current, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(snapshot, dict) or snapshot.get('source') != 'routeros_api':
        raise ValueError('Sumber snapshot tidak valid.')
    if snapshot.get('snapshot_type') != 'pppoe_accounts' or snapshot.get('snapshot_complete') is not True:
        raise ValueError('Hanya snapshot akun/sesi lengkap yang boleh diterapkan.')
    source = snapshot.get('router_key')
    if source not in ('samiran', 'candipetak') or not isinstance(snapshot.get('router_identity'), str) or not snapshot['router_identity'].strip():
        raise ValueError('Identitas sumber router tidak valid.')
    timestamp = snapshot.get('collected_at')
    try:
        age = (now - utc(timestamp)).total_seconds()
    except (ValueError, TypeError):
        raise ValueError('Waktu snapshot tidak valid.') from None
    if age < -30 or age > int(os.environ.get('MIKROTIK_SNAPSHOT_MAX_AGE_SECONDS', '180')):
        raise ValueError('Snapshot kedaluwarsa/berasal dari waktu mendatang; tarik ulang data router.')
    rows = snapshot.get('pppoe')
    if not isinstance(rows, list):
        raise ValueError('pppoe wajib berupa array.')
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Baris snapshot tidak valid.')
        name = row.get('user')
        if not isinstance(name, str) or not name.strip() or name != name.strip() or name in seen:
            raise ValueError('Username kosong/ganda pada snapshot.')
        seen.add(name)
        if row.get('status') not in ('ONLINE', 'OFFLINE') or any(k in row for k in ('password', 'secret')):
            raise ValueError('Status tidak valid atau snapshot berisi field rahasia.')
        if any(not isinstance(row.get(k, '-'), str) for k in ('ip', 'mac', 'uptime')):
            raise ValueError('Field koneksi wajib berupa string.')

    customers = [dict(row) for row in current]
    by_name = defaultdict(list)
    for index, row in enumerate(customers):
        by_name[str(row.get('user') or '').strip()].append(index)
    matched, unmatched, conflicts = [], [], []
    for live in rows:
        candidates = by_name.get(live['user'], [])
        if not candidates:
            unmatched.append(live['user'])
            continue
        # Imported router names are area groups. Never rename them to the physical router.
        if len(candidates) != 1:
            conflicts.append(live['user'])
            continue
        index = candidates[0]
        previous = customers[index]
        if previous.get('source_router_key') not in (None, '', source):
            conflicts.append(live['user'])
            continue
        if previous.get('last_live_update') and utc(previous['last_live_update']) >= utc(timestamp):
            raise ValueError('Snapshot lebih lama/sama dengan data terakhir; tarik ulang router.')
        previous.update({k: live.get(k, '-') for k in ('status', 'ip', 'mac', 'uptime')})
        previous.update(source_router_key=source, source_router_identity=snapshot['router_identity'],
                        last_live_update=timestamp, data_quality='FRESH')
        matched.append(previous)
    missing = []
    for row in customers:
        if row.get('source_router_key') == source and row.get('user') not in seen:
            # Account absent from secrets is not proof of a connection failure.
            row['data_quality'] = 'UNKNOWN'
            missing.append(row.get('user'))
    return {'customers': customers, 'matched_rows': matched,
            'report': {'router_key': source, 'snapshot_accounts': len(rows),
                       'updated': len(matched), 'not_imported': len(unmatched),
                       'conflicts': len(conflicts), 'missing_owned': len(missing),
                       'online': sum(r['status'] == 'ONLINE' for r in matched),
                       'offline': sum(r['status'] == 'OFFLINE' for r in matched)}}


def freshness(customers, health, now=None):
    now = now or datetime.now(timezone.utc)
    limit = int(os.environ.get('MIKROTIK_STALE_SECONDS', '180'))
    result = []
    for original in customers:
        row = dict(original)
        source = row.get('source_router_key')
        if source:
            state = health.get(source, {})
            try:
                stale = (now - utc(row['last_live_update'])).total_seconds() > limit
            except (ValueError, KeyError, TypeError):
                stale = True
            if stale or state.get('status') == 'STALE':
                row['data_quality'] = 'STALE'
        else:
            row['data_quality'] = 'UNKNOWN'
        result.append(row)
    return result
