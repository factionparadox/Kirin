import contextlib
import functools
import hashlib
import http.server
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
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
mirror = load('fetch-mirror')


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


class TestMirror(Server):
    """scripts/publish-content.sh packs and splits; fetch-mirror.py verifies and reassembles."""

    def make_payloads(self):
        work = self.base / 'work'
        r = work / 'payloads/russian'
        content = {'library': {'FSI Russian/FAST/Lessons 1-5.pdf': os.urandom(5000), 'Peace Corps/Course.pdf': b'%PDF'},
                   'audiobooks': {'A2/Сказки - Afanasyev/01.mp3': os.urandom(7000), 'catalog.json': b'[]'},
                   'voices': {'ru_RU-irina-medium.onnx': os.urandom(3000)}}
        for folder, files in content.items():
            for rel, data in files.items():
                p = r / folder / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
            lines = [f'{hashlib.sha256(d).hexdigest()}  {rel}' for rel, d in sorted(files.items())]
            (r / folder / 'SHA256SUMS').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return work, content

    def publish(self):
        work, content = self.make_payloads()
        mirror_json = self.base / 'mirror.json'
        env = {**os.environ, 'KIRIN_MIRROR_PART_SIZE': '4k', 'KIRIN_MIRROR_JSON': str(mirror_json)}
        result = subprocess.run(['bash', str(BUILD.parent / 'publish-content.sh'), '--work', str(work),
                                 '--out', str(self.base / 'out'), '--dry-run'],
                                capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        for part in (self.base / 'out/content-v1').glob('*.tar.[0-9][0-9]'):
            self.publish_file(part)
        return mirror_json, content

    def publish_file(self, path):
        (self.site / path.name).write_bytes(path.read_bytes())

    def fetch(self, mirror_json, pack, dest):
        return quiet(mirror.main, ['--mirror', str(mirror_json), '--pack', pack, '--dest', str(dest), '--base', self.url])

    def test_round_trip(self):
        mirror_json, content = self.publish()
        index = json.loads(mirror_json.read_text())
        self.assertEqual(set(index['packs']), {'ru-course', 'ru-audiobooks', 'ru-voices'})
        self.assertGreater(len(index['packs']['ru-audiobooks']['parts']), 1)          # split into parts
        self.assertTrue(index['url'].endswith('/releases/download/content-v1/'))
        for pack, folder in (('ru-course', 'library'), ('ru-audiobooks', 'audiobooks'), ('ru-voices', 'voices')):
            dest = self.base / 'installed' / folder
            self.assertEqual(self.fetch(mirror_json, pack, dest), 0, pack)
            for rel, data in content[folder].items():
                self.assertEqual((dest / rel).read_bytes(), data, rel)
        self.assertFalse(list((self.base / 'installed').glob('.kirin-mirror-*')))   # working files cleaned up

    def test_tampered_part_and_unknown_pack(self):
        mirror_json, _ = self.publish()
        first = json.loads(mirror_json.read_text())['packs']['ru-audiobooks']['parts'][0]['name']
        (self.site / first).write_bytes(b'tampered')
        dest = self.base / 'books'
        self.assertEqual(self.fetch(mirror_json, 'ru-audiobooks', dest), 1)
        self.assertFalse(dest.exists())
        self.assertEqual(self.fetch(mirror_json, 'ai-tutor', dest), 3)
        self.assertEqual(self.fetch(self.base / 'missing.json', 'ru-course', dest), 3)

    def test_unsafe_archive_refused(self):
        import tarfile
        evil = self.base / 'evil.tar'
        with tarfile.open(evil, 'w') as tar:
            info = tarfile.TarInfo('ru-course/../../escape.txt'); data = b'x'; info.size = 1
            tar.addfile(info, io.BytesIO(data))
        sha = hashlib.sha256(evil.read_bytes()).hexdigest()
        (self.site / 'evil.tar.00').write_bytes(evil.read_bytes())
        m = self.base / 'm.json'
        m.write_text(json.dumps({'url': self.url, 'packs': {'ru-course': {'size': evil.stat().st_size, 'sha256': sha,
                     'parts': [{'name': 'evil.tar.00', 'size': evil.stat().st_size, 'sha256': sha}]}}}))
        self.assertEqual(self.fetch(m, 'ru-course', self.base / 'x' / 'library'), 1)
        self.assertFalse((self.base / 'escape.txt').exists())
