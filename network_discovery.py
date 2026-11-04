"""Local discovery of the receiver, authenticated without broadcasting its token."""
import hashlib
import hmac
import logging
import re
import socket
import threading
import time


class ReceiverDiscovery:
    def __init__(self, token, http_port=5000, host='0.0.0.0', port=5001):
        self.token = token.encode()
        self.http_port = http_port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, port))
        self.socket.settimeout(.5)
        self.port = self.socket.getsockname()[1]
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True, name='climaguard-discovery')

    def start(self):
        self.thread.start()

    def run(self):
        recent = {}
        while not self.stop.is_set():
            try:
                payload, peer = self.socket.recvfrom(256)
                match = re.fullmatch(rb'CLIMAGUARD_DISCOVER_V1 ([0-9a-f]{16})', payload)
                if not match:
                    continue
                now = time.monotonic()
                if now - recent.get(peer[0], -10) < 1:
                    continue
                if len(recent) > 256:
                    recent.clear()
                recent[peer[0]] = now
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
                    route.connect(peer)
                    local_ip = route.getsockname()[0]
                message = b'CLIMAGUARD_SERVER_V1 ' + match[1] + b' ' + str(self.http_port).encode() + b' ' + local_ip.encode()
                proof = hmac.new(self.token, message, hashlib.sha256).hexdigest().encode()
                self.socket.sendto(message + b' ' + proof, peer)
            except socket.timeout:
                continue
            except OSError:
                if not self.stop.is_set():
                    logging.exception('Falha na descoberta local da placa.')
                return

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
        self.socket.close()
