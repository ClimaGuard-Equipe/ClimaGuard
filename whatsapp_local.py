"""Authenticated loopback bridge to the bundled WPPConnect runtime."""
import json
from http.client import HTTPConnection, HTTPException
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading


class WhatsAppLocal:
    def __init__(self, data_dir):
        self.directory = (Path(data_dir) / 'whatsapp-session').resolve()
        root = Path(__file__).resolve().parent
        self.helper = root / 'whatsapp_local' / 'bridge.js'
        self.runtime = root / 'whatsapp_runtime' if getattr(sys, 'frozen', False) else root / 'work' / 'whatsapp-runtime'
        self.node = self.runtime / 'node.exe'
        self.process = None
        self.secret = secrets.token_urlsafe(40)
        self.lock = threading.RLock()

    @staticmethod
    def browser_path():
        candidates = []
        for name in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            base = Path(os.environ.get(name, 'C:/Program Files'))
            candidates.extend([base / 'Google/Chrome/Application/chrome.exe', base / 'Microsoft/Edge/Application/msedge.exe'])
        return next((str(path) for path in candidates if path.is_file()), None)

    def available(self):
        return (self.node.is_file() and self.helper.is_file() and
                (self.helper.parent / 'node_modules/@wppconnect-team/wppconnect/package.json').is_file()
                and self.browser_path() is not None)

    def request(self, endpoint, data=None, timeout=4):
        if not self.process or self.process.poll() is not None:
            raise ValueError('Conecte o WhatsApp em Serviços de envio.')
        try:
            control = json.loads((self.directory / 'control.json').read_text())
            if control.get('pid') != self.process.pid or not 1 <= int(control['port']) <= 65535:
                raise ValueError('Aguarde a inicialização da conexão WhatsApp.')
            connection = HTTPConnection('127.0.0.1', int(control['port']), timeout=timeout)
            try:
                connection.request('POST' if data is not None else 'GET', endpoint,
                    body=json.dumps(data).encode() if data is not None else None,
                    headers={'Authorization': 'Bearer ' + self.secret, 'Content-Type': 'application/json'})
                response = connection.getresponse()
                result = json.loads(response.read(100000))
                if response.status >= 400:
                    raise ValueError(result.get('error') if isinstance(result, dict) else 'A conexão local recusou a operação WhatsApp.')
            finally:
                connection.close()
            if not isinstance(result, dict):
                raise ValueError('Resposta inválida da conexão WhatsApp.')
            return result
        except (OSError, HTTPException, KeyError, json.JSONDecodeError):
            raise ValueError('A conexão WhatsApp ainda não respondeu. Aguarde e tente novamente.') from None

    def status(self, qr=False):
        if not self.available():
            return {'state': 'unavailable', 'detail': 'Instale a versão atualizada do ClimaGuard e mantenha o Microsoft Edge ou Google Chrome instalado.'}
        if self.process and self.process.poll() is not None:
            return {'state': 'error', 'detail': 'A conexão local foi encerrada. Clique em Conectar WhatsApp para tentar novamente.'}
        if not self.process:
            return {'state': 'idle', 'detail': 'Clique em Conectar WhatsApp para começar.'}
        try:
            result = self.request('/status')
        except ValueError:
            result = {'state': 'starting', 'detail': 'Iniciando a conexão local com o WhatsApp…'}
        if not qr:
            result.pop('qr', None)
        return result

    def start(self):
        with self.lock:
            if not self.available():
                raise ValueError(self.status()['detail'])
            if not self.process or self.process.poll() is not None:
                self.directory.mkdir(parents=True, exist_ok=True)
                (self.directory / 'control.json').unlink(missing_ok=True)
                env = {key: value for key, value in os.environ.items() if key not in ('NODE_OPTIONS', 'NODE_PATH')}
                env.update(CLIMAGUARD_WPP_DATA=str(self.directory), CLIMAGUARD_WPP_SECRET=self.secret,
                           CLIMAGUARD_WPP_BROWSER=self.browser_path())
                self.process = subprocess.Popen([str(self.node), str(self.helper)], cwd=self.directory,
                    env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            # The short-lived thread keeps the web request responsive while Node loads.
            def connect():
                import time
                for _ in range(60):
                    try:
                        self.request('/connect', {})
                        return
                    except ValueError:
                        if not self.process or self.process.poll() is not None:
                            return
                        time.sleep(.5)
            threading.Thread(target=connect, daemon=True, name='climaguard-whatsapp-start').start()
        return self.status(qr=True)

    def send(self, job):
        result = self.request('/send', {'phone': job['destination'], 'message': job['message'],
            'requestId': f"{job['id']}-{int(job['created'])}"}, timeout=45)
        if not isinstance(result.get('id'), str) or not result['id'].startswith('wpp:'):
            raise ValueError('O WhatsApp não retornou um comprovante do envio.')
        return result['id']

    def delivery(self, provider_id):
        import re
        if not re.fullmatch(r'wpp:[0-9a-f-]{36}', provider_id):
            raise ValueError('Identificador WhatsApp inválido.')
        result = self.request('/delivery/' + provider_id[4:], timeout=12)
        if result.get('status') not in ('accepted', 'delivered', 'read', 'failed'):
            raise ValueError('Não foi possível confirmar o estado da entrega.')
        return result['status'], result.get('detail', '')

    def close(self):
        with self.lock:
            if not self.process:
                return
            process = self.process
            try:
                if process.poll() is None:
                    try:
                        self.request('/close', {}, timeout=2)
                    except ValueError:
                        pass
                    process.stdin.close()
                    process.wait(timeout=8)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=3)
            self.process = None
