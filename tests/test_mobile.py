"""iPhone authorization, isolation, expiry and remote setup without external traffic."""
import json
from pathlib import Path
import tempfile
import subprocess
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mobile import MobileCompanion, COOKIE
from mobile_remote import MobileRemote
from portal import create_app

ORIGIN = 'https://test-node.test-tail.ts.net:8443'
HEADERS = {'X-ClimaGuard-Mobile': '1', 'Origin': ORIGIN}
READY = dict(state='ready', ready=True, url=ORIGIN, detail='Pronto')


class MobileTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict('os.environ', {}, clear=True)
        self.env.start()
        self.directory = tempfile.TemporaryDirectory()
        self.app = create_app(self.directory.name, worker=False)
        self.desktop = self.app.test_client()
        csrf = self.desktop.get('/api/session').json['csrf_token']
        result = self.desktop.post('/api/register', json=dict(name='Mobile test', email='owner@example.test', password='synthetic-test-password'), headers={'X-CSRF-Token': csrf}).json
        self.csrf, self.owner = result['csrf_token'], result['user']['id']
        self.mobile = self.app.extensions['climaguard_mobile']
        self.mobile.available = True
        self.remote = patch.object(self.mobile.remote, 'status', return_value=READY)
        self.remote.start()

    def tearDown(self):
        self.remote.stop()
        self.directory.cleanup()
        self.env.stop()

    def pair(self, name='iPhone test'):
        client = self.mobile.app.test_client()
        issued = self.mobile.issue(self.owner)
        response = client.post('/api/pair', base_url=ORIGIN, json=dict(code=issued['code'], name=name), headers=HEADERS)
        self.assertEqual(response.status_code, 200, response.json)
        return client, issued, response

    def test_pairing_is_one_use_and_saved_as_hash_only(self):
        client, issued, response = self.pair()
        cookie = client.get_cookie(COOKIE, domain='test-node.test-tail.ts.net')
        self.assertIsNotNone(cookie)
        self.assertIn('Secure', response.headers['Set-Cookie'])
        self.assertIn('HttpOnly', response.headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', response.headers['Set-Cookie'])
        saved = self.mobile.path.read_text()
        self.assertNotIn(cookie.value, saved)
        self.assertNotIn(issued['code'], saved)
        again = self.mobile.app.test_client().post('/api/pair', base_url=ORIGIN, json=dict(code=issued['code'], name='Other'), headers=HEADERS)
        self.assertEqual(again.status_code, 400)
        self.assertEqual(client.get('/api/status', base_url=ORIGIN).status_code, 200)

    def test_three_iphones_have_independent_revocable_access(self):
        phones = [self.pair(name)[0] for name in ('iPhone 15', 'iPhone 15 Pro Max', 'iPhone 16 Pro Max')]
        devices = self.mobile.access(self.owner)['devices']
        self.assertEqual(len(devices), 3)
        self.assertEqual(len({d['id'] for d in devices}), 3)
        response = self.desktop.post('/api/mobile/access', json=dict(action='revoke', id=devices[1]['id']), headers={'X-CSRF-Token': self.csrf})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([p.get('/api/status', base_url=ORIGIN).status_code for p in phones], [200, 401, 200])

    def test_access_survives_restart_and_expires_after_thirty_days(self):
        client, _, _ = self.pair()
        token = client.get_cookie(COOKIE, domain='test-node.test-tail.ts.net').value
        restored = MobileCompanion(self.directory.name, self.mobile.store, self.mobile.network, self.mobile.remote)
        second = restored.app.test_client()
        second.set_cookie(COOKIE, token, domain='test-node.test-tail.ts.net', secure=True)
        self.assertEqual(second.get('/api/status', base_url=ORIGIN).status_code, 200)
        with patch('mobile.time.time', return_value=time.time() + 31 * 86400):
            self.assertEqual(second.get('/api/status', base_url=ORIGIN).status_code, 401)

    def test_code_expires_and_bad_attempts_are_limited(self):
        issued = self.mobile.issue(self.owner)
        with patch('mobile.time.time', return_value=time.time() + 301), self.assertRaises(ValueError):
            self.mobile.pair(issued['code'], 'Expired')
        for _ in range(7):
            with self.assertRaises(ValueError): self.mobile.pair('not-a-code', 'Bad')
        with self.assertRaisesRegex(ValueError, 'Aguarde'):
            self.mobile.pair(issued['code'], 'Rate limited')

    def test_pair_and_logout_require_same_origin_custom_header(self):
        issued = self.mobile.issue(self.owner)
        client = self.mobile.app.test_client()
        data = dict(code=issued['code'], name='My phone')
        self.assertEqual(client.post('/api/pair', json=data, base_url=ORIGIN).status_code, 403)
        self.assertEqual(client.post('/api/pair', json=data, base_url=ORIGIN, headers={**HEADERS, 'Origin':'https://other.example'}).status_code, 403)
        self.assertEqual(client.post('/api/pair', json=[], base_url=ORIGIN, headers=HEADERS).status_code, 400)

    def test_unpaired_clients_cannot_read_and_desktop_apis_do_not_exist(self):
        client = self.mobile.app.test_client()
        self.assertEqual(client.get('/api/status', base_url=ORIGIN).status_code, 401)
        for path in ('/api/providers', '/api/session', '/api/device/wifi', '/api/preferences', '/api/readings', '/api/mobile/access', '/assets/../portal.py'):
            with self.subTest(path=path):self.assertEqual(client.get(path, base_url=ORIGIN).status_code, 404)

    def test_snapshot_excludes_credentials_contacts_and_other_users_alerts(self):
        client, _, _ = self.pair()
        store = self.mobile.store
        providers = self.app.extensions['climaguard_providers']
        providers.save({'RESEND_API_KEY':'SECRET-API-KEY', 'RESEND_FROM':'private@example.test'})
        store.add_reading(dict(temperature=26.2, humidity=55.4, energy=True), 'real', 0, providers)
        prefs = store.preferences(self.owner)
        prefs.update(email='private-contact@example.test', phone='+5511999999999')
        store.save_preferences(self.owner, prefs)
        with store.connect() as db:
            store.queue(db, self.owner, 'real', 'power', 'email', prefs, 'Owner message', providers, time.time())
            store.queue(db, self.owner + 100, 'real', 'power', 'email', prefs, 'OTHER-USER-SECRET', providers, time.time())
        result = client.get('/api/status', base_url=ORIGIN)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['latest']['temperature'], 26.2)
        self.assertEqual(len(result.json['alerts']), 1)
        for secret in ('SECRET-API-KEY', 'private@example.test', 'private-contact@example.test', '+5511999999999', 'OTHER-USER-SECRET', 'provider_id', 'destination'):
            self.assertNotIn(secret, result.get_data(as_text=True))
        self.assertEqual(result.headers['Cache-Control'], 'no-store')

    def test_demo_and_frozen_board_cannot_show_live(self):
        client, _, _ = self.pair()
        providers = self.app.extensions['climaguard_providers']
        self.mobile.store.add_reading(dict(temperature=25, humidity=50, energy=True), 'demo', self.owner, providers)
        result = client.get('/api/status', base_url=ORIGIN).json
        self.assertFalse(result['online'])
        self.assertIsNone(result['latest'])
        self.mobile.store.add_reading(dict(temperature=25, humidity=50, energy=True), 'real', 0, providers)
        self.mobile.network.selected = 'cg-0123456789ab'
        self.assertFalse(client.get('/api/status', base_url=ORIGIN).json['online'])

    def test_logout_revokes_persistent_access(self):
        client, _, _ = self.pair()
        self.assertEqual(client.post('/api/logout', base_url=ORIGIN, json={}, headers=HEADERS).status_code, 200)
        self.assertEqual(client.get('/api/status', base_url=ORIGIN).status_code, 401)
        self.assertEqual(self.mobile.access(self.owner)['devices'], [])

    def test_manifest_icons_shell_and_service_worker_are_bundled(self):
        client = self.mobile.app.test_client()
        manifest = client.get('/manifest.webmanifest').json
        self.assertEqual(manifest['display'], 'standalone')
        self.assertEqual(manifest['start_url'], '/')
        for path in ('/', '/assets/mobile.css', '/assets/mobile.js', '/assets/icon-180.png', '/assets/icon-192.png', '/assets/icon-512.png', '/sw.js'):
            with self.subTest(path=path), client.get(path) as response:self.assertEqual(response.status_code, 200)
        with client.get('/sw.js') as worker:
            self.assertEqual(worker.headers['Service-Worker-Allowed'], '/')
            self.assertIn("url.pathname.startsWith('/api/')", worker.get_data(as_text=True))

    def test_desktop_pairing_needs_login_localhost_and_csrf(self):
        self.assertEqual(self.desktop.post('/api/mobile/access', json={'action':'pair'}).status_code, 403)
        self.assertEqual(self.desktop.get('/api/mobile/access', environ_overrides={'REMOTE_ADDR':'192.168.1.44'}).status_code, 403)
        self.assertEqual(self.desktop.post('/api/mobile/access', json={'action':'pair'}, headers={'X-CSRF-Token': self.csrf}).status_code, 200)
        with self.mobile.store.connect() as db:db.execute('UPDATE users SET admin=0 WHERE id=?', (self.owner,))
        self.assertEqual(self.desktop.post('/api/mobile/access', json={'action':'remote'}, headers={'X-CSRF-Token': self.csrf}).status_code, 403)


