# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPEC).resolve().parent.parent
notices = []
for package in ('pywebview', 'waitress', 'pyserial', 'psutil', 'qrcode'):
    notices += copy_metadata(package, recursive=True)
a = Analysis(
    [str(root / 'desktop.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / 'index.html'), '.'),
           (str(root / 'web_assets'), 'web_assets'),
           (str(root / 'mobile_assets'), 'mobile_assets'),
           (str(root / 'packaging' / 'climaguard.ico'), 'packaging'),
           (str(root / 'packaging' / 'ajuda.html'), 'packaging'),
           (str(root / 'packaging' / 'licenses'), 'licenses'),
           (str(root / 'whatsapp_local' / 'bridge.js'), 'whatsapp_local'),
           (str(root / 'whatsapp_local' / 'package.json'), 'whatsapp_local'),
           (str(root / 'whatsapp_local' / 'package-lock.json'), 'whatsapp_local'),
           (str(root / 'whatsapp_local' / 'node_modules'), 'whatsapp_local/node_modules'),
           (str(root / 'docs'), 'docs')] +
          [(str(root / 'work' / 'whatsapp-runtime' / name), 'whatsapp_runtime') for name in
           ('node.exe', 'Node-LICENSE.txt', 'WPPConnect-source.zip', 'LEIA-ME-LICENCAS.txt', 'runtime.json')] + notices,
    hiddenimports=['webview.platforms.edgechromium', 'webview.platforms.winforms', 'serial.tools.list_ports_windows'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'gtk', 'gi', 'cefpython3', 'pytest', 'esptool'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ClimaGuard',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False,
          icon=str(root / 'packaging' / 'climaguard.ico'),
          version=str(root / 'packaging' / 'version_info.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ClimaGuard')
