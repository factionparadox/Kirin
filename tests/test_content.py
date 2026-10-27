"""kirin-content against a fake installed system, a stub Ollama and a local web server."""
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'scripts/kirin-content'


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / 'root'
        subprocess.run(['sh', str(ROOT / 'scripts/install-education.sh')], env={**os.environ, 'DESTDIR': str(self.root)},
                       check=True, capture_output=True)
        (self.root / 'usr/share/kirin').mkdir(parents=True, exist_ok=True)
        (self.root / 'usr/share/kirin/russian.json').write_text(json.dumps({'model': 'tutor', 'voices': 'x'}))
        self.site = base / 'site'; self.site.mkdir()
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(self.site))
        handler.log_message = lambda *a: None
        httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close); self.addCleanup(httpd.shutdown)
        self.url = f'http://127.0.0.1:{httpd.server_port}'
        # Stub Ollama: remembers pulled tags in a file.
        self.ollama = base / 'ollama'
        self.ollama.write_text('#!/bin/sh\nS="$(dirname "$0")/pulled"\ncase "$1" in\n'
                               '  list) echo "NAME ID SIZE"; [ -f "$S" ] && sed "s/$/ x 1GB/" "$S" ;;\n'
                               '  pull) echo "$2" >> "$S" ;;\n  rm) grep -vx "$2" "$S" > "$S.n"; mv "$S.n" "$S" ;;\nesac\n')
        self.ollama.chmod(0o755)

    def publish_zim(self, directory, name, data=b'zim'):
        d = self.site / 'zim' / directory; d.mkdir(parents=True, exist_ok=True)
        (d / name).write_bytes(data)
        (d / f'{name}.sha256').write_text(f'{hashlib.sha256(data).hexdigest()}  {name}\n')
        listing = d / 'index.html'
        listing.write_text((listing.read_text() if listing.exists() else '') + f'<a href="{name}">{name}</a>\n')

    def run_tool(self, *args, input=''):
        env = {**os.environ, 'KIRIN_CONTENT_ROOT': str(self.root), 'KIRIN_CONTENT_OLLAMA': str(self.ollama),
               'KIRIN_CONTENT_KIWIX': self.url + '/zim', 'KIRIN_CONTENT_ARCHIVE': self.url + '/archive/',
               'KIRIN_CONTENT_MEZHDUNAMI': self.url + '/mn/index.shtml', 'KIRIN_CONTENT_YTDLP': 'no-such-ytdlp'}
        return subprocess.run([str(TOOL), *args], capture_output=True, text=True, env=env, input=input)

    def config(self):
        return json.loads((self.root / 'usr/share/kirin/russian.json').read_text())

    def test_models_go_through_ollama(self):
        r = self.run_tool('install', 'ai-coder')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('qwen2.5-coder:7b-instruct', (self.ollama.parent / 'pulled').read_text())
        self.assertRegex(self.run_tool('list').stdout, r'ai-coder\s+installed')
        self.assertRegex(self.run_tool('list').stdout, r'ai-tutor\s+18\.6 GB')
        self.run_tool('remove', 'ai-coder')
        self.assertNotIn('qwen2.5-coder', (self.ollama.parent / 'pulled').read_text())

    def test_dictionaries_are_verified_and_configured(self):
        self.publish_zim('wiktionary', 'wiktionary_en_all_nopic_2026-09.zim')
        self.publish_zim('wiktionary', 'wiktionary_ru_all_nopic_2026-08.zim')
        r = self.run_tool('install', 'ru-dictionaries')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        cfg = self.config()
        self.assertEqual(cfg['dictionary'], '/opt/kirin/russian/dictionary/wiktionary_en_all_nopic_2026-09.zim')
        self.assertEqual(cfg['kiwix']['wiktionary-ru'], '/opt/kirin/russian/dictionary/wiktionary_ru_all_nopic_2026-08.zim')
        self.assertEqual(cfg['model'], 'tutor')                        # existing settings kept
        self.assertRegex(self.run_tool('list').stdout, r'ru-dictionaries\s+installed')
        self.run_tool('remove', 'ru-dictionaries')
        self.assertEqual(self.config()['kiwix'], {})

    def test_tampered_zim_refused(self):
        self.publish_zim('wikisource', 'wikisource_ru_all_nopic_2019-08.zim')
        self.publish_zim('wikipedia', 'wikipedia_ru_all_mini_2026-10.zim')
        (self.site / 'zim/wikipedia/wikipedia_ru_all_mini_2026-10.zim').write_bytes(b'tampered')
        r = self.run_tool('install', 'ru-reading')
        self.assertEqual(r.returncode, 1)
        self.assertIn('FAILED', r.stdout)
        self.assertNotIn('wikipedia', self.config()['kiwix'])
        self.assertIn('wikisource', self.config()['kiwix'])

    def test_interactive_choice_and_unknown_pack(self):
        r = self.run_tool(input='1\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('qwen2.5-coder', (self.ollama.parent / 'pulled').read_text())
        self.assertEqual(self.run_tool('install', 'nonsense').returncode, 2)

    def test_installed_with_its_helpers(self):
        lib = self.root / 'usr/lib/kirin/content'
        for name in ('fetch-files.py', 'fetch-kiwix.py', 'fetch-archive.py', 'fetch-mezhdunami.py',
                     'library.tsv', 'audiobooks.tsv'):
            self.assertTrue((lib / name).is_file(), name)
        self.assertTrue(os.access(self.root / 'usr/bin/kirin-content', os.X_OK))


if __name__ == '__main__':
    unittest.main()