class RemoteTests(unittest.TestCase):
    def setup_remote(self, configuration=None):
        remote = MobileRemote()
        remote.executable = lambda: 'test-tailscale.exe'
        config = configuration or {}
        calls = []

        def command(arguments, timeout=10):
            calls.append(arguments)
            if arguments == ['status', '--json']:
                return SimpleNamespace(returncode=0, stdout=json.dumps({'BackendState':'Running', 'Self':{'DNSName':'test-node.test-tail.ts.net.'}}), stderr='')
            if arguments == ['serve', 'status', '--json']:
                return SimpleNamespace(returncode=0, stdout=json.dumps(config), stderr='')
            config.update({'TCP':{'8443':{'HTTPS':True}}, 'Web':{'test-node.test-tail.ts.net:8443':{'Handlers':{'/':{'Proxy':'http://127.0.0.1:5003'}}}}})
            return SimpleNamespace(returncode=0, stdout='Ready', stderr='')
        remote.command = command
        return remote, calls

    def test_private_https_is_prepared_without_touching_port_443(self):
        remote, calls = self.setup_remote({'TCP':{'443':{'HTTPS':True}}, 'Web':{'test-node.test-tail.ts.net:443':{'Handlers':{'/':{'Proxy':'http://127.0.0.1:7000'}}}}})
        self.assertTrue(remote.enable()['ready'])
        self.assertIn(['serve', '--bg', '--https=8443', 'http://127.0.0.1:5003'], calls)
        self.assertFalse(any('funnel' in call for call in calls))

    def test_existing_listener_or_public_funnel_is_not_overwritten(self):
        for config in ({'TCP':{'8443':{'HTTPS':True}}}, {'AllowFunnel':{'test-node.test-tail.ts.net:8443':True}}):
            remote, calls = self.setup_remote(config)
            with self.assertRaisesRegex(ValueError, 'preservada'):remote.enable()
            self.assertFalse(any('--bg' in call for call in calls))

    def test_login_and_missing_installation_do_not_change_configuration(self):
        remote = MobileRemote()
        remote.executable = lambda: None
        self.assertEqual(remote.status()['state'], 'not_installed')
        with self.assertRaises(ValueError):remote.enable()
        remote.executable = lambda: 'test.exe'
        remote.command = lambda *a, **kw: SimpleNamespace(returncode=0, stdout='{"BackendState":"NeedsLogin"}', stderr='')
        self.assertEqual(remote.status(force=True)['state'], 'login')

    def test_https_consent_url_is_preserved_when_cli_waits_for_user(self):
        remote, calls = self.setup_remote()
        original = remote.command
        def command(arguments, timeout=10):
            if '--bg' in arguments:
                raise subprocess.TimeoutExpired(arguments, timeout, output=b'Enable HTTPS: https://login.tailscale.com/f/serve?node=test-node\n')
            return original(arguments, timeout)
        remote.command = command
        result = remote.enable()
        self.assertEqual(result['state'], 'approval')
        self.assertEqual(result['approval_url'], 'https://login.tailscale.com/f/serve?node=test-node')
