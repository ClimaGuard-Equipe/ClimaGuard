"""Windows receiver and notifications; the physical board operates over Wi-Fi."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import webbrowser
from urllib.request import ProxyHandler, build_opener

from waitress import create_server
from portal import ROOT, create_app
from receber_usb import main as receive_usb
from network_discovery import ReceiverDiscovery

VERSION = '1.6.4'
TITLE = 'ClimaGuard'


def application_data_dir():
    configured = os.environ.get('CLIMAGUARD_DATA_DIR')
    if configured:
        return Path(configured).resolve()
    local_app_data = os.environ.get('LOCALAPPDATA')
    return (Path(local_app_data) if local_app_data else Path.home() / 'AppData' / 'Local') / 'ClimaGuard'


def configure_logging(data_dir):
    data_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(data_dir / 'aplicativo.log', maxBytes=2_000_000, backupCount=2, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format='%(asctime)s %(levelname)s %(message)s', force=True)
    # Windowed Python has no terminal streams; third-party libraries still print.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w', encoding='utf-8')


class SingleInstance:
    def __init__(self, data_dir):
        self.handle = None
        self.already_running = False
        if sys.platform == 'win32':
            self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            self.kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
            self.kernel.CreateMutexW.restype = wintypes.HANDLE
            self.kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
            digest = hashlib.sha256(str(data_dir.resolve()).casefold().encode()).hexdigest()[:20]
            self.handle = self.kernel.CreateMutexW(None, False, 'Local\\ClimaGuard-' + digest)
            if not self.handle:
                raise OSError('Não foi possível reservar a instância do aplicativo.')
            self.already_running = ctypes.get_last_error() == 183

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class DesktopServer:
    def __init__(self, data_dir, host='0.0.0.0', port=5000, usb=False, network=None):
        self.data_dir = Path(data_dir)
        self.stop_event = threading.Event()
        self.usb_enabled = usb
        self.usb_thread = None
        self.delivery_thread = None
        self.discovery = None
        self.discovery_enabled = host == '0.0.0.0'
        self.network_enabled = self.discovery_enabled if network is None else network
        # Bind before starting delivery and USB workers.
        self.app = create_app(self.data_dir, worker=False)
        self.server = create_server(self.app, host=host, port=port)
        self.url = f'http://127.0.0.1:{self.server.effective_port}'
        self.server_thread = threading.Thread(target=self.server.run, daemon=True, name='climaguard-http')
        self.mobile_server = self.mobile_thread = None
        mobile = self.app.extensions['climaguard_mobile']
        try:
            self.mobile_server = create_server(mobile.app, host='127.0.0.1', port=5003 if port == 5000 else 0)
            mobile.remote.port = self.mobile_server.effective_port
            self.mobile_thread = threading.Thread(target=self.mobile_server.run, daemon=True, name='climaguard-mobile')
        except OSError:
            mobile.error = 'A porta local 5003 está em uso. Feche a outra instância e reinicie o ClimaGuard.'

    def start(self):
        self.server_thread.start()
        if self.mobile_thread:
            self.mobile_thread.start()
            self.app.extensions['climaguard_mobile'].available = True
        if self.network_enabled:
            self.app.extensions['climaguard_network'].start()
        if self.discovery_enabled:
            try:
                self.discovery = ReceiverDiscovery((self.data_dir / '.device-token').read_text().strip(), self.server.effective_port)
                self.discovery.start()
            except OSError:
                logging.exception('Descoberta indisponível; a placa ainda pode usar o endereço configurado.')
        whatsapp = self.app.extensions['climaguard_whatsapp']
        providers = self.app.extensions['climaguard_providers']
        if providers.config().get('WHATSAPP_PROVIDER') == 'wppconnect' and (whatsapp.directory / 'browser').exists() and whatsapp.available():
            whatsapp.start()
        from providers import deliver_one
        store = self.app.extensions['climaguard_store']

        def delivery_worker():
            while not self.stop_event.is_set():
                store.jobs_ready.clear()
                try:
                    if deliver_one(self.app.extensions['climaguard_store'], self.app.extensions['climaguard_providers']):
                        continue
                except Exception:
                    logging.exception('Falha temporária na fila de notificações.')
                store.jobs_ready.wait(2)

        self.delivery_thread = threading.Thread(target=delivery_worker, daemon=True, name='climaguard-alerts')
        self.delivery_thread.start()
        if self.usb_enabled:
            self.usb_thread = threading.Thread(target=self.usb_worker, daemon=True, name='climaguard-usb')
            self.usb_thread.start()

    def usb_worker(self):
        last_error = None
        while not self.stop_event.is_set():
            try:
                receive_usb(data_dir=self.data_dir, server_url=self.url, stop_event=self.stop_event)
            except Exception as error:
                if str(error) != last_error:
                    logging.info('USB: %s', error)
                    last_error = str(error)
            self.stop_event.wait(5)

    def close(self):
        self.stop_event.set()
        self.app.extensions['climaguard_store'].jobs_ready.set()
        if self.delivery_thread:
            self.delivery_thread.join(timeout=5)
        self.app.extensions['climaguard_network'].close()
        if self.discovery:
            self.discovery.close()
        self.app.extensions['climaguard_whatsapp'].close()
        self.app.extensions['climaguard_mobile'].available = False
        if self.mobile_server:
            self.mobile_server.task_dispatcher.shutdown(timeout=3)
            self.mobile_server.close()
        if self.usb_thread:
            self.usb_thread.join(timeout=3)
        self.server.task_dispatcher.shutdown(timeout=3)
        self.server.close()


def self_test(report_path):
    """Exercise the frozen Python runtime and bundled assets without sending messages."""
    with tempfile.TemporaryDirectory(prefix='climaguard-test-') as directory:
        server = DesktopServer(directory, host='127.0.0.1', port=0, usb=False)
        try:
            server.start()
            opener = build_opener(ProxyHandler({}))
            results = {}
            for path in ('/health', '/', '/assets/app.js', '/assets/style.css', '/api/session'):
                with opener.open(server.url + path, timeout=10) as response:
                    payload = response.read()
                    results[path] = {'status': response.status, 'bytes': len(payload)}
                    if path == '/health':
                        assert json.loads(payload)['app'] == TITLE
            mobile_results = {}
            for path in ('/', '/manifest.webmanifest', '/sw.js', '/assets/mobile.js', '/assets/mobile.css', '/assets/icon-180.png'):
                with opener.open(f'http://127.0.0.1:{server.mobile_server.effective_port}' + path, timeout=10) as response:
                    payload = response.read()
                    mobile_results[path] = {'status': response.status, 'bytes': len(payload)}
            assert (Path(directory) / '.device-token').exists()
            report = {'ok': True, 'version': VERSION, 'frozen': bool(getattr(sys, 'frozen', False)), 'checks': results, 'mobile_checks': mobile_results}
            Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        finally:
            server.close()


def show_error(message):
    if sys.platform == 'win32':
        ctypes.windll.user32.MessageBoxW(None, message, TITLE, 0x10)


def main():
    parser = argparse.ArgumentParser(description='ClimaGuard para Windows')
    parser.add_argument('--self-test', metavar='REPORT')
    parser.add_argument('--smoke-test', metavar='REPORT')
    parser.add_argument('--usb', action='store_true', help='Usar a ponte USB em vez da placa por Wi-Fi (modo de manutenção).')
    parser.add_argument('--legacy-network', action='store_true', help='Aceitar leituras de firmware anterior a 1.3 (modo de manutenção).')
    args = parser.parse_args()
    if args.self_test:
        self_test(args.self_test)
        return 0
    temporary = tempfile.TemporaryDirectory(prefix='climaguard-ui-test-', ignore_cleanup_errors=True) if args.smoke_test else None
    data_dir = Path(temporary.name) if temporary else application_data_dir()
    configure_logging(data_dir)
    instance = SingleInstance(data_dir)
    server = None
    try:
        if instance.already_running:
            user32 = ctypes.windll.user32
            user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
            user32.FindWindowW.restype = wintypes.HWND
            user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
            user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
            window_handle = user32.FindWindowW(None, TITLE)
            if window_handle:
                user32.ShowWindow(window_handle, 9)
                user32.SetForegroundWindow(window_handle)
            return 0
        import webview
        from webview.menu import Menu, MenuAction
        server = DesktopServer(data_dir, host='0.0.0.0' if args.legacy_network and not temporary else '127.0.0.1',
                               port=0 if temporary else 5000, usb=args.usb and not temporary,
                               network=not temporary and not args.usb)
        server.start()
        window = webview.create_window(TITLE, server.url, width=1280, height=850,
                                       min_size=(800, 600), background_color='#123c35', text_select=True)

        def close_help_windows():
            for other_window in list(webview.windows):
                if other_window is not window:
                    other_window.destroy()
        window.events.closed += close_help_windows

        def help_window():
            help_file = ROOT / 'packaging' / 'ajuda.html'
            webview.create_window('Ajuda do ClimaGuard', html=help_file.read_text(encoding='utf-8'),
                                  width=760, height=700, text_select=True)

        menu = [Menu('Aplicativo', [
            MenuAction('Abrir no navegador', lambda: webbrowser.open(server.url)),
            MenuAction('Abrir pasta de dados', lambda: os.startfile(data_dir)),
            MenuAction('Como usar', help_window),
            MenuAction('Sair', window.destroy),
        ])]
        if args.smoke_test:
            def check_window():
                report = {'ok': False, 'frozen': bool(getattr(sys, 'frozen', False))}
                try:
                    for _ in range(50):
                        report['page'] = window.evaluate_js('JSON.stringify({title:document.title,loginVisible:!document.getElementById("auth").hidden,hasWhatsApp:!!document.querySelector("[data-test=whatsapp]")})')
                        if json.loads(report['page'])['loginVisible']:
                            report['ok'] = json.loads(report['page'])['hasWhatsApp']
                            break
                        time.sleep(.2)
                except Exception as error:
                    report['error'] = str(error)
                finally:
                    Path(args.smoke_test).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                    window.destroy()
            window.events.loaded += check_window
        webview.settings['ALLOW_FILE_URLS'] = False
        webview.start(gui='edgechromium', private_mode=False, storage_path=str(data_dir / 'WebView'),
                      menu=menu, icon=str(ROOT / 'packaging' / 'climaguard.ico'))
        return 0
    except Exception as error:
        logging.exception('Não foi possível abrir o aplicativo.')
        message = (f'Não foi possível abrir o ClimaGuard.\n\n{error}\n\n'
                   'Se a porta 5000 estiver em uso, feche a versão anterior do ClimaGuard e abra novamente.\n'
                   'Consulte aplicativo.log na pasta de dados para mais detalhes.')
        if args.smoke_test:
            Path(args.smoke_test).write_text(json.dumps({'ok': False, 'error': str(error)}), encoding='utf-8')
        else:
            show_error(message)
        return 1
    finally:
        if server:
            server.close()
        instance.close()
        if temporary:
            logging.shutdown()
            temporary.cleanup()


if __name__ == '__main__':
    sys.exit(main())
