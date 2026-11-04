"""Configure the physical board over USB and keep its private setup-network card."""
import base64
import io
import json
from pathlib import Path
import re
import threading
import time
import uuid

import qrcode
import serial
from serial.tools import list_ports

DEVICE_ID = re.compile(r'cg-[0-9a-f]{12}')
WIFI_ERRORS = {
    'storage_failed': 'A placa conectou, mas não conseguiu salvar a rede na memória. A configuração anterior foi mantida.',
    'network_not_found': 'O ESP32 não encontrou essa rede. Verifique se o compartilhamento está ligado e em 2,4 GHz, próximo à placa.',
    'handshake_timeout': 'A negociação de segurança com o Wi-Fi não terminou. No celular, confira a compatibilidade WPA2 e se novos aparelhos estão permitidos.',
    'authentication_failed': 'O ponto de acesso recusou a autenticação do ESP32. Confira a senha e se o celular permite conectar novos aparelhos.',
    'association_failed': 'O ponto de acesso recusou a conexão do ESP32. Confira o limite de aparelhos e a lista de dispositivos permitidos no celular.',
    'authentication_timeout': 'O ponto de acesso não respondeu à autenticação a tempo. Aproxime a placa e mantenha o compartilhamento do celular ativo.',
    'signal_lost': 'O ESP32 perdeu o sinal durante a conexão. Aproxime a placa do celular ou roteador e tente novamente.',
    'ip_timeout': 'O ESP32 entrou no Wi-Fi, mas não recebeu um IP. Confira o limite de aparelhos e o serviço DHCP do celular ou roteador.',
    'connection_timeout': 'A conexão não terminou no prazo. Mantenha o compartilhamento ativo, próximo à placa, e confira se novos aparelhos são permitidos.',
}


def validate_wifi(ssid, password):
    if not isinstance(ssid, str) or not 1 <= len(ssid.encode('utf-8')) <= 32 or any(ord(c) < 32 for c in ssid):
        raise ValueError('Informe o nome da rede com até 32 bytes, sem quebras de linha.')
    if not isinstance(password, str) or any(ord(c) < 32 for c in password):
        raise ValueError('Confira a senha do Wi-Fi.')
    length = len(password.encode('utf-8'))
    if length and not 8 <= length <= 63 and not (length == 64 and re.fullmatch(r'[0-9a-fA-F]{64}', password)):
        raise ValueError('A senha deve ter de 8 a 63 bytes. Para rede aberta, deixe vazia.')
    return ssid, password


