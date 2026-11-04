"""Private HTTPS access through an explicitly configured Tailscale Serve port."""
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time


class MobileRemote:
    def __init__(self, port=5003):
        self.port = port
        self.lock = threading.RLock()
        self.cached = None
        self.checked = 0

    def executable(self):
        path = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Tailscale' / 'tailscale.exe'
        return str(path) if path.is_file() else None

    def command(self, arguments, timeout=10):
        executable = self.executable()
        if not executable:
            raise ValueError('Instale o Tailscale neste computador e entre na sua conta pessoal.')
        return subprocess.run([executable, *arguments], capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=timeout,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def status(self, force=False):
        with self.lock:
            if not force and self.cached is not None and time.monotonic() - self.checked < 15:
                return dict(self.cached)
            result = dict(state='not_installed', ready=False, url='',
                          detail='Instale o Tailscale no computador e nos iPhones e entre na mesma conta pessoal.')
            try:
                if self.executable():
                    status = self.command(['status', '--json'])
                    value = json.loads(status.stdout) if status.returncode == 0 else {}
                    if value.get('BackendState') != 'Running':
                        result.update(state='login', detail='Abra o Tailscale no Windows e entre na sua conta. Use a mesma conta nos iPhones.')
                    else:
                        name = str(value.get('Self', {}).get('DNSName', '')).rstrip('.')
                        if not re.fullmatch(r'[a-z0-9-]+\.[a-z0-9.-]+\.ts\.net', name):
                            result.update(state='dns', detail='Ative o MagicDNS e o HTTPS na sua rede Tailscale.')
                        else:
                            url = f'https://{name}:8443'
                            serve = self.command(['serve', 'status', '--json'])
                            configuration = json.loads(serve.stdout) if serve.returncode == 0 else {}
                            handlers = configuration.get('Web', {}).get(f'{name}:8443', {}).get('Handlers', {})
                            target = handlers.get('/', {}).get('Proxy', '')
                            public = configuration.get('AllowFunnel', {}).get(f'{name}:8443') is True
                            ready = not public and target == f'http://127.0.0.1:{self.port}' and configuration.get('TCP', {}).get('8443', {}).get('HTTPS') is True
                            result.update(state='ready' if ready else 'configure', ready=ready, url=url,
                                          detail='Acesso privado pronto. Mantenha o Tailscale conectado nos iPhones.' if ready else 'Clique em Preparar acesso remoto para conectar o ClimaGuard ao Tailscale.')
            except (OSError, ValueError, AttributeError, TypeError, subprocess.TimeoutExpired):
                result.update(state='unavailable', detail='Não foi possível consultar o Tailscale. Confirme se ele está aberto e conectado.')
            self.cached, self.checked = result, time.monotonic()
            return dict(result)

    def enable(self):
        with self.lock:
            state = self.status(force=True)
            if state['ready']:
                return state
            if state['state'] != 'configure':
                raise ValueError(state['detail'])
            configuration = self.command(['serve', 'status', '--json'])
            value = json.loads(configuration.stdout) if configuration.returncode == 0 else {}
            # Keep other applications' listeners intact, including the default 443.
            occupied = any(key.endswith(':8443') for key in value.get('Web', {})) or '8443' in value.get('TCP', {}) or any(key.endswith(':8443') and enabled for key, enabled in value.get('AllowFunnel', {}).items())
            if occupied:
                raise ValueError('A porta HTTPS 8443 do Tailscale já atende outro serviço. A configuração existente foi preservada.')
            output = ''
            try:
                completed = self.command(['serve', '--bg', '--https=8443', f'http://127.0.0.1:{self.port}'], timeout=15)
                output = completed.stdout + '\n' + completed.stderr
            except subprocess.TimeoutExpired as error:
                # The CLI waits for the user after printing the HTTPS consent URL.
                for chunk in (error.stdout, error.stderr):
                    if chunk:
                        output += chunk.decode('utf-8', errors='replace') if isinstance(chunk, bytes) else chunk
            result = self.status(force=True)
            if result['ready']:
                return result
            consent = re.search(r'https://login\.tailscale\.com/[A-Za-z0-9_/?=&.%:-]+', output)
            if consent:
                result.update(state='approval', approval_url=consent.group(0), detail='Abra o link e autorize o HTTPS no Tailscale. Depois clique novamente em Preparar acesso remoto.')
                return result
            raise ValueError('O Tailscale ainda não liberou o HTTPS. Abra o Tailscale, confira a conexão e tente novamente.')
