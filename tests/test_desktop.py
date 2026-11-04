"""Desktop packaging and USB persistence tests, without native windows or real sends."""
import json
from http.client import HTTPConnection
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.request import ProxyHandler, build_opener

from desktop import DesktopServer, SingleInstance, application_data_dir, self_test
from receber_usb import main as receive_usb


class DesktopTests(unittest.TestCase):
    def test_wifi_ingest_needs_no_usb_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            server = DesktopServer(directory, host='127.0.0.1', port=0)
            try:
                server.start()
                self.assertFalse(server.usb_enabled)
                self.assertIsNone(server.usb_thread)
                token = (Path(directory) / '.device-token').read_text().strip()
                connection = HTTPConnection('127.0.0.1', server.server.effective_port, timeout=5)
                try:
                    connection.request('POST', '/api/readings', body=json.dumps({'temperature':26.1,'humidity':52,'energy':True}),
                                       headers={'Content-Type':'application/json','X-Device-Token':token})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertTrue(json.loads(response.read())['ok'])
                    snapshot = server.app.extensions['climaguard_store'].snapshot(0, 'real')
                    self.assertTrue(snapshot['online'])
                    self.assertEqual(snapshot['latest']['temperature'], 26.1)
                finally:
                    connection.close()
            finally:
                server.close()
            self.assertFalse(server.delivery_thread.is_alive())

    def test_desktop_data_is_persistent_and_separate_from_bundle(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOCALAPPDATA': directory}, clear=True):
            self.assertEqual(application_data_dir(), Path(directory) / 'ClimaGuard')
            with patch.dict(os.environ, {'CLIMAGUARD_DATA_DIR': str(Path(directory) / 'custom')}):
                self.assertEqual(application_data_dir(), Path(directory) / 'custom')

    def test_desktop_server_serves_assets_and_processes_notification_queue(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            server = DesktopServer(directory, host='127.0.0.1', port=0, usb=False)
            try:
                client = server.app.test_client()
                csrf = client.get('/api/session').json['csrf_token']
                created = client.post('/api/register', json={'name': 'Teste desktop', 'email': 'desktop@example.test',
                                      'password': 'desktop-test-only'}, headers={'X-CSRF-Token': csrf}).json
                csrf = created['csrf_token']
                client.post('/api/preferences', json={'enabled': True, 'temperature_enabled': True, 'power_enabled': True,
                            'threshold': 30, 'cooldown_minutes': 1, 'channels': ['email'], 'phone': '',
                            'email': 'desktop@example.test', 'consent': True}, headers={'X-CSRF-Token': csrf})
                providers = server.app.extensions['climaguard_providers']
                providers.save({'RESEND_API_KEY': 'synthetic-key', 'RESEND_FROM': 'test@example.test', 'live_enabled': True})
                sent = threading.Event()

                class Response:
                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        pass

                    def read(self, size):
                        return b'{"id":"synthetic-message"}'

                def fake_transport(request, timeout):
                    sent.set()
                    return Response()

                providers.transport = fake_transport
                server.start()
                # Let the empty queue worker go idle before submitting a job.
                time.sleep(.2)
                result = client.post('/api/test-message', json={'channel': 'email', 'confirm': True}, headers={'X-CSRF-Token': csrf})
                self.assertEqual(result.status_code, 202)
                self.assertTrue(sent.wait(.8), 'A new job did not wake the idle delivery worker')
                deadline = time.monotonic() + 3
                while client.get('/api/alerts').json['alerts'][0]['status'] == 'sending' and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertEqual(client.get('/api/alerts').json['alerts'][0]['status'], 'accepted')
                connection = HTTPConnection('127.0.0.1', int(server.server.effective_port), timeout=5)
                try:
                    connection.request('GET', '/')
                    self.assertIn(b'ClimaGuard', connection.getresponse().read())
                finally:
                    connection.close()
            finally:
                server.close()
                server.server_thread.join(timeout=3)
                self.assertFalse(server.server_thread.is_alive())

    def test_self_test_writes_real_http_check_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.json'
            self_test(path)
            report = json.loads(path.read_text(encoding='utf-8'))
            self.assertTrue(report['ok'])
            self.assertEqual(report['checks']['/health']['status'], 200)
            self.assertGreater(report['checks']['/assets/app.js']['bytes'], 1000)

    @unittest.skipUnless(os.name == 'nt', 'Windows named mutex')
    def test_second_instance_is_detected_and_lock_is_released(self):
        with tempfile.TemporaryDirectory() as directory:
            first = SingleInstance(Path(directory))
            second = SingleInstance(Path(directory))
            try:
                self.assertFalse(first.already_running)
                self.assertTrue(second.already_running)
            finally:
                second.close()
                first.close()
            third = SingleInstance(Path(directory))
            try:
                self.assertFalse(third.already_running)
            finally:
                third.close()

    def test_usb_uses_installed_data_directory_and_releases_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            (data_dir / '.device-token').write_text('synthetic-device-token', encoding='utf-8')
            stop = threading.Event()
            request_sent = []
            fake_connection = SimpleNamespace(reset_input_buffer=lambda: None,
                readline=lambda: b'{"temperature":25,"humidity":55,"energy":true}\n')

            class Connection:
                def __enter__(self):
                    return fake_connection

                def __exit__(self, *args):
                    stop.set()

            class Response:
                def __enter__(self):
                    stop.set()
                    return self

                def __exit__(self, *args):
                    pass

                def read(self):
                    return b'{}'

            def send(request, timeout):
                request_sent.append(request)
                return Response()

            port = SimpleNamespace(device='COM9', description='USB CH340', vid=0x1A86, pid=0x7523)
            with patch('receber_usb.list_ports.comports', return_value=[port]), \
                 patch('receber_usb.serial.Serial', return_value=Connection()), \
                 patch('receber_usb.urllib.request.build_opener', return_value=SimpleNamespace(open=send)):
                receive_usb(data_dir=data_dir, server_url='http://127.0.0.1:54321', stop_event=stop)
            self.assertEqual(request_sent[0].full_url, 'http://127.0.0.1:54321/api/readings')
            self.assertEqual(request_sent[0].get_header('X-device-token'), 'synthetic-device-token')
            self.assertEqual(json.loads(request_sent[0].data)['humidity'], 55)
            self.assertTrue((data_dir / 'recebimento-usb.log').exists())


if __name__ == '__main__':
    unittest.main()
