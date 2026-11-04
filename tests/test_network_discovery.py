"""Exercise the actual LAN discovery socket without hardware or external messages."""
import hashlib
import hmac
import socket
import unittest

from network_discovery import ReceiverDiscovery


class DiscoveryTests(unittest.TestCase):
    def test_discovery_authenticates_nonce_port_and_address_without_exposing_token(self):
        token = 'synthetic-device-secret'
        service = ReceiverDiscovery(token, http_port=54321, host='127.0.0.1', port=0)
        service.start()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.settimeout(.2)
                peer = ('127.0.0.1', service.port)
                client.sendto(b'CLIMAGUARD_DISCOVER_V1 invalid', peer)
                with self.assertRaises(socket.timeout):
                    client.recvfrom(256)
                nonce = b'0123456789abcdef'
                client.sendto(b'CLIMAGUARD_DISCOVER_V1 ' + nonce, peer)
                response, _ = client.recvfrom(256)
                message, proof = response.rsplit(b' ', 1)
                self.assertEqual(message, b'CLIMAGUARD_SERVER_V1 ' + nonce + b' 54321 127.0.0.1')
                self.assertNotIn(token.encode(), response)
                self.assertEqual(proof, hmac.new(token.encode(), message, hashlib.sha256).hexdigest().encode())
                self.assertNotEqual(proof, hmac.new(b'wrong-token', message, hashlib.sha256).hexdigest().encode())
        finally:
            service.close()
        self.assertFalse(service.thread.is_alive())
