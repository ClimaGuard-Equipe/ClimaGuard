"""USB provisioning uses a verified board and never reflects Wi-Fi passwords."""
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from portal import create_app
from wifi_provision import WifiProvision, validate_wifi


class UsbConnection:
    def __init__(self, success=True, wrong_id=False):
        self.success = success
        self.writes = []
        self.lines = [json.dumps({'app':'ClimaGuard','id':'cg-0123456789ab','wifi':{'setup_ssid':'ClimaGuard-6789AB'}}).encode()]
        self.wrong_id = wrong_id

    def __enter__(self): return self
    def __exit__(self,*args): pass
    def flush(self): pass
    def readline(self,*args): return self.lines.pop(0) if self.lines else b''

    def write(self,value):
        self.writes.append(value)
        request = json.loads(value)
        reply = dict(app='ClimaGuard',id='cg-0123456789ab',request_id=request['request_id'],
                     event='wifi_result' if request['command']=='set_wifi' else request['command'],ok=self.success)
        if request['command']=='wifi_card': reply.update(ap_ssid='ClimaGuard-6789AB',ap_password='TESTCARD23456')
        else: reply.update(ssid=request.get('ssid',''),ip='192.168.1.42')
        if not self.success: reply['message']='An untrusted board might echo SECRET-NOT-TO-REFLECT'
        self.lines.append(json.dumps(reply).encode())


class WifiProvisionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.provision = WifiProvision(self.directory.name)
        self.ports = patch('wifi_provision.list_ports.comports',return_value=[SimpleNamespace(vid=0x1a86,device='COM88')])
        self.ports.start()

    def tearDown(self):
        self.ports.stop()
        self.directory.cleanup()

    def test_usb_card_is_persistent_and_qr_contains_no_home_wifi_password(self):
        connection = UsbConnection()
        with patch('wifi_provision.serial.Serial',return_value=connection):
            card = self.provision.capture_card('cg-0123456789ab')
        self.assertEqual(card['ssid'],'ClimaGuard-6789AB')
        self.assertTrue(card['qr'].startswith('data:image/png;base64,'))
        self.assertEqual(self.provision.card(card['id']),card)
        self.assertEqual(json.loads(connection.writes[0])['command'],'wifi_card')

    def test_usb_sends_unicode_credentials_without_storing_or_returning_network_password(self):
        card_connection = UsbConnection()
        with patch('wifi_provision.serial.Serial',return_value=card_connection): self.provision.capture_card()
        connection = UsbConnection()
        password = 'sensitive-WIFI-password'
        with patch('wifi_provision.serial.Serial',return_value=connection):
            result = self.provision.configure('Rede João',password,'cg-0123456789ab')
        self.assertEqual(json.loads(connection.writes[0])['ssid'],'Rede João')
        self.assertEqual(json.loads(connection.writes[0])['password'],password)
        self.assertNotIn(password,json.dumps(result))
        self.assertNotIn(password,self.provision.path.read_text())

    def test_failure_does_not_reflect_arbitrary_serial_message(self):
        connection = UsbConnection(success=False)
        with patch('wifi_provision.serial.Serial',return_value=connection),self.assertRaises(ValueError) as raised:
            self.provision.exchange('set_wifi',{'ssid':'test-network','password':'SECRET-NOT-TO-REFLECT'})
        self.assertNotIn('SECRET-NOT-TO-REFLECT',str(raised.exception))

    def test_firmware_error_code_explains_storage_failure_without_echoing_serial_text(self):
        connection = UsbConnection(success=False)
        original_write = connection.write
        def reply_with_code(payload):
            original_write(payload)
            reply = json.loads(connection.lines[-1])
            reply['error_code'] = 'storage_failed'
            connection.lines[-1] = json.dumps(reply).encode()
        connection.write = reply_with_code
        with patch('wifi_provision.serial.Serial',return_value=connection), self.assertRaises(ValueError) as raised:
            self.provision.exchange('set_wifi', {'ssid':'test-network','password':'test-password'})
        self.assertIn('memória',str(raised.exception))
        self.assertNotIn('SECRET',str(raised.exception))

    def test_another_board_is_rejected_before_sending_credentials(self):
        connection = UsbConnection()
        with patch('wifi_provision.serial.Serial',return_value=connection),self.assertRaises(ValueError):
            self.provision.exchange('set_wifi',{'ssid':'test-network','password':'test-password'},'cg-ffffffffffff')
        self.assertEqual(connection.writes,[])

    def test_selected_port_is_used_when_multiple_usb_devices_exist(self):
        connection = UsbConnection()
        with patch.object(self.provision, 'ports', return_value=[SimpleNamespace(device='COM77'), SimpleNamespace(device='COM88')]), \
             patch('wifi_provision.serial.Serial', return_value=connection) as serial:
            self.provision.capture_card(port='COM88')
        serial.assert_called_once_with('COM88', 115200, timeout=.25, write_timeout=2)

    def test_stale_or_arbitrary_port_is_rejected_before_opening_usb(self):
        with patch('wifi_provision.serial.Serial') as serial:
            for port in ('COM99', '../private', '', 88):
                with self.subTest(port=port), self.assertRaises(ValueError):
                    self.provision.configure('test-network', 'test-password', port=port)
            serial.assert_not_called()

    def test_invalid_lengths_controls_and_utf8_are_rejected_before_opening_usb(self):
        with patch('wifi_provision.serial.Serial') as serial:
            for ssid,password in [('', 'password'),('a'*33,'password'),('é'*17,'password'),('test','short'),('test','bad\npassword'),('test',None)]:
                with self.subTest(ssid=ssid),self.assertRaises(ValueError): self.provision.configure(ssid,password)
            serial.assert_not_called()
        self.assertEqual(validate_wifi('open-network',''),('open-network',''))


class WifiProvisionPortalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = create_app(self.directory.name,worker=False)
        self.client = self.app.test_client()
        csrf = self.client.get('/api/session').json['csrf_token']
        registered = self.client.post('/api/register',json={'name':'Wifi test','email':'wifi@example.test','password':'test-password'},headers={'X-CSRF-Token':csrf}).json
        self.csrf = registered['csrf_token']
        self.user_id = registered['user']['id']

    def tearDown(self): self.directory.cleanup()

    def test_wifi_card_and_changes_are_admin_only_local_and_csrf_protected(self):
        self.assertEqual(self.client.post('/api/device/wifi',json={'action':'save'}).status_code,403)
        self.assertEqual(self.client.get('/api/device/wifi',environ_overrides={'REMOTE_ADDR':'192.168.1.8'}).status_code,403)
        with patch.object(self.app.extensions['climaguard_wifi_provision'],'ports',return_value=[]):
            self.assertIsNone(self.client.get('/api/device/wifi').json['card'])
        with self.app.extensions['climaguard_store'].connect() as db: db.execute('UPDATE users SET admin=0 WHERE id=?',(self.user_id,))
        self.assertEqual(self.client.get('/api/device/wifi').status_code,403)

    def test_wifi_password_is_only_forwarded_to_usb_and_never_stored_in_preferences(self):
        provision = self.app.extensions['climaguard_wifi_provision']
        with patch.object(provision,'configure',return_value={'ok':True,'message':'Rede salva'}) as configure:
            response = self.client.post('/api/device/wifi',json={'action':'save','ssid':'test-network','password':'test-secret-password'},headers={'X-CSRF-Token':self.csrf})
            self.assertEqual(response.status_code,200)
            configure.assert_called_once_with('test-network','test-secret-password',None,port=None)
            self.assertNotIn('test-secret-password',response.get_data(as_text=True))
        self.assertNotIn('test-secret-password',json.dumps(self.app.extensions['climaguard_store'].preferences(self.user_id)))

    def test_usb_ports_are_listed_and_explicit_selection_reaches_provisioner(self):
        provision = self.app.extensions['climaguard_wifi_provision']
        with patch.object(provision, 'ports', return_value=[SimpleNamespace(device='COM88', description='ESP32 USB')]):
            result = self.client.get('/api/device/wifi').json
        self.assertEqual(result['ports'], [{'device': 'COM88', 'description': 'ESP32 USB'}])
        self.assertTrue(result['usb_available'])
        with patch.object(provision, 'configure', return_value={'ok': True, 'message': 'Rede salva'}) as configure:
            response = self.client.post('/api/device/wifi', json={'action': 'save', 'port': 'COM88', 'ssid': 'test-network', 'password': 'test-password'}, headers={'X-CSRF-Token': self.csrf})
        self.assertEqual(response.status_code, 200)
        configure.assert_called_once_with('test-network', 'test-password', None, port='COM88')

    def test_common_local_account_can_configure_usb_without_receiving_private_card(self):
        provision = self.app.extensions['climaguard_wifi_provision']
        with self.app.extensions['climaguard_store'].connect() as db:
            db.execute('UPDATE users SET admin=0 WHERE id=?', (self.user_id,))
        self.assertEqual(self.client.get('/api/device/wifi').status_code, 403)
        self.assertEqual(self.client.get('/api/device/wifi/usb', environ_overrides={'REMOTE_ADDR':'192.168.1.8'}).status_code, 403)
        self.assertEqual(self.client.post('/api/device/wifi/usb', json={'action':'identify'}).status_code, 403)
        with patch.object(provision, 'ports', return_value=[SimpleNamespace(device='COM88',description='ESP32 USB')]):
            self.assertEqual(self.client.get('/api/device/wifi/usb').json['ports'][0]['device'],'COM88')
        with patch.object(provision, 'capture_card', return_value={'id':'cg-0123456789ab','password':'PRIVATE-AP-PASSWORD','qr':'PRIVATE-QR'}):
            response = self.client.post('/api/device/wifi/usb', json={'action':'identify','port':'COM88'}, headers={'X-CSRF-Token':self.csrf})
            self.assertEqual(response.json, {'ok':True,'id':'cg-0123456789ab'})
        with patch.object(provision, 'configure', return_value={'ok':True,'message':'Rede salva'}) as configure:
            response = self.client.post('/api/device/wifi/usb', json={'action':'save','port':'COM88','ssid':'test-network','password':'test-password'}, headers={'X-CSRF-Token':self.csrf})
            self.assertEqual(response.status_code, 200)
            configure.assert_called_once_with('test-network','test-password',None,port='COM88')
        with patch.object(provision, 'open_portal') as open_portal:
            response = self.client.post('/api/device/wifi/usb', json={'action':'portal'}, headers={'X-CSRF-Token':self.csrf})
            self.assertEqual(response.status_code, 400)
            open_portal.assert_not_called()
