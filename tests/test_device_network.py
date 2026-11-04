"""Actual UDP/HTTP board simulation: fresh installs, adapters, freshness and access limits."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from device_network import DeviceNetwork, lan_interfaces
from portal import create_app


class FakeBoard:
    def __init__(self):
        self.value = dict(app='ClimaGuard', protocol=2, id='cg-0123456789ab', model='ESP8266',
                          boot_id='0123456789abcdef', sequence=1, sample_age_ms=0,
                          temperature=27.5, humidity=51.2, energy=True)
        board = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                payload = json.dumps(board.value).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(('127.0.0.1', 0))
        self.udp.settimeout(.1)
        self.stop = threading.Event()
        self.discovery_thread = threading.Thread(target=self.announce, daemon=True)
        self.thread.start()
        self.discovery_thread.start()

    def announce(self):
        while not self.stop.is_set():
            try:
                data, peer = self.udp.recvfrom(128)
                prefix = b'CLIMAGUARD_FIND_V2 '
                if data.startswith(prefix):
                    reply = {key: self.value[key] for key in ('app', 'protocol', 'id', 'model')}
                    reply.update(nonce=data[len(prefix):].decode(), port=self.http.server_port)
                    self.udp.sendto(json.dumps(reply).encode(), peer)
            except socket.timeout:
                continue

    def configure(self, manager):
        manager.interfaces = lambda: [dict(name='Ethernet de teste', ip='127.0.0.1',
                                           network='127.0.0.0/8', broadcast='127.0.0.1')]
        manager.device_port = self.http.server_port
        manager.discovery_port = self.udp.getsockname()[1]

    def close(self):
        self.stop.set()
        self.discovery_thread.join(timeout=2)
        self.udp.close()
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=2)


class DeviceNetworkTests(unittest.TestCase):
    def setUp(self):
        self.board = FakeBoard()
        self.directory = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.board.close()
        self.directory.cleanup()

    def manager(self):
        self.received = []
        manager = DeviceNetwork(self.directory.name, self.received.append)
        self.board.configure(manager)
        return manager

    def test_discovery_and_poll_work_in_two_fresh_installs_with_different_tokens(self):
        with tempfile.TemporaryDirectory() as other:
            apps = [create_app(path, worker=False) for path in (self.directory.name, other)]
            tokens = [(Path(path) / '.device-token').read_text() for path in (self.directory.name, other)]
            self.assertNotEqual(*tokens)
            for app in apps:
                manager = app.extensions['climaguard_network']
                self.board.configure(manager)
                manager.discover()
                manager.poll()
                self.assertTrue(manager.snapshot()['online'])
                self.assertEqual(manager.snapshot()['device']['ip'], '127.0.0.1')
                status = app.extensions['climaguard_store'].snapshot(0, 'real')
                self.assertEqual(status['latest']['temperature'], 27.5)
                self.assertEqual(len(status['history']), 1)

    def test_same_sample_is_not_duplicated_and_board_restart_is_accepted(self):
        manager = self.manager()
        manager.connect_address('127.0.0.1')
        manager.poll()
        manager.poll()
        self.assertEqual(len(self.received), 1)
        self.board.value['sequence'] += 1
        manager.poll()
        self.assertEqual(len(self.received), 2)
        self.board.value.update(boot_id='fedcba9876543210', sequence=1)
        manager.poll()
        self.assertEqual(len(self.received), 3)

    def test_live_reading_arrives_during_blocked_discovery(self):
        manager = self.manager()
        manager.connect_address('127.0.0.1')
        manager.poll()
        scanning, release, received = threading.Event(), threading.Event(), threading.Event()

        def slow_discovery():
            scanning.set()
            release.wait(3)

        manager.discover = slow_discovery
        manager.receive = lambda row: received.set()
        try:
            manager.start()
            self.assertTrue(scanning.wait(1))
            self.board.value.update(sequence=2, energy=False)
            self.assertTrue(received.wait(.8), 'Discovery blocked a new live reading')
            self.assertFalse(release.is_set())
        finally:
            release.set()
            manager.close()
        self.assertFalse(manager.thread.is_alive())
        self.assertFalse(manager.discovery_thread.is_alive())

    def test_saved_board_is_located_again_after_its_ip_changes(self):
        manager = self.manager()
        manager.selected = self.board.value['id']
        manager.devices[manager.selected] = dict(id=manager.selected, ip='127.0.0.2', model='ESP8266', seen=0)
        manager.save_selection()
        manager.discover()
        manager.poll()
        self.assertEqual(manager.snapshot()['device']['ip'], '127.0.0.1')
        self.assertEqual(json.loads(manager.path.read_text())['ip'], '127.0.0.1')
        self.assertTrue(manager.snapshot()['online'])

    def test_http_success_with_frozen_sequence_does_not_keep_connection_green(self):
        manager = self.manager()
        manager.connect_address('127.0.0.1')
        manager.poll()
        manager.last_sample = time.time() - 21
        manager.poll()
        self.assertFalse(manager.snapshot()['online'])
        self.assertEqual(manager.snapshot()['state'], 'offline')
        self.assertIsNotNone(manager.snapshot()['last_contact'])

    def test_stale_or_invalid_sensor_payload_is_not_ingested(self):
        manager = self.manager()
        manager.connect_address('127.0.0.1')
        self.board.value['sample_age_ms'] = 20000
        with self.assertRaises(ValueError):
            manager.poll()
        self.board.value.update(sample_age_ms=0, humidity=999)
        manager.connect_address('127.0.0.1')
        with self.assertRaises(ValueError):
            manager.poll()
        self.assertEqual(self.received, [])

    def test_esp32_zmpt_disabled_keeps_temperature_and_never_invents_energy(self):
        manager = self.manager()
        self.board.value.update(model='ESP32', energy=None,
                                power={'type':'ZMPT101B','valid':False,'state':'disabled','enabled':False,'calibrated':False})
        manager.connect_address('127.0.0.1')
        manager.poll()
        self.assertTrue(manager.snapshot()['online'])
        self.assertEqual(self.received[0]['temperature'], 27.5)
        self.assertIsNone(self.received[0]['energy'])
        self.assertEqual(manager.snapshot()['device']['power']['state'], 'disabled')
        self.board.value.update(sequence=2, temperature=None, humidity=None)
        manager.poll()
        self.assertEqual(self.received[-1], {'temperature':None,'humidity':None,'energy':None})
        self.board.value.update(sequence=3, temperature=25, humidity=50, energy=True, power={'type':'unrecognized'})
        manager.poll()
        self.assertNotIn('power', manager.snapshot()['device'])

    def test_cannot_probe_external_addresses_urls_or_local_broadcast(self):
        manager = self.manager()
        for address in ('8.8.8.8', 'http://127.0.0.1', '127.255.255.255', '127.0.0.0', None):
            with self.subTest(address=address), self.assertRaises(ValueError):
                manager.connect_address(address)

    def test_active_ethernet_and_wifi_are_both_searched_without_default_wifi_assumption(self):
        def address(ip):
            return SimpleNamespace(family=socket.AF_INET, address=ip, netmask='255.255.255.0')
        addresses = {'Ethernet':[address('192.168.1.50')], 'Wi-Fi':[address('192.168.10.5')],
                     'Loopback':[address('127.0.0.1')], 'Off':[address('10.0.0.2')]}
        stats = {name:SimpleNamespace(isup=name!='Off') for name in addresses}
        with patch('device_network.psutil.net_if_addrs', return_value=addresses), patch('device_network.psutil.net_if_stats', return_value=stats):
            adapters = lan_interfaces()
        self.assertEqual([item['name'] for item in adapters], ['Ethernet','Wi-Fi'])
        self.assertEqual([item['broadcast'] for item in adapters], ['192.168.1.255','192.168.10.255'])

    def test_multiple_boards_require_selection_and_selected_board_is_not_replaced(self):
        manager = self.manager()
        manager.last_scan = time.time()
        manager.adapters = manager.interfaces()
        now = time.time()
        manager.devices = {key:dict(id=key,ip=ip,model='ESP8266',seen=now) for key,ip in
                           [('cg-0123456789ab','127.0.0.1'),('cg-0123456789ac','127.0.0.2')]}
        self.assertEqual(manager.snapshot()['state'], 'choose')
        manager.select_device('cg-0123456789ac')
        manager.discover()
        self.assertEqual(manager.selected,'cg-0123456789ac')

    def test_demo_readings_do_not_prove_physical_communication(self):
        app = create_app(self.directory.name, worker=False)
        store = app.extensions['climaguard_store']
        store.add_reading(dict(temperature=28,humidity=50,energy=True),'demo',1,app.extensions['climaguard_providers'])
        self.assertFalse(app.extensions['climaguard_network'].snapshot()['online'])
