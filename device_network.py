"""Discover sensor boards on every LAN adapter and read their local telemetry."""
import ipaddress
import json
import logging
from http.client import HTTPConnection
from pathlib import Path
import re
import secrets
import select
import socket
import threading
import time

import psutil

from storage import validate_reading

DEVICE_ID = re.compile(r'cg-[0-9a-f]{12}')
POLL_INTERVAL = .2


def lan_interfaces():
    result = []
    stats = psutil.net_if_stats()
    for name, addresses in psutil.net_if_addrs().items():
        if name not in stats or not stats[name].isup:
            continue
        for address in addresses:
            if address.family != socket.AF_INET or not address.netmask:
                continue
            try:
                interface = ipaddress.IPv4Interface(f'{address.address}/{address.netmask}')
            except ValueError:
                continue
            if interface.ip.is_loopback or interface.ip.is_link_local or interface.network.prefixlen >= 31:
                continue
            result.append(dict(name=name, ip=str(interface.ip), network=str(interface.network),
                               broadcast=str(interface.network.broadcast_address)))
    return result


class DeviceNetwork:
    def __init__(self, data_dir, receive, interfaces=lan_interfaces, device_port=80, discovery_port=5002):
        self.path = Path(data_dir) / 'device-network.json'
        self.receive = receive
        self.interfaces = interfaces
        self.device_port = device_port
        self.discovery_port = discovery_port
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.scan_wake = threading.Event()
        self.stop = threading.Event()
        self.thread = None
        self.discovery_thread = None
        self.adapters = []
        self.devices = {}
        self.selected = None
        self.last_sample = None
        self.last_contact = None
        self.cursor = None
        self.scanning = False
        self.last_scan = None
        self.error = ''
        self.manual = None
        try:
            saved = json.loads(self.path.read_text(encoding='utf-8'))
            if DEVICE_ID.fullmatch(saved.get('id', '')) and isinstance(saved.get('ip'), str):
                self.selected = saved['id']
                self.devices[self.selected] = dict(saved, model='Placa', seen=0)
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def start(self):
        if self.thread:
            return
        self.thread = threading.Thread(target=self.run, daemon=True, name='climaguard-device-network')
        self.thread.start()
        self.discovery_thread = threading.Thread(target=self.scan_loop, daemon=True, name='climaguard-discovery')
        self.discovery_thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        self.scan_wake.set()
        if self.thread:
            self.thread.join(timeout=5)
        if self.discovery_thread:
            self.discovery_thread.join(timeout=5)

    def request_scan(self):
        with self.lock:
            self.last_scan = None
        self.wake.set()
        self.scan_wake.set()

    def select_device(self, device_id):
        with self.lock:
            if device_id not in self.devices:
                raise ValueError('A placa não está na lista. Procure novamente.')
            if device_id != self.selected:
                self.last_sample = self.last_contact = self.cursor = None
            self.selected = device_id
            self.save_selection()
        self.wake.set()

    def save_selection(self):
        device = self.devices[self.selected]
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'id': self.selected, 'ip': device['ip']}), encoding='utf-8')
        temporary.replace(self.path)

    def local_address(self, address):
        try:
            ip = ipaddress.IPv4Address(address)
        except (ValueError, TypeError):
            raise ValueError('Informe somente o IP local da placa, como 192.168.1.237.') from None
        adapters = self.interfaces()
        if ip.is_unspecified or ip.is_multicast or not any(
            ip in ipaddress.IPv4Network(item['network']) and
            ip not in (ipaddress.IPv4Network(item['network']).network_address,
                       ipaddress.IPv4Network(item['network']).broadcast_address)
            for item in adapters
        ):
            raise ValueError('O IP precisa pertencer à rede local deste computador.')
        return str(ip)

    def connect_address(self, address):
        address = self.local_address(address)
        with self.lock:
            self.manual = address
            self.error = ''
        self.wake.set()

    def discover(self):
        nonce = secrets.token_hex(8)
        sockets = []
        with self.lock:
            self.scanning = True
        try:
            adapters = self.interfaces()
            with self.lock:
                self.adapters = adapters
            for adapter in adapters:
                connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    connection.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    connection.bind((adapter['ip'], 0))
                    connection.setblocking(False)
                    request = f'CLIMAGUARD_FIND_V2 {nonce}'.encode()
                    connection.sendto(request, (adapter['broadcast'], self.discovery_port))
                    sockets.append(connection)
                except OSError:
                    connection.close()
            end = time.monotonic() + 1.2
            while sockets and not self.stop.is_set() and time.monotonic() < end:
                ready, _, _ = select.select(sockets, [], [], min(.2, max(0, end - time.monotonic())))
                for connection in ready:
                    payload, peer = connection.recvfrom(1025)
                    try:
                        if len(payload) > 1024:
                            continue
                        device = json.loads(payload)
                        if not isinstance(device, dict) or device.get('app') != 'ClimaGuard' or device.get('protocol') != 2:
                            continue
                        if device.get('nonce') != nonce or device.get('port') != self.device_port:
                            continue
                        if not isinstance(device.get('id'), str) or not DEVICE_ID.fullmatch(device['id']):
                            continue
                        if device.get('model') not in ('ESP8266', 'ESP32'):
                            continue
                        address = self.local_address(peer[0])
                        with self.lock:
                            self.devices = {key: item for key, item in self.devices.items()
                                            if key == self.selected or time.time() - item['seen'] < 120}
                            if device['id'] not in self.devices and len(self.devices) >= 64:
                                continue
                            self.devices[device['id']] = dict(id=device['id'], ip=address,
                                                              model=device['model'], seen=time.time())
                    except (ValueError, TypeError, AttributeError):
                        continue
            with self.lock:
                # Do not silently switch to a different board if a selected board disappears.
                candidates = [key for key, item in self.devices.items() if time.time() - item['seen'] < 60]
                if not self.selected and len(candidates) == 1:
                    self.selected = candidates[0]
                    self.save_selection()
                elif self.selected in candidates:
                    self.save_selection()
        finally:
            for connection in sockets:
                connection.close()
            with self.lock:
                self.scanning = False
                self.last_scan = time.time()

    def read_device(self, address):
        address = self.local_address(address)
        connection = HTTPConnection(address, self.device_port, timeout=2)
        try:
            connection.request('GET', '/climaguard/status', headers={'Accept': 'application/json'})
            response = connection.getresponse()
            payload = response.read(2049)
            if response.status != 200 or len(payload) > 2048:
                raise ValueError('A placa não respondeu com uma leitura válida.')
            value = json.loads(payload)
        finally:
            connection.close()
        if not isinstance(value, dict) or value.get('app') != 'ClimaGuard' or value.get('protocol') != 2:
            raise ValueError('O endereço não respondeu como uma placa ClimaGuard atualizada.')
        if not isinstance(value.get('id'), str) or not DEVICE_ID.fullmatch(value['id']):
            raise ValueError('Identificação da placa inválida.')
        if value.get('model') not in ('ESP8266', 'ESP32') or not re.fullmatch(r'[0-9a-f]{16}', str(value.get('boot_id', ''))):
            raise ValueError('Identificação do firmware inválida.')
        if type(value.get('sequence')) is not int or value['sequence'] < 1:
            raise ValueError('A placa ainda está iniciando as medições.')
        if type(value.get('sample_age_ms')) is not int or not 0 <= value['sample_age_ms'] < 15000:
            raise ValueError('A placa está respondendo, mas a leitura não foi atualizada.')
        validate_reading(value)
        return value

    def poll(self):
        with self.lock:
            manual, self.manual = self.manual, None
            selected = self.selected
            device = dict(self.devices[selected]) if selected in self.devices else None
        if not manual and not device:
            return
        value = self.read_device(manual or device['ip'])
        if not manual and value['id'] != selected:
            raise ValueError('O IP agora pertence a outra placa. Procurando a placa selecionada.')
        with self.lock:
            if manual:
                self.devices[value['id']] = dict(id=value['id'], ip=manual, model=value['model'], seen=time.time())
                if value['id'] != self.selected:
                    self.last_sample = self.last_contact = self.cursor = None
                self.selected = value['id']
                self.save_selection()
            elif self.selected != selected:
                return
            self.devices[self.selected].update(model=value['model'], seen=time.time())
            power = value.get('power')
            allowed_power_states = ('disabled', 'starting', 'no_signal', 'clipped', 'timing',
                                    'unstable', 'adc_error', 'present', 'absent')
            if (value['model'] == 'ESP32' and isinstance(power, dict) and power.get('type') == 'ZMPT101B'
                    and power.get('state') in allowed_power_states
                    and all(type(power.get(key)) is bool for key in ('enabled', 'valid', 'calibrated'))):
                self.devices[self.selected]['power'] = {key: power[key] for key in
                                                       ('type', 'state', 'enabled', 'valid', 'calibrated')}
            else:
                self.devices[self.selected].pop('power', None)
            wifi = value.get('wifi')
            if isinstance(wifi,dict) and isinstance(wifi.get('ssid'),str) and len(wifi['ssid'].encode()) <= 32:
                self.devices[self.selected]['wifi_ssid'] = wifi['ssid']
                self.devices[self.selected]['wifi_configurable'] = isinstance(wifi.get('setup_ssid'),str)
            cursor = (value['id'], value['boot_id'], value['sequence'])
            now = time.time()
            self.last_contact = now
            self.error = ''
            if self.cursor and cursor[:2] == self.cursor[:2] and cursor[2] <= self.cursor[2]:
                return
            self.receive(validate_reading(value))
            self.cursor = cursor
            self.last_sample = now - value['sample_age_ms'] / 1000

    def scan_loop(self):
        # A broadcast search waits for replies; it must not delay live readings.
        while not self.stop.is_set():
            self.scan_wake.clear()
            try:
                self.discover()
            except (OSError, ValueError):
                logging.info('Busca da placa será repetida.')
            except Exception:
                logging.exception('Falha temporária na busca da placa.')
            self.wake.set()
            self.scan_wake.wait(20)

    def run(self):
        while not self.stop.is_set():
            self.wake.clear()
            try:
                if not self.stop.is_set():
                    self.poll()
            except (OSError, ValueError) as error:
                with self.lock:
                    self.error = str(error) if isinstance(error, ValueError) else 'A placa não respondeu. Confira a alimentação e a rede local.'
            except Exception:
                logging.exception('Falha temporária na busca da placa.')
                with self.lock:
                    self.error = 'Não foi possível consultar a placa. A busca será repetida.'
            self.wake.wait(POLL_INTERVAL)

    def snapshot(self):
        with self.lock:
            now = time.time()
            device = self.devices.get(self.selected)
            online = self.last_sample is not None and now - self.last_sample < 20
            candidates = [dict(item) for item in self.devices.values() if now - item['seen'] < 60 or item['id'] == self.selected]
            if online:
                state, label = 'connected', 'Placa conectada'
            elif self.last_sample is not None:
                state, label = 'offline', 'Sem comunicação com a placa'
            elif not self.adapters and self.last_scan is not None:
                state, label = 'no_network', 'Sem rede local disponível'
            elif not self.selected and len(candidates) > 1:
                state, label = 'choose', 'Escolha uma placa'
            elif device and now - device['seen'] < 60:
                state, label = 'found', 'Placa encontrada; aguardando leitura'
            else:
                state, label = 'searching', 'Procurando a placa na rede'
            return dict(state=state, label=label, online=online, scanning=self.scanning,
                        selected=self.selected, device=dict(device) if device else None,
                        devices=candidates, interfaces=list(self.adapters), last_scan=self.last_scan,
                        last_contact=self.last_contact, last_sample=self.last_sample, error=self.error)
