import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from live_snapshot import plan_snapshot, freshness
from mikrotik_service import RouterConfig, RouterError, fetch_snapshot, atomic_json, _connection


class SnapshotMappingTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.customers = [
            {'user': 'area-a', 'router': 'AREA A', 'nama_asli': 'Nama A', 'lokasi': 'Alamat A',
             'latitude': -7.1, 'longitude': 110.1, 'profile': '10M', 'status': 'OFFLINE'},
            {'user': 'area-b', 'router': 'AREA B', 'status': 'ONLINE'},
            {'user': 'missing', 'router': 'AREA B', 'status': 'ONLINE'}]
        self.snapshot = {'source': 'routeros_api', 'router_key': 'samiran',
                         'router_identity': 'SAMIRAN', 'snapshot_complete': True,
                         'snapshot_type': 'pppoe_accounts', 'collected_at': self.now.isoformat(),
                         'pppoe': [{'user': 'area-a', 'status': 'ONLINE', 'ip': '192.0.2.1', 'uptime': '1m', 'mac': 'AA'},
                                   {'user': 'area-b', 'status': 'OFFLINE'},
                                   {'user': 'not-imported', 'status': 'OFFLINE'}]}

    def test_preserves_metadata_groups_and_missing_customers(self):
        original = copy.deepcopy(self.customers)
        plan = plan_snapshot(self.snapshot, self.customers, self.now)
        self.assertEqual(plan['report']['updated'], 2)
        self.assertEqual(plan['report']['not_imported'], 1)
        self.assertEqual(len(plan['customers']), 3)
        a = plan['customers'][0]
        for key in ('router', 'latitude', 'longitude', 'nama_asli', 'lokasi', 'profile'):
            self.assertEqual(a[key], original[0][key])
        self.assertEqual(a['source_router_key'], 'samiran')
        self.assertEqual(a['status'], 'ONLINE')
        self.assertEqual(plan['customers'][2]['status'], 'ONLINE')
        self.assertEqual(self.customers, original)

    def test_rejects_partial_old_invalid_duplicate_and_secret_data(self):
        for change in (
            {'snapshot_complete': False}, {'snapshot_type': 'partial'},
            {'collected_at': (self.now - timedelta(minutes=10)).isoformat()},
            {'pppoe': [{'user': 'area-a', 'status': 'BROKEN'}]},
            {'pppoe': [{'user': 'area-a', 'status': 'ONLINE', 'password': 'must-not-persist'}]},
            {'pppoe': [{'user': 'area-a', 'status': 'ONLINE'}] * 2},
        ):
            with self.subTest(change=tuple(change)), self.assertRaises(ValueError):
                plan_snapshot(dict(self.snapshot, **change), self.customers, self.now)

    def test_second_source_cannot_overwrite_owned_customers(self):
        first = plan_snapshot(self.snapshot, self.customers, self.now)['customers']
        next_snapshot = dict(self.snapshot, router_key='candipetak', collected_at=(self.now + timedelta(seconds=60)).isoformat())
        plan = plan_snapshot(next_snapshot, first, self.now + timedelta(seconds=60))
        self.assertEqual(plan['report']['conflicts'], 2)
        self.assertEqual(plan['report']['updated'], 0)
        self.assertEqual(plan['customers'][0]['source_router_key'], 'samiran')

    def test_empty_complete_snapshot_and_stale_do_not_invent_offline(self):
        first = plan_snapshot(self.snapshot, self.customers, self.now)['customers']
        stamp = self.now + timedelta(seconds=60)
        empty = dict(self.snapshot, pppoe=[], collected_at=stamp.isoformat())
        plan = plan_snapshot(empty, first, stamp)
        self.assertEqual(plan['customers'][0]['status'], 'ONLINE')
        self.assertEqual(plan['customers'][0]['data_quality'], 'UNKNOWN')
        rows = freshness(first, {'samiran': {'status': 'STALE'}}, stamp)
        self.assertEqual(rows[0]['status'], 'ONLINE')
        self.assertEqual(rows[0]['data_quality'], 'STALE')
        self.assertEqual(freshness(first, {}, self.now + timedelta(minutes=5))[0]['data_quality'], 'STALE')

    def test_ambiguous_username_is_skipped(self):
        self.customers.append(dict(self.customers[0], router='AREA OTHER'))
        plan = plan_snapshot(self.snapshot, self.customers, self.now)
        self.assertEqual(plan['report']['conflicts'], 1)
        self.assertEqual(plan['customers'][0]['status'], 'OFFLINE')


class ReadOnlyServiceTests(unittest.TestCase):
    def test_only_print_and_selected_properties_are_requested(self):
        class Api:
            def __init__(self):
                self.calls = []
                self.closed = False
            def __call__(self, cmd, **kwargs):
                self.calls.append((cmd, kwargs))
                return iter({
                    '/system/identity/print': [{'name': 'REAL'}],
                    '/ppp/secret/print': [{'name': 'a', 'service': 'pppoe', 'password': 'never-store'}, {'name': 'b', 'service': 'any'}],
                    '/ppp/active/print': [{'name': 'a', 'service': 'pppoe', 'address': '192.0.2.1', 'caller-id': 'MAC', 'uptime': '10m'}]
                }[cmd])
            def close(self):
                self.closed = True
        api = Api()
        result = fetch_snapshot(RouterConfig('samiran', 'host', 8728, 'AREA'), connector=lambda _: api)
        self.assertTrue(result['snapshot_complete'])
        self.assertEqual([r['status'] for r in result['pppoe']], ['ONLINE', 'OFFLINE'])
        self.assertEqual(len(api.calls), 3)
        self.assertTrue(all(cmd.endswith('/print') for cmd, _ in api.calls))
        self.assertTrue(all('password' not in args['.proplist'] for _, args in api.calls))
        self.assertNotIn('password', json.dumps(result))
        self.assertNotIn('never-store', json.dumps(result))
        self.assertTrue(api.closed)

    def test_unknown_port_never_connects_and_credentials_not_in_repr(self):
        config = RouterConfig('samiran', 'host', 6100, 'AREA', password='private-value')
        self.assertNotIn('private-value', repr(config))
        with self.assertRaisesRegex(RouterError, 'SERVICE_UNCONFIRMED'):
            _connection(config)

    def test_partial_read_does_not_produce_json_or_replace_previous_success(self):
        class Api:
            closed = False
            def __call__(self, command, **kwargs):
                if command == '/system/identity/print':
                    return iter([{'name': 'REAL'}])
                def partial():
                    yield {'name': 'a', 'service': 'pppoe'}
                    raise TimeoutError()
                return partial()
            def close(self):
                self.closed = True
        api = Api()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'samiran.json'
            atomic_json(path, {'previous': 'success'})
            with self.assertRaises(RouterError):
                snapshot = fetch_snapshot(RouterConfig('samiran', 'host', 8728, 'AREA'), connector=lambda _: api)
                atomic_json(path, snapshot)
            self.assertEqual(json.loads(path.read_text()), {'previous': 'success'})
            self.assertTrue(api.closed)


if __name__ == '__main__':
    unittest.main()
