"""Outbound providers. Real network calls happen only for explicitly enabled jobs."""
import base64
import json
import os
import re
import threading
from email.utils import parseaddr
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FIELDS = ('RESEND_API_KEY', 'RESEND_FROM', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN',
          'TWILIO_SMS_FROM', 'TWILIO_WHATSAPP_FROM', 'TWILIO_WHATSAPP_CONTENT_SID',
          'TWILIO_WHATSAPP_CONTENT_VARIABLES', 'TWILIO_MODE', 'WHATSAPP_PROVIDER')
SECRET_FIELDS = ('RESEND_API_KEY', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN')
WHATSAPP_TEMPLATE_FIELDS = ('TWILIO_WHATSAPP_CONTENT_SID', 'TWILIO_WHATSAPP_CONTENT_VARIABLES')


def whatsapp_variables_text(config):
    # Preserve the mapping used by existing installations; new settings can use {}.
    default = '{}' if config.get('TWILIO_MODE') == 'trial' else '{"1":"{message}"}'
    return config.get('TWILIO_WHATSAPP_CONTENT_VARIABLES', default) or '{}'


def whatsapp_variables(config, message=None):
    try:
        values = json.loads(whatsapp_variables_text(config))
    except (ValueError, TypeError):
        raise ValueError('As variáveis do modelo WhatsApp devem ser um objeto JSON, como {"1":"{message}"}.') from None
    if not isinstance(values, dict) or len(values) > 100:
        raise ValueError('Informe um objeto JSON com até 100 variáveis para o modelo WhatsApp.')
    result = {}
    for key, value in values.items():
        if not re.fullmatch(r'[A-Za-z0-9]{1,16}', key) or not isinstance(value, str):
            raise ValueError('As variáveis WhatsApp precisam de chaves alfanuméricas e valores de texto.')
        if message is not None:
            value = value.replace('{message}', message)
        if not value.strip() or len(value) > 1600 or any(ord(ch) < 32 for ch in value) or '     ' in value:
            raise ValueError('Revise as variáveis WhatsApp: use texto não vazio, sem quebras de linha, tabulações ou mais de quatro espaços seguidos, com até 1600 caracteres.')
        result[key] = value
    return result


class Providers:
    def __init__(self, path, transport=None, whatsapp_local=None):
        self.path, self.transport = path, transport or urlopen
        self.lock = threading.Lock()
        self.values = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        self.whatsapp_local = whatsapp_local

    def config(self):
        with self.lock:
            data = dict(self.values)
        for field in FIELDS:
            if os.environ.get(field):
                data[field] = os.environ[field]
        return data

    def live_enabled(self):
        return self.config().get('live_enabled') is True

    def ready(self, channel):
        return self.configuration_error(channel) is None

    def configuration_error(self, channel):
        c = self.config()
        if channel == 'email':
            return None if c.get('RESEND_API_KEY') and c.get('RESEND_FROM') else 'Configure a chave e o remetente do e-mail em Serviços de envio.'
        if channel not in ('sms', 'whatsapp'):
            return 'Canal de envio inválido.'
        if channel == 'whatsapp' and c.get('WHATSAPP_PROVIDER') == 'wppconnect':
            if self.whatsapp_local is None:
                return 'A conexão local WhatsApp não está disponível neste aplicativo.'
            status = self.whatsapp_local.status()
            return None if status['state'] == 'connected' else status['detail']
        if not c.get('TWILIO_ACCOUNT_SID') or not c.get('TWILIO_AUTH_TOKEN'):
            return 'Configure o Account SID e o Auth Token da Twilio em Serviços de envio.'
        field = 'TWILIO_SMS_FROM' if channel == 'sms' else 'TWILIO_WHATSAPP_FROM'
        if not c.get(field):
            return 'Configure o remetente de WhatsApp mostrado pela Twilio (ele pode ser diferente do número de SMS).' if channel == 'whatsapp' else 'Configure o número remetente de SMS.'
        if channel == 'whatsapp' and c.get('TWILIO_MODE') == 'trial' and not c.get('TWILIO_WHATSAPP_CONTENT_SID'):
            return 'WhatsApp de teste pendente: vincule seu celular em Try out WhatsApp na Twilio e copie o ContentSid (HX...) da requisição de teste. A verificação por SMS não substitui essa vinculação.'
        return None

    def summary(self, admin=False):
        c = self.config()
        result = {'live_enabled': c.get('live_enabled') is True,
                  'ready': {key: self.ready(key) for key in ('email', 'sms', 'whatsapp')}}
        if admin:
            result['fields'] = {k: c.get(k, '') for k in FIELDS if k not in SECRET_FIELDS}
            result['fields']['TWILIO_MODE'] = c.get('TWILIO_MODE', 'standard')
            result['fields']['WHATSAPP_PROVIDER'] = c.get('WHATSAPP_PROVIDER', 'twilio')
            result['fields']['TWILIO_WHATSAPP_CONTENT_VARIABLES'] = whatsapp_variables_text(c)
            result['saved'] = {k: bool(c.get(k)) for k in SECRET_FIELDS}
        return result

    def save(self, data):
        with self.lock:
            c = dict(self.values)
            for field in FIELDS:
                if field not in data:
                    continue
                value = data.get(field, '')
                limit = 4096 if field == 'TWILIO_WHATSAPP_CONTENT_VARIABLES' else 512
                if not isinstance(value, str) or len(value) > limit or any(ord(ch) < 32 for ch in value):
                    raise ValueError('Revise os dados do serviço.')
                value = value.strip()
                # Empty passwords keep their saved values. Template fields can be cleared.
                if value or field in WHATSAPP_TEMPLATE_FIELDS:
                    c[field] = value
            if c.get('TWILIO_ACCOUNT_SID') and not re.fullmatch(r'AC[0-9a-fA-F]{32}', c['TWILIO_ACCOUNT_SID']):
                raise ValueError('O Account SID da Twilio deve começar com AC e ter 34 caracteres.')
            if c.get('TWILIO_MODE', 'standard') not in ('standard', 'trial'):
                raise ValueError('Selecione o modo de conta Twilio.')
            if c.get('WHATSAPP_PROVIDER', 'twilio') not in ('twilio', 'wppconnect'):
                raise ValueError('Selecione o serviço de WhatsApp.')
            if c.get('TWILIO_WHATSAPP_CONTENT_SID') and not re.fullmatch(r'HX[0-9a-fA-F]{32}', c['TWILIO_WHATSAPP_CONTENT_SID']):
                raise ValueError('O identificador do modelo WhatsApp deve começar com HX.')
            whatsapp_variables(c)
            for key in ('TWILIO_SMS_FROM', 'TWILIO_WHATSAPP_FROM'):
                if c.get(key) and not re.fullmatch(r'\+[1-9]\d{6,14}', c[key].removeprefix('whatsapp:')):
                    raise ValueError('Informe o remetente Twilio com +, país e número.')
            if c.get('RESEND_FROM') and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', parseaddr(c['RESEND_FROM'])[1]):
                raise ValueError('Informe um e-mail de remetente válido para o Resend.')
            if type(data.get('live_enabled', False)) is not bool:
                raise ValueError('Revise a ativação dos envios.')
            c['live_enabled'] = data.get('live_enabled', False)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(c), encoding='utf-8')
            temporary.replace(self.path)
            self.values = c

    def send(self, job):
        channel, destination, message = job['channel'], job['destination'], job['message']
        c = self.config()
        if not self.live_enabled():
            raise ValueError('Envios reais desativados pelo administrador.')
        problem = self.configuration_error(channel)
        if problem:
            raise ValueError(problem)
        if channel == 'whatsapp' and c.get('WHATSAPP_PROVIDER') == 'wppconnect':
            return self.whatsapp_local.send(job)
        if channel == 'email':
            body = json.dumps({'from': c['RESEND_FROM'], 'to': [destination],
                               'subject': 'ClimaGuard • ' + ('Teste de envio' if job['kind'] == 'test' else 'Alerta do ambiente'),
                               'text': message}, ensure_ascii=False).encode('utf-8')
            req = Request('https://api.resend.com/emails', data=body, headers={
                'Authorization': 'Bearer ' + c['RESEND_API_KEY'], 'Content-Type': 'application/json',
                'Idempotency-Key': f"climaguard-{job['id']}-{int(job['created'])}"})
        else:
            trial = c.get('TWILIO_MODE') == 'trial'
            if trial and job['kind'] != 'test':
                raise ValueError('A conta de teste Twilio aceita mensagens predefinidas, sem o texto real do alerta. Use e-mail para alertas reais ou configure uma conta Twilio com envio personalizado liberado.')
            sid, token = c['TWILIO_ACCOUNT_SID'], c['TWILIO_AUTH_TOKEN']
            sender = c['TWILIO_SMS_FROM' if channel == 'sms' else 'TWILIO_WHATSAPP_FROM']
            body = {'From': sender, 'To': destination}
            if channel == 'whatsapp':
                body.update(From='whatsapp:' + sender.removeprefix('whatsapp:'), To='whatsapp:' + destination)
                if c.get('TWILIO_WHATSAPP_CONTENT_SID'):
                    body['ContentSid'] = c['TWILIO_WHATSAPP_CONTENT_SID']
                    if not trial:
                        variables = whatsapp_variables(c)
                        if job['kind'] != 'test' and not any('{message}' in value for value in variables.values()):
                            raise ValueError('O modelo WhatsApp precisa de {message} nas variáveis para incluir o alerta real. Modelos com texto fixo servem somente para testar o canal.')
                        if variables:
                            body['ContentVariables'] = json.dumps(whatsapp_variables(c, message), ensure_ascii=False)
                else:
                    body['Body'] = message
            else:
                if trial:
                    body['Body'] = 'sms_appointment_reminders'
                else:
                    body['Body'] = message
            req = Request(f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json', data=urlencode(body).encode(), headers={
                'Authorization': 'Basic ' + base64.b64encode(f'{sid}:{token}'.encode()).decode(),
                'Content-Type': 'application/x-www-form-urlencoded'})
        data = self.request_json(req, channel, c)
        if channel == 'whatsapp' and data.get('status') in ('failed', 'undelivered'):
            raise ValueError(self.twilio_error(c, data.get('error_code'), data.get('error_message')))
        return str(data.get('id') or data.get('sid') or '')

    def whatsapp_delivery(self, job):
        c = self.config()
        message_sid = job.get('provider_id') or ''
        if job['channel'] == 'whatsapp' and message_sid.startswith('wpp:'):
            if self.whatsapp_local is None:
                raise ValueError('A conexão local WhatsApp não está disponível.')
            return self.whatsapp_local.delivery(message_sid)
        if job['channel'] != 'whatsapp' or not re.fullmatch(r'(SM|MM)[0-9a-fA-F]{32}', message_sid):
            raise ValueError('Este aviso não tem um identificador de mensagem WhatsApp para consulta.')
        sid, token = c.get('TWILIO_ACCOUNT_SID'), c.get('TWILIO_AUTH_TOKEN')
        if not sid or not token:
            raise ValueError('Configure as credenciais Twilio para consultar a entrega.')
        req = Request(f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages/{message_sid}.json', headers={
            'Authorization': 'Basic ' + base64.b64encode(f'{sid}:{token}'.encode()).decode()})
        data = self.request_json(req, 'whatsapp', c)
        status = data.get('status')
        if status in ('failed', 'undelivered', 'canceled'):
            return 'failed', self.twilio_error(c, data.get('error_code'), data.get('error_message'))
        if status == 'read':
            return 'read', 'A Twilio confirmou que a mensagem foi lida no WhatsApp.'
        if status == 'delivered':
            return 'delivered', 'A Twilio confirmou a entrega da mensagem no WhatsApp.'
        if status in ('accepted', 'queued', 'sending', 'sent', 'scheduled'):
            return 'accepted', 'Mensagem em processamento na Twilio. A entrega ainda não foi confirmada; consulte novamente em instantes.'
        raise ValueError('A Twilio não retornou um estado de entrega reconhecido. Consulte os logs na sua conta.')

    @staticmethod
    def twilio_error(config, code, message='', http_status=None):
        code = str(code or '')
        code = code if code.isdigit() else ''
        message = str(message or 'A mensagem não foi entregue. Consulte os logs da Twilio.')
        for field in SECRET_FIELDS:
            if config.get(field):
                message = message.replace(config[field], '[credencial ocultada]')
        message = re.sub(r'(?i)(Basic|Bearer)\s+[A-Za-z0-9+/=._-]+', r'\1 [credencial ocultada]', message)
        message = ' '.join(message.split())[:500]
        hints = {
            '63007': 'Use o remetente habilitado para WhatsApp mostrado na mesma conta Twilio; o número de SMS pode ser diferente.',
            '63015': 'Vincule o celular destinatário ao Sandbox enviando o join indicado pela Twilio. No Sandbox legado, a vinculação expira após três dias.',
            '63016': 'A janela de 24 horas terminou. Envie uma mensagem do celular para o remetente WhatsApp e tente novamente, ou configure um modelo aprovado com ContentSid.',
            '21656': 'Confira se as variáveis JSON correspondem às variáveis do modelo. No novo trial, use somente o ContentSid fornecido pela Twilio, sem variáveis.',
            '21608': 'Verifique o telefone destinatário na conta de teste da Twilio.',
            '20003': 'Confira o Account SID e o Auth Token da conta que possui esse remetente.',
        }
        context = ([f'HTTP {http_status}'] if http_status else []) + ([f'código {code}'] if code else [])
        suffix = ' (' + ', '.join(context) + ')' if context else ''
        hint = (' ' + hints[code]) if code in hints else ''
        return f'Twilio recusou o envio ou a entrega{suffix}: {message}{hint}'

    def request_json(self, req, channel, c):
        req.add_header('Accept', 'application/json')
        req.add_header('User-Agent', 'ClimaGuard/2.0')
        try:
            with self.transport(req, timeout=12) as response:
                data = json.loads(response.read(65536))
                if not isinstance(data, dict):
                    raise ValueError('O serviço retornou uma resposta inválida. Confira os logs antes de repetir o envio.')
                return data
        except HTTPError as error:
            code = ''
            message = ''
            raw_error = error.read(65536).decode('utf-8', errors='replace')
            try:
                parsed = json.loads(raw_error)
                if isinstance(parsed, dict):
                    code = str(parsed.get('code', ''))
                    code = code if code.isdigit() else ''
                    message = str(parsed.get('message', ''))
            except (ValueError, OSError):
                pass
            if not message and raw_error.strip():
                gateway_code = re.search(r'error\s*code\s*:\s*(\d{3,5})', raw_error, re.IGNORECASE)
                if gateway_code:
                    raise ValueError(f'O serviço de proteção da API recusou a requisição (HTTP {error.code}, código {gateway_code.group(1)}). Isso não confirma erro na chave ou no destinatário.') from None
                if '<html' in raw_error.lower() or '<!doctype' in raw_error.lower():
                    raise ValueError(f'A conexão recebeu uma página de bloqueio em vez da resposta da API (HTTP {error.code}). Confira a rede e o serviço; isso não confirma erro nas credenciais.') from None
            if channel == 'email':
                lower = message.lower()
                if 'own email' in lower or 'testing emails' in lower:
                    addresses = re.findall(r'[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', message)
                    allowed = f" Destinatário autorizado informado pelo Resend: {addresses[0]}." if addresses else ''
                    raise ValueError('O Resend permite usar onboarding@resend.dev somente para o e-mail da própria conta.' + allowed + ' Para outros destinatários, verifique um domínio no Resend.') from None
                if 'api key' in lower and ('invalid' in lower or 'not found' in lower or 'missing' in lower):
                    raise ValueError('A chave de API foi recusada pelo Resend. Crie uma chave com permissão de envio e substitua a chave em Serviços de envio.') from None
                if 'domain' in lower and ('verif' in lower or 'permission' in lower or 'restrict' in lower):
                    raise ValueError('O Resend recusou o domínio ou a permissão do remetente. Confira se a chave permite o remetente configurado. Para teste, use onboarding@resend.dev com uma chave que permita esse envio.') from None
                if message:
                    # Preserve the provider's useful explanation, never credentials.
                    for secret_field in SECRET_FIELDS:
                        value = c.get(secret_field)
                        if value:
                            message = message.replace(value, '[credencial ocultada]')
                    message = ' '.join(message.split())[:350]
                    raise ValueError(f'Resend recusou o envio (HTTP {error.code}): {message}') from None
            if channel in ('sms', 'whatsapp'):
                raise ValueError(self.twilio_error(c, code, message, error.code)) from None
            suffix = f' (código {code})' if code else ''
            raise ValueError(f'O serviço recusou o envio: HTTP {error.code}{suffix}. Confira credenciais, remetente e permissões do destinatário.') from None
        except (URLError, OSError, TimeoutError):
            raise ValueError('Não foi possível confirmar o envio. Confira a internet e o serviço antes de tentar novamente.') from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError('O serviço retornou uma resposta inválida. Confira os logs antes de repetir o envio.') from None


def deliver_one(store, providers):
    job = store.claim_job()
    if not job:
        return False
    prefs = store.preferences(job['user_id'])
    destination = prefs['email'] if job['channel'] == 'email' else prefs['phone']
    if not prefs['consent'] or not prefs['enabled'] or job['channel'] not in prefs['channels'] or destination != job['destination']:
        store.finish_job(job['id'], 'blocked', 'As preferências de envio foram alteradas antes do processamento.')
        return True
    problem = providers.configuration_error(job['channel'])
    if not providers.live_enabled() or problem:
        store.finish_job(job['id'], 'blocked', problem or 'Envios reais desativados pelo administrador.')
        return True
    try:
        provider_id = providers.send(job)
        store.finish_job(job['id'], 'accepted', 'Aceito pelo serviço. A entrega ao destinatário ainda não foi confirmada.', provider_id)
    except ValueError as error:
        store.finish_job(job['id'], 'failed', str(error))
    except Exception:
        store.finish_job(job['id'], 'failed', 'Falha ao processar o envio. Confira o serviço antes de repetir.')
    return True