class WifiProvision:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / '.wifi-setup-cards.json'
        self.lock = threading.Lock()

    def ports(self):
        return [p for p in list_ports.comports() if p.vid in (0x1A86, 0x10C4, 0x303A)]

    def exchange(self, command, fields=None, expected_id=None, timeout=40, port=None):
        if not self.lock.acquire(blocking=False):
            raise ValueError('Há uma configuração USB em andamento. Aguarde terminar.')
        try:
            ports = self.ports()
            if port is not None:
                if not isinstance(port, str) or not any(p.device == port for p in ports):
                    raise ValueError('A porta USB selecionada não está disponível. Atualize a lista e confira o cabo.')
                ports = [p for p in ports if p.device == port]
            if len(ports) != 1:
                raise ValueError('Conecte a placa por um cabo USB de dados e selecione a porta no aplicativo.')
            try:
                with serial.Serial(ports[0].device, 115200, timeout=.25, write_timeout=2) as connection:
                    boot_deadline = time.monotonic() + 9
                    device_id = None
                    while time.monotonic() < boot_deadline:
                        try:
                            value = json.loads(connection.readline(4096).decode('utf-8', errors='replace'))
                        except (ValueError, UnicodeError):
                            continue
                        if not isinstance(value, dict) or value.get('app') != 'ClimaGuard':
                            continue
                        if not isinstance(value.get('id'), str) or not DEVICE_ID.fullmatch(value['id']):
                            continue
                        device_id = value['id']
                        if expected_id and device_id != expected_id:
                            raise ValueError('A placa na USB não é a placa selecionada no painel.')
                        if not isinstance(value.get('wifi'), dict) or 'setup_ssid' not in value['wifi']:
                            raise ValueError('Esta placa precisa do firmware 1.4 ou superior para trocar o Wi-Fi pelo aplicativo.')
                        break
                    if not device_id:
                        raise ValueError('A placa não se identificou. Confira o cabo e feche o Monitor Serial do Arduino.')
                    request_id = uuid.uuid4().hex
                    request = {'command':command,'request_id':request_id, **(fields or {})}
                    connection.write((json.dumps(request,ensure_ascii=False)+'\n').encode('utf-8'))
                    connection.flush()
                    event = 'wifi_result' if command == 'set_wifi' else command
                    deadline = time.monotonic() + timeout
                    while time.monotonic() < deadline:
                        try:
                            value = json.loads(connection.readline(4096).decode('utf-8', errors='replace'))
                        except (ValueError, UnicodeError):
                            continue
                        if not isinstance(value, dict) or value.get('app') != 'ClimaGuard' or value.get('id') != device_id:
                            continue
                        if value.get('request_id') != request_id or value.get('event') != event:
                            continue
                        if value.get('ok') is not True:
                            code = value.get('error_code')
                            if isinstance(code, str) and code in WIFI_ERRORS:
                                raise ValueError(WIFI_ERRORS[code])
                            raise ValueError('A alteração não foi concluída. Confira nome, senha e Wi-Fi de 2,4 GHz. A rede anterior foi mantida.')
                        return value
                    raise ValueError('A resposta da placa não chegou. Confira a conexão USB e procure a placa na rede antes de tentar novamente; não foi possível confirmar a gravação.')
            except (serial.SerialException, OSError):
                raise ValueError('Não foi possível acessar a USB. Feche o Monitor Serial do Arduino e confira o cabo.') from None
        finally:
            self.lock.release()

    def cards(self):
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def card(self, device_id=None):
        cards = self.cards()
        if device_id:
            return cards.get(device_id)
        return next(iter(cards.values())) if len(cards) == 1 else None

    def capture_card(self, device_id=None, port=None):
        value = self.exchange('wifi_card', expected_id=device_id, timeout=5, port=port)
        ssid, password = value.get('ap_ssid'), value.get('ap_password')
        if not isinstance(ssid,str) or not ssid.startswith('ClimaGuard-') or len(ssid.encode()) > 32:
            raise ValueError('A placa não forneceu um cartão de configuração válido.')
        validate_wifi(ssid,password)
        def escape(value):
            return ''.join('\\'+c if c in '\\;,:"' else c for c in value)
        encoded = f'WIFI:T:WPA;S:{escape(ssid)};P:{escape(password)};;'
        qr = qrcode.make(encoded)
        buffer = io.BytesIO()
        qr.save(buffer, format='PNG')
        card = dict(id=value['id'],ssid=ssid,password=password,portal_url='http://192.168.4.1/',
                    qr='data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode())
        cards = self.cards(); cards[value['id']] = card
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(cards),encoding='utf-8')
        temporary.replace(self.path)
        return card

    def configure(self, ssid, password, device_id=None, port=None):
        ssid,password = validate_wifi(ssid,password)
        if not self.card(device_id):
            card = self.capture_card(device_id, port=port)
            device_id = card['id']
        value = self.exchange('set_wifi',{'ssid':ssid,'password':password},expected_id=device_id,port=port)
        return {'ok':True,'ssid':ssid,'ip':value.get('ip',''),
                'message':'Rede salva na placa. Conecte o computador à mesma rede e use Procurar placa.'}

    def open_portal(self, device_id=None, port=None):
        card = self.card(device_id) or self.capture_card(device_id, port=port)
        self.exchange('wifi_portal',expected_id=card['id'],timeout=5,port=port)
        return card
