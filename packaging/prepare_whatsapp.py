"""Reproduce the local WhatsApp runtime without downloading another browser."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.request import urlopen
import zipfile

root = Path(__file__).resolve().parent.parent
runtime = root / 'work/whatsapp-runtime'
runtime.mkdir(parents=True, exist_ok=True)
version = 'v22.23.4'
name = f'node-{version}-win-x64.zip'
base = f'https://nodejs.org/dist/{version}/'
if not (runtime / 'node.exe').is_file():
    with urlopen(base + 'SHASUMS256.txt', timeout=30) as response:
        sums = response.read().decode()
    expected = next(line.split()[0] for line in sums.splitlines() if line.split()[-1] == name)
    with urlopen(base + name, timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit('Falha na verificação SHA-256 do Node.js oficial.')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for source, target in [('node.exe', 'node.exe'), ('LICENSE', 'Node-LICENSE.txt')]:
            (runtime / target).write_bytes(archive.read(f'node-{version}-win-x64/{source}'))
    (runtime / 'runtime.json').write_text(json.dumps({'node': version, 'source': base + name, 'sha256': expected}, indent=2))

package_dir = root / 'whatsapp_local'
source_url = 'https://codeload.github.com/wppconnect-team/wppconnect/zip/1bfcf56f48f8741cdfc9218188c56bdb8717bddf'
if not (runtime / 'WPPConnect-source.zip').exists():
    with urlopen(source_url, timeout=90) as response:
        (runtime / 'WPPConnect-source.zip').write_bytes(response.read())
(runtime / 'LEIA-ME-LICENCAS.txt').write_text(
    'WPPConnect 2.3.5: LGPL-3.0-or-later. Código-fonte correspondente: WPPConnect-source.zip.\n'
    + source_url + '\nA biblioteca permanece substituível na pasta whatsapp_local/node_modules.\n'
    'As licenças dos demais pacotes acompanham suas respectivas pastas.\n'
    'Node.js: consulte Node-LICENSE.txt.\n', encoding='utf-8')
lock_hash = hashlib.sha256((package_dir / 'package-lock.json').read_bytes()).hexdigest()
stamp = runtime / 'dependencies.sha256'
if not (package_dir / 'node_modules/@wppconnect-team/wppconnect/package.json').is_file() or not stamp.exists() or stamp.read_text() != lock_hash:
    npm = shutil.which('npm.cmd') or shutil.which('npm')
    if not npm:
        raise SystemExit('Instale Node.js/npm para preparar as dependências do instalador.')
    env = dict(os.environ, PUPPETEER_SKIP_DOWNLOAD='true')
    subprocess.run([npm, 'ci', '--omit=dev', '--ignore-scripts', '--no-fund', '--no-audit'], cwd=package_dir, env=env, check=True)
    stamp.write_text(lock_hash)
print('Runtime WhatsApp local preparado: Node.js e WPPConnect, sem dados pessoais.')
