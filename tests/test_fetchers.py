import contextlib
import functools
import hashlib
import http.server
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest

BUILD = Path(__file__).resolve().parents[1] / 'scripts/build'


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), BUILD / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


files = load('fetch-files')
kiwix = load('fetch-kiwix')


def quiet(fn, *args):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*args)


class Server(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.site = self.base / 'site'
        self.site.mkdir()
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(self.site))
        handler.log_message = lambda *a: None
        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.url = f'http://127.0.0.1:{self.httpd.server_port}/'

    def publish(self, rel, data):
        path = self.site / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


class TestFetchFiles(Server):
    def manifest(self, rows):
        m = self.base / 'm.tsv'
        m.write_text('# comment\n\n' + ''.join(f'{d}\t{u}\n' for d, u in rows), encoding='utf-8')
        return m

    def run_fetch(self, rows, required=False):
        out, lock = self.base / 'out', self.base / 'lock.json'
        code = quiet(files.main, ['--manifest', str(self.manifest(rows)), '--dest', str(out),
                                  '--lock', str(lock)] + (['--required'] if required else []))
        return code, out, lock

    def test_downloads_pins_and_reuses(self):
        self.publish('a.pdf', b'course one')
        self.publish('b b.mp3', b'tape')
        rows = [('Course/One.pdf', self.url + 'a.pdf'), ('Course/Audio/Tape 1.mp3', self.url + 'b%20b.mp3')]
        code, out, lock = self.run_fetch(rows)
        self.assertEqual(code, 0)
        self.assertEqual((out / 'Course/One.pdf').read_bytes(), b'course one')
        pinned = json.loads(lock.read_text())
        self.assertEqual(pinned['Course/One.pdf']['sha256'], hashlib.sha256(b'course one').hexdigest())
        self.assertIn('Course/Audio/Tape 1.mp3', (out / 'SHA256SUMS').read_text())
        (self.site / 'a.pdf').unlink()          # cached copy is reused without the network
        self.assertEqual(self.run_fetch(rows)[0], 0)

    def test_changed_source_is_refused(self):
        self.publish('a.pdf', b'original')
        rows = [('One.pdf', self.url + 'a.pdf')]
        _, out, _ = self.run_fetch(rows)
        (out / 'One.pdf').unlink()
        self.publish('a.pdf', b'tampered')
        code, out, _ = self.run_fetch(rows, required=True)
        self.assertEqual(code, 1)
        self.assertFalse((out / 'One.pdf').exists())

    def test_missing_file_is_optional_unless_required(self):
        self.publish('a.pdf', b'ok')
        rows = [('One.pdf', self.url + 'a.pdf'), ('Gone.pdf', self.url + 'missing.pdf')]
        files.download.__defaults__ = (1,)      # no retry delay in tests
        self.addCleanup(setattr, files.download, '__defaults__', (3,))
        code, out, _ = self.run_fetch(rows)
        self.assertEqual(code, 0)
        self.assertTrue((out / 'One.pdf').is_file())
        self.assertNotIn('Gone.pdf', (out / 'SHA256SUMS').read_text())
        self.assertEqual(self.run_fetch(rows, required=True)[0], 1)

    def test_unsafe_destination_rejected(self):
        for bad in ('../escape.pdf', '/etc/x', 'a/../../b'):
            with self.assertRaises(ValueError):
                files.read_manifest(self.manifest([(bad, self.url + 'a')]))

    def test_real_library_manifest_is_valid(self):
        rows = files.read_manifest(Path(__file__).resolve().parents[1] / 'packaging/russian/library.tsv')
        self.assertGreaterEqual(len(rows), 15)
        voices = files.read_manifest(Path(__file__).resolve().parents[1] / 'packaging/russian/voices.tsv')
        self.assertEqual(len(voices), 8)


class TestFetchKiwix(Server):
    def publish_zim(self, name, data):
        self.publish(name, data)
        self.publish(name + '.sha256', f'{hashlib.sha256(data).hexdigest()}  {name}\n'.encode())

    def listing(self, *names):
        self.publish('index.html', ''.join(f'<a href="{n}">{n}</a>\n' for n in names).encode())

    def test_picks_newest_and_verifies(self):
        self.publish_zim('wiktionary_en_all_nopic_2026-01.zim', b'old dictionary')
        self.publish_zim('wiktionary_en_all_nopic_2026-09.zim', b'new dictionary')
        self.listing('wiktionary_en_all_nopic_2026-01.zim', 'wiktionary_en_all_nopic_2026-09.zim',
                     'wiktionary_en_all_maxi_2026-10.zim')
        dest = self.base / 'dict'
        (dest).mkdir()
        (dest / 'wiktionary_en_all_nopic_2025-01.zim').write_bytes(b'stale')
        name = kiwix.fetch(self.url, 'wiktionary_en_all_nopic_', dest)
        self.assertEqual(name, 'wiktionary_en_all_nopic_2026-09.zim')
        self.assertEqual((dest / name).read_bytes(), b'new dictionary')
        self.assertFalse((dest / 'wiktionary_en_all_nopic_2025-01.zim').exists())

    def test_bad_checksum_refused(self):
        self.publish('wiktionary_en_all_nopic_2026-09.zim', b'corrupt')
        self.publish('wiktionary_en_all_nopic_2026-09.zim.sha256', b'0' * 64 + b'  x\n')
        self.listing('wiktionary_en_all_nopic_2026-09.zim')
        dest = self.base / 'dict'
        with self.assertRaises(ValueError):
            kiwix.fetch(self.url, 'wiktionary_en_all_nopic_', dest)
        self.assertFalse((dest / 'wiktionary_en_all_nopic_2026-09.zim').exists())

    def test_existing_verified_file_not_redownloaded(self):
        self.publish_zim('wiktionary_en_all_nopic_2026-09.zim', b'dictionary')
        dest = self.base / 'dict'
        kiwix.fetch(self.url, 'wiktionary_en_all_nopic_', dest, 'wiktionary_en_all_nopic_2026-09.zim')
        (self.site / 'wiktionary_en_all_nopic_2026-09.zim').unlink()
        self.assertEqual(kiwix.fetch(self.url, 'wiktionary_en_all_nopic_', dest, 'wiktionary_en_all_nopic_2026-09.zim'),
                         'wiktionary_en_all_nopic_2026-09.zim')

    def test_pinned_name_must_match_prefix(self):
        with self.assertRaises(ValueError):
            kiwix.fetch(self.url, 'wiktionary_en_all_nopic_', self.base / 'd', '../../etc/passwd')


if __name__ == '__main__':
    unittest.main()
