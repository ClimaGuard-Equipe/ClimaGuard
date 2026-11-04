"""Read-only iPhone companion, isolated from desktop configuration and sending APIs."""
from collections import deque
import hashlib
import io
import json
from pathlib import Path
import re
import secrets
import threading
import time

from flask import Flask, jsonify, request, send_from_directory
import qrcode

ROOT = Path(__file__).resolve().parent
COOKIE = 'climaguard_mobile'


class MobileCompanion:
    def __init__(self, data_dir, store, network, remote):
        self.path = Path(data_dir) / '.mobile-devices.json'
        self.store, self.network, self.remote = store, network, remote
        self.lock = threading.RLock()
        self.pending = {}
        self.failures = deque()
        self.devices = {}
        self.available = False
        self.error = ''
        try:
            saved = json.loads(self.path.read_text(encoding='utf-8'))
            for key, value in saved.get('devices', {}).items():
                if (re.fullmatch(r'[0-9a-f]{64}', key) and isinstance(value, dict)
                    and type(value.get('user_id')) is int and isinstance(value.get('expires'), (int, float))
                    and isinstance(value.get('name'), str) and re.fullmatch(r'[0-9a-f]{16}', str(value.get('id', '')))
                    and value['expires'] > time.time()):
                    self.devices[key] = value
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        self.app = self.create_app()

    def save(self):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'version': 1, 'devices': self.devices}), encoding='utf-8')
        temporary.replace(self.path)

    def access(self, user_id):
        with self.lock:
            devices = [dict(id=v['id'], name=v['name'], created=v['created'], expires=v['expires'])
                       for v in self.devices.values() if v['user_id'] == user_id and v['expires'] > time.time()]
        return dict(devices=devices, remote=self.remote.status(), available=self.available, error=self.error)

    def issue(self, user_id):
        if not self.available:
            raise ValueError(self.error or 'O serviço do iPhone ainda não está disponível. Reinicie o ClimaGuard.')
        remote = self.remote.status(force=True)
        if not remote['ready']:
            raise ValueError('Prepare primeiro o acesso remoto pelo Tailscale.')
        with self.lock:
            now = time.time()
            self.pending = {key: value for key, value in self.pending.items() if value['expires'] > now and value['user_id'] != user_id}
            if len([v for v in self.devices.values() if v['user_id'] == user_id and v['expires'] > now]) >= 12:
                raise ValueError('Você já autorizou 12 aparelhos. Remova um antes de adicionar outro.')
            while True:
                code = f'{secrets.randbelow(100_000_000):08d}'
                digest = hashlib.sha256(code.encode()).hexdigest()
                if digest not in self.pending:
                    break
            self.pending[digest] = dict(user_id=user_id, expires=now + 300)
        url = remote['url'] + '/#code=' + code
        output = io.BytesIO()
        qrcode.make(url).save(output, format='PNG')
        import base64
        return dict(code=code, expires=now + 300, url=url, base_url=remote['url'] + '/',
                    qr='data:image/png;base64,' + base64.b64encode(output.getvalue()).decode())

    def pair(self, code, name):
        with self.lock:
            now = time.time()
            while self.failures and self.failures[0] < now - 60:
                self.failures.popleft()
            if len(self.failures) >= 8:
                raise ValueError('Aguarde um minuto antes de tentar outro código.')
            code = re.sub(r'[\s-]', '', code) if isinstance(code, str) else ''
            digest = hashlib.sha256(code.encode()).hexdigest()
            entry = self.pending.get(digest) if re.fullmatch(r'[0-9]{8}', code) else None
            if not entry or entry['expires'] <= now:
                self.failures.append(now)
                raise ValueError('Código inválido ou expirado. Gere outro no ClimaGuard do computador.')
            name = name.strip() if isinstance(name, str) else ''
            if not 1 <= len(name) <= 60 or any(ord(c) < 32 for c in name):
                raise ValueError('Informe um nome para este iPhone, com até 60 caracteres.')
            if not self.store.user(entry['user_id']):
                raise ValueError('A conta deste código não está mais disponível.')
            self.devices = {k: v for k, v in self.devices.items() if v['expires'] > now}
            if len(self.devices) >= 64 or sum(v['user_id'] == entry['user_id'] for v in self.devices.values()) >= 12:
                raise ValueError('Limite de aparelhos atingido. Remova um aparelho pelo computador.')
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            self.devices[token_hash] = dict(id=secrets.token_hex(8), user_id=entry['user_id'], name=name,
                                            created=now, expires=now + 30 * 86400)
            try:
                self.save()
            except OSError:
                del self.devices[token_hash]
                raise ValueError('Não foi possível salvar este aparelho. Confira o espaço no computador.') from None
            del self.pending[digest]
            return token

    def authenticate(self):
        token = request.cookies.get(COOKIE, '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            return None
        with self.lock:
            device = self.devices.get(hashlib.sha256(token.encode()).hexdigest())
            if not device or device['expires'] <= time.time():
                return None
            return dict(device) if self.store.user(device['user_id']) else None

    def revoke(self, user_id, device_id):
        with self.lock:
            selected = [key for key, value in self.devices.items() if value['user_id'] == user_id and value['id'] == device_id]
            if not selected:
                raise ValueError('Este aparelho não está na sua lista.')
            previous = dict(self.devices)
            for key in selected:
                del self.devices[key]
            try:
                self.save()
            except OSError:
                self.devices = previous
                raise

    def create_app(self):
        app = Flask('climaguard-mobile', static_folder=None)
        app.config['MAX_CONTENT_LENGTH'] = 4096

        @app.before_request
        def protect():
            if request.method == 'POST':
                if request.headers.get('X-ClimaGuard-Mobile') != '1' or not request.is_json:
                    return jsonify(error='Abra o ClimaGuard pelo ícone ou pelo Safari.'), 403
                origin = request.headers.get('Origin', '')
                expected = self.remote.status().get('url', '')
                if origin and origin.rstrip('/') not in (expected, 'http://' + request.host, 'https://' + request.host):
                    return jsonify(error='Origem inválida.'), 403
                if request.headers.get('Sec-Fetch-Site') == 'cross-site':
                    return jsonify(error='Origem inválida.'), 403

        @app.after_request
        def headers(response):
            response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                                     'X-Frame-Options': 'DENY', 'Referrer-Policy': 'no-referrer',
                                     'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
            return response

        @app.errorhandler(413)
        def too_large(_):
            return jsonify(error='Dados muito grandes.'), 413

        @app.get('/')
        def home():
            return send_from_directory(ROOT / 'mobile_assets', 'index.html')

        @app.get('/assets/<path:filename>')
        def assets(filename):
            return send_from_directory(ROOT / 'mobile_assets', filename)

        @app.get('/manifest.webmanifest')
        def manifest():
            response = jsonify(id='/', name='ClimaGuard', short_name='ClimaGuard', lang='pt-BR',
                               start_url='/', scope='/', display='standalone', orientation='any',
                               theme_color='#123c35', background_color='#f2f6f3',
                               icons=[dict(src=f'/assets/icon-{size}.png', sizes=f'{size}x{size}', type='image/png', purpose='any') for size in (192, 512)])
            response.mimetype = 'application/manifest+json'
            return response

        @app.get('/sw.js')
        def worker():
            response = send_from_directory(ROOT / 'mobile_assets', 'sw.js')
            response.headers['Service-Worker-Allowed'] = '/'
            return response

        @app.post('/api/pair')
        def pair():
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return jsonify(error='Informe o código exibido no computador.'), 400
            try:
                token = self.pair(data.get('code'), data.get('name', 'Meu iPhone'))
            except ValueError as error:
                return jsonify(error=str(error)), 400
            response = jsonify(ok=True)
            response.set_cookie(COOKIE, token, httponly=True, secure=True, samesite='Strict', max_age=30 * 86400)
            return response

        @app.get('/api/status')
        def status():
            device = self.authenticate()
            if not device:
                return jsonify(error='Autorize este iPhone com o código exibido no computador.'), 401
            user_id = device['user_id']
            snapshot = self.store.snapshot(user_id, 'real')
            connection = self.network.snapshot()
            online = connection['online'] if connection['selected'] else snapshot['device_online']
            preferences = self.store.preferences(user_id)
            alerts = [{key: row[key] for key in ('id', 'created', 'kind', 'channel', 'status', 'detail', 'message', 'source')}
                      for row in self.store.alert_history(user_id) if row['source'] != 'demo'][:15]
            return jsonify(latest=snapshot['latest'], history=snapshot['history'][-60:], online=online,
                           connection=dict(label=connection['label'], model=(connection['device'] or {}).get('model', 'Placa')),
                           preferences={key: preferences[key] for key in ('enabled', 'threshold', 'temperature_enabled', 'power_enabled', 'channels')},
                           alerts=alerts, device_name=device['name'], server_time=time.time())

        @app.post('/api/logout')
        def logout():
            device = self.authenticate()
            if device:
                self.revoke(device['user_id'], device['id'])
            response = jsonify(ok=True)
            response.delete_cookie(COOKIE, secure=True, httponly=True, samesite='Strict')
            return response

        return app
