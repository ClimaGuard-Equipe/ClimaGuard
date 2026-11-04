"""Check the Git index or public build for private files without printing secrets."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.parse import unquote, urlsplit

PRIVATE_NAMES = {'.providers.json', '.providers.tmp', '.device-token', '.session-secret',
                 '.wifi-setup-cards.json', '.wifi-setup-cards.tmp', '.mobile-devices.json',
                 '.mobile-devices.tmp', 'device-network.json', 'device-network.tmp', 'config.h',
                 'local.properties', 'readings.jsonl'}
PRIVATE_DIRS = {'WebView', 'whatsapp-session', 'tokens', 'userDataDir'}
SECRET_PATTERNS = [re.compile(p) for p in (
    r'\bre_[A-Za-z0-9_-]{24,}', r'\b(?:ghp_|gho_|github_pat_)[A-Za-z0-9_]{25,}',
    r'\bsk-(?:proj-)?[A-Za-z0-9_-]{35,}', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')]

def private_file(name, bundle=False):
    path=PurePosixPath(name)
    vendor='node_modules' in path.parts
    if not vendor and (path.name in PRIVATE_NAMES or any(p in PRIVATE_DIRS for p in path.parts)):
        return True
    if path.name == '.env' or path.suffix.lower() in {'.jks','.keystore','.dpapi','.sqlite3','.db'}:
        return True
    if not bundle and (any(p in {'.venv','node_modules','work','dist','build','.gradle'} for p in path.parts)
                       or path.suffix.lower() in {'.exe','.apk','.bin','.elf','.zip','.log'}):
        return True
    return False

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--working-tree',action='store_true')
    parser.add_argument('--bundle',type=Path)
    args=parser.parse_args()
    root=args.root.resolve(); issues=[]
    if args.bundle:
        bundle=args.bundle.resolve()
        files=[(p.relative_to(bundle).as_posix(),p.read_bytes) for p in bundle.rglob('*') if p.is_file()]
    else:
        command=['git','ls-files','-z']
        if args.working_tree: command+=['--cached','--others','--exclude-standard']
        names=subprocess.check_output(command,cwd=root).decode('utf-8').split('\0')
        files=[]
        for name in sorted(set(names)-{''}):
            if args.working_tree:
                if not (root/name).is_file(): continue
                reader=(root/name).read_bytes
            else:
                reader=lambda name=name: subprocess.check_output(['git','show',':'+name],cwd=root)
            files.append((name,reader))
    for name,reader in files:
        if private_file(name,bool(args.bundle)): issues.append({'file':name,'issue':'private/generated file'}); continue
        # Installed third-party files are checked by path; scan our textual sources for key formats.
        if args.bundle and (name.startswith('_internal/whatsapp_') or name.endswith('.exe')): continue
        try: text=reader().decode('utf-8-sig')
        except UnicodeError: continue
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            issues.append({'file':name,'issue':'possible credential; value suppressed'})
        if name.endswith('.md') and not args.bundle:
            for link in re.findall(r'\]\(([^)\n]+)\)',text):
                link=link.strip('<>').split(' "',1)[0]
                if not link or link.startswith('#') or urlsplit(link).scheme: continue
                target=(root/PurePosixPath(name).parent/unquote(link.split('#',1)[0])).resolve()
                indexed={filename for filename,_ in files}
                if (not target.is_relative_to(root) or not target.is_file() or
                    (not args.working_tree and target.relative_to(root).as_posix() not in indexed)):
                    issues.append({'file':name,'issue':'missing local link','target':link})
    report={'ok':not issues,'files_checked':len(files),'issues':issues}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['ok'] else 1

if __name__=='__main__': raise SystemExit(main())
