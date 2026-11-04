"""Local HTTP isolation, idempotency and delivery, without WhatsApp or live sends."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from http.client import HTTPConnection
from unittest.mock import patch

from whatsapp_local import WhatsAppLocal
from providers import Providers

ROOT = Path(__file__).resolve().parent.parent
NODE = ROOT / 'work/whatsapp-runtime/node.exe'


class LocalProviderTests(unittest.TestCase):
    def test_local_alerts_do_not_require_twilio_and_preserve_sensor_text(self):
        with tempfile.TemporaryDirectory() as directory:
            bridge = unittest.mock.Mock()
            bridge.status.return_value = {'state': 'connected'}
            bridge.send.return_value = 'wpp:00000000-0000-0000-0000-000000000001'
            with patch.dict(os.environ, {}, clear=True):
                p = Providers(Path(directory) / '.providers.json', whatsapp_local=bridge)
                p.save({'WHATSAPP_PROVIDER': 'wppconnect', 'live_enabled': True})
                job = {'channel': 'whatsapp', 'destination': '+15555550123', 'kind': 'temperature',
                       'message': 'Temperatura 35 °C; umidade 55%.', 'id': 1, 'created': 1}
                self.assertTrue(p.ready('whatsapp'))
                self.assertEqual(p.send(job), bridge.send.return_value)
                bridge.send.assert_called_once_with(job)
                bridge.status.return_value = {'state': 'qr', 'detail': 'Escaneie o QR Code.'}
                self.assertFalse(p.ready('whatsapp'))
                with self.assertRaisesRegex(ValueError, 'QR Code'):
                    p.send(job)


@unittest.skipUnless(NODE.exists(), 'Bundled Node runtime required')
class LocalBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.bridge = WhatsAppLocal(self.temp.name)
        self.bridge.directory.mkdir()
        self.count = Path(self.temp.name) / 'send-count'
        env = dict(os.environ, CLIMAGUARD_WPP_DATA=str(self.bridge.directory),
                   CLIMAGUARD_WPP_SECRET=self.bridge.secret, CLIMAGUARD_WPP_COUNT=str(self.count))
        self.bridge.process = subprocess.Popen([str(NODE), '--require', str(ROOT / 'tests/wpp_fixture.cjs'),
            str(ROOT / 'whatsapp_local/bridge.js')], env=env, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        for _ in range(100):
            if (self.bridge.directory / 'control.json').exists():
                return
            if self.bridge.process.poll() is not None:
                self.fail('Fixture helper exited before binding')
            time.sleep(.05)
        self.fail('Helper did not bind')

    def tearDown(self):
        self.bridge.close()
        self.temp.cleanup()

    def test_helper_rejects_missing_auth_and_browser_origin(self):
        port = json.loads((self.bridge.directory / 'control.json').read_text())['port']
        for headers in ({}, {'Authorization': 'Bearer ' + 'é' * len(self.bridge.secret)},
                        {'Authorization': 'Bearer ' + self.bridge.secret, 'Origin': 'http://example.test'}):
            connection = HTTPConnection('127.0.0.1', port, timeout=3)
            connection.request('GET', '/status', headers=headers)
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read(); connection.close()

    def test_send_requires_connection_is_idempotent_and_reads_delivery(self):
        job = {'id': 1, 'created': 1, 'destination': '+15555550123', 'message': 'Teste isolado °C'}
        with self.assertRaisesRegex(ValueError, 'Conecte'):
            self.bridge.send(job)
        self.bridge.request('/connect', {})
        for _ in range(40):
            if self.bridge.request('/status')['state'] == 'connected':
                break
            time.sleep(.02)
        first = self.bridge.send(job)
        self.assertEqual(self.bridge.send(job), first)
        self.assertEqual(self.count.read_text(), '1')
        self.assertEqual(self.bridge.delivery(first)[0], 'read')
        process = self.bridge.process
        self.bridge.close()
        self.assertIsNotNone(process.poll())


if __name__ == '__main__':
    unittest.main()
