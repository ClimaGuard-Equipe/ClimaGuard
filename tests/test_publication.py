"""The public-file guard checks staged files and never discloses detected keys."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CHECK=Path(__file__).resolve().parent.parent/'packaging/check_publication.py'

class PublicationTests(unittest.TestCase):
    def test_clean_staged_documentation_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            subprocess.run(['git','init','-q',str(root)],check=True)
            (root/'README.md').write_text('[Guia](guide.md)',encoding='utf-8')
            (root/'guide.md').write_text('Use o aplicativo.',encoding='utf-8')
            subprocess.run(['git','add','README.md','guide.md'],cwd=root,check=True)
            run=subprocess.run([sys.executable,str(CHECK),'--root',str(root)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout)
            self.assertTrue(json.loads(run.stdout)['ok'])

    def test_staged_secret_and_missing_document_are_rejected_without_echoing_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            subprocess.run(['git','init','-q',str(root)],check=True)
            key='gh'+'p_'+'x'*30
            (root/'README.md').write_text('[Guia](missing.md)',encoding='utf-8')
            (root/'.env').write_text('TOKEN='+key,encoding='utf-8')
            (root/'example.py').write_text('token="'+key+'"',encoding='utf-8')
            subprocess.run(['git','add','.'],cwd=root,check=True)
            run=subprocess.run([sys.executable,str(CHECK),'--root',str(root)],capture_output=True,text=True)
            self.assertEqual(run.returncode,1)
            issues=json.loads(run.stdout)['issues']
            self.assertEqual({issue['file'] for issue in issues},{'.env','README.md','example.py'})
            self.assertNotIn(key,run.stdout+run.stderr)
