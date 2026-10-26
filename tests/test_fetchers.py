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
archive = load('fetch-archive')
mezhdu = load('fetch-mezhdunami')


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


class TestFetchArchive(Server):
    def item(self, ident, language='rus', tracks=(('01_x_64kb.mp3', b'one'), ('02_x_64kb.mp3', b'two'))):
        files_meta = []
        for name, data in tracks:
            self.publish(f'download/{ident}/{name}', data)
            files_meta.append({'name': name, 'format': '64Kbps MP3', 'md5': hashlib.md5(data).hexdigest(),
                               'sha1': hashlib.sha1(data).hexdigest()})
        files_meta.append({'name': 'big.mp3', 'format': '128Kbps MP3', 'md5': 'x', 'sha1': 'y'})
        self.publish(f'metadata/{ident}', json.dumps({'metadata': {'title': 'Повести Белкина', 'creator': 'Пушкин',
                     'language': language, 'runtime': '3:00:00'}, 'files': files_meta}).encode())

    def run_fetch(self, rows, *extra):
        m = self.base / 'books.tsv'
        m.write_text('# x\n' + ''.join(f'{i}\t{l}\n' for i, l in rows), encoding='utf-8')
        out = self.base / 'out'
        return quiet(archive.main, ['--manifest', str(m), '--dest', str(out), '--base', self.url, *extra]), out

    def test_downloads_verified_tracks_and_catalog(self):
        self.item('belkin')
        self.item('english', language='eng')
        rc, out = self.run_fetch([('belkin', 'B1'), ('english', 'A2'), ('gone', 'B2')])
        self.assertEqual(rc, 0)
        cat = json.loads((out / 'catalog.json').read_text(encoding='utf-8'))
        self.assertEqual([b['id'] for b in cat], ['belkin'])
        folder = out / cat[0]['folder']
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ['01_x_64kb.mp3', '02_x_64kb.mp3'])
        self.assertTrue(str(cat[0]['folder']).startswith('B1/Повести Белкина - Пушкин'))
        self.assertIn('B1/Повести Белкина - Пушкин/01_x_64kb.mp3', (out / 'SHA256SUMS').read_text(encoding='utf-8'))
        self.assertEqual(self.run_fetch([('gone', 'B2')], '--required')[0], 1)

    def test_tampered_track_refused(self):
        self.item('belkin')
        self.publish('download/belkin/02_x_64kb.mp3', b'tampered')
        rc, out = self.run_fetch([('belkin', 'B1')])
        self.assertEqual(json.loads((out / 'catalog.json').read_text()), [])
        self.assertFalse(list(out.rglob('*.part')))

    def test_bad_manifest(self):
        with self.assertRaises(ValueError):
            archive.read_manifest(self.manifest_file('x\tZ9\n'))
        with self.assertRaises(ValueError):
            archive.read_manifest(self.manifest_file('../x\tA1\n'))

    def manifest_file(self, text):
        m = self.base / 'bad.tsv'; m.write_text(text); return m

    def test_real_audiobook_manifest(self):
        rows = archive.read_manifest(Path(__file__).resolve().parents[1] / 'packaging/russian/audiobooks.tsv')
        self.assertGreaterEqual(len(rows), 25)
        self.assertEqual({l for _, l in rows}, {'A2', 'B1', 'B2'})


class TestFetchMezhdunami(Server):
    def build_site(self):
        self.publish('index.shtml', b'<html><link href="/css/s.css" rel="stylesheet">'
                     b'<script src="https://cdn.example.invalid/x.js"></script>'
                     b'<a href="unit01/1_1/index.shtml#top">1.1</a> <a href="/pdfs/v1.pdf">pdf</a>'
                     b'<a href="https://elsewhere.example/">out</a></html>')
        self.publish('css/s.css', b'body{background:url("../img/bg.png")}')
        self.publish('img/bg.png', b'PNG')
        self.publish('pdfs/v1.pdf', b'%PDF')
        self.publish('unit01/1_1/index.shtml', '<p>Привет</p><img src="img/a.png">'
                     '<iframe width="100%" src="https://w.soundcloud.com/player/?url=http%3A%2F%2Fapi.soundcloud.com'
                     '%2Ftracks%2F111&amp;color=x"></iframe>'
                     '<iframe src="https://w.soundcloud.com/player/?url=https%3A//api.soundcloud.com/tracks/222"></iframe>'
                     '<a href="../../index.shtml">home</a>'.encode())
        self.publish('unit01/1_1/img/a.png', b'PNG')

    def fake_ytdlp(self):
        script = self.base / 'ytdlp.py'
        script.write_text('import sys, re\nargs = sys.argv[1:]\nout = args[args.index("-o") + 1]\n'
                          'for url in open(args[args.index("-a") + 1]):\n'
                          '    tid = re.search(r"(\\d+)$", url.strip()).group(1)\n'
                          '    if tid == "111": open(out.replace("%(id)s", tid).replace("%(ext)s", "mp3"), "w").write("a")\n')
        return f'python3 {script}'

    def test_offline_copy_with_local_audio(self):
        self.build_site()
        dest = self.base / 'mn'
        rc = quiet(mezhdu.main, ['--base', self.url + 'index.shtml', '--dest', str(dest), '--ytdlp', self.fake_ytdlp()])
        self.assertEqual(rc, 0)
        index = (dest / 'index.html').read_text(encoding='utf-8')
        self.assertIn('href="unit01/1_1/index.html#top"', index)
        self.assertIn('href="pdfs/v1.pdf"', index)
        self.assertIn('href="https://elsewhere.example/"', index)        # outside links kept
        self.assertIn('href="css/s.css"', index)
        self.assertTrue((dest / 'pdfs/v1.pdf').is_file())
        self.assertIn('url("../img/bg.png")', (dest / 'css/s.css').read_text())
        self.assertTrue((dest / 'img/bg.png').is_file())
        lesson = (dest / 'unit01/1_1/index.html').read_text(encoding='utf-8')
        self.assertIn('<audio controls preload="none" src="../../audio/111.mp3">', lesson)
        self.assertIn('not in the offline copy', lesson)                 # track 222 failed
        self.assertNotIn('soundcloud', lesson)
        self.assertIn('href="../../index.html"', lesson)
        self.assertIn('CC BY-NC-ND', (dest / 'KIRIN-README.txt').read_text(encoding='utf-8').replace('Creative Commons BY-NC-ND', 'CC BY-NC-ND'))
        self.assertIn('unit01/1_1/img/a.png', (dest / 'SHA256SUMS').read_text())

    def test_unreachable_site_fails(self):
        self.assertEqual(quiet(mezhdu.main, ['--base', self.url + 'missing/', '--dest', str(self.base / 'x')]), 1)
