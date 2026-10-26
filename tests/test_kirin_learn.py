import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kirin_learn', ROOT / 'kirin_learn.py')
learn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(learn)

class KirinLearnTests(unittest.TestCase):
    def test_topics_from_offline_directory(self):
        with patch.object(learn, 'TOPIC_PATH', ROOT / 'lessons'):
            self.assertGreaterEqual(len(learn.topics()), 5)
    def test_path_traversal_refused(self):
        with patch.object(learn, 'TOPIC_PATH', ROOT / 'lessons'):
            with self.assertRaises(ValueError):
                learn.show('../../etc/passwd')
    def test_explain_does_not_execute(self):
        output = io.StringIO()
        with patch.object(learn.subprocess, 'call', side_effect=AssertionError('executed')):
            with contextlib.redirect_stdout(output):
                learn.explain('apt update; echo attack')
        self.assertIn('did not execute', output.getvalue())
    def test_coding_model_and_loopback(self):
        self.assertEqual(learn.MODEL, 'qwen2.5-coder:7b-instruct')
        self.assertTrue(learn.API.startswith('http://127.0.0.1:'))
    def test_tutor_command(self):
        with patch.object(learn.shutil, 'which', return_value='/usr/bin/nvim'):
            with patch.object(learn.subprocess, 'call', return_value=0) as call:
                learn.tutor('neovim')
        call.assert_called_once_with(['nvim', '-c', 'Tutor kirin-01-basics'])
    def test_cli_missing_topics_nonzero(self):
        with patch.object(learn, 'TOPIC_PATH', Path('/definitely-missing-kirin-dir')):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(learn.main(['topics']), 1)
    def test_staging_installer(self):
        import os, subprocess
        with tempfile.TemporaryDirectory() as td:
            env = {**os.environ, 'DESTDIR': td}
            subprocess.run(['sh', str(ROOT / 'scripts/install-education.sh')], env=env, check=True, capture_output=True)
            self.assertTrue((Path(td)/'usr/bin/kirin-learn').exists())
            self.assertTrue((Path(td)/'usr/share/nvim/site/tutor/kirin-01-basics.tutor').exists())
            self.assertEqual(len(list((Path(td)/'usr/share/kirin/learn/topics').glob('*.md'))), 7)
            self.assertTrue((Path(td)/'usr/share/applications/kirin-russian-tutor.desktop').exists())
            self.assertTrue((Path(td)/'usr/bin/kirin-welcome').exists())
            self.assertTrue((Path(td)/'etc/xdg/autostart/kirin-welcome.desktop').exists())
            vocab = (Path(td)/'usr/share/kirin/russian/vocab.tsv').read_text(encoding='utf-8')
            self.assertEqual(sum(1 for l in vocab.splitlines() if l and not l.startswith('#')), 10000)
            for name in ('words', 'audiobooks', 'path', 'wikisource', 'wikipedia'):
                self.assertTrue((Path(td)/f'usr/share/applications/kirin-russian-{name}.desktop').exists(), name)


class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


class RussianTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'voices').mkdir()
        (self.root / 'voices/ru_RU-irina-medium.onnx').write_bytes(b'voice')
        piper = self.root / 'piper'
        piper.write_text('#!/bin/sh\nexit 0\n'); piper.chmod(0o755)
        lib = self.root / 'library/DLI Russian Basic Course'
        (lib / 'Audio').mkdir(parents=True)
        (lib / 'Mod 01.pdf').write_bytes(b'%PDF'); (lib / 'Audio/Tape.mp3').write_bytes(b'ID3')
        config = self.root / 'russian.json'
        config.write_text(json.dumps({'model': 'tutor:test', 'piper': str(piper), 'voices': str(self.root / 'voices'),
                                      'library': str(self.root / 'library'), 'dictionary': ''}))
        patcher = patch.object(learn, 'RUSSIAN_CONFIG', config)
        patcher.start(); self.addCleanup(patcher.stop)

    def test_tutor_uses_local_model_and_level(self):
        sent = {}
        def fake_urlopen(req, timeout):
            sent.update(json.loads(req.data)); sent['url'] = req.full_url
            return FakeResponse(b'{"message":{"content":"\u041f\u0440\u0438"}}\n{"message":{"content":"\u0432\u0435\u0442"}}\n')
        out = io.StringIO()
        with patch.object(learn.request, 'urlopen', fake_urlopen), contextlib.redirect_stdout(out):
            learn.russian('How do I say hello?', 'B1')
        self.assertEqual(sent['model'], 'tutor:test')
        self.assertTrue(sent['url'].startswith('http://127.0.0.1:'))
        self.assertIn('level B1', sent['messages'][0]['content'])
        self.assertIn('Привет', out.getvalue())
        self.assertIn('can be wrong', out.getvalue())

    def test_default_model_is_the_large_tutor(self):
        self.assertTrue(learn.RUSSIAN_DEFAULTS['model'].startswith('qwen3:30b'))

    def test_say_strips_stress_and_plays(self):
        calls = []
        def fake_run(cmd, input, capture_output):
            calls.append((cmd, input)); Path(cmd[cmd.index('--output_file') + 1]).write_bytes(b'RIFF')
            return subprocess_result(0)
        with patch.object(learn.subprocess, 'run', fake_run), \
             patch.object(learn.shutil, 'which', lambda name: '/usr/bin/' + name if name == 'aplay' else None), \
             patch.object(learn.subprocess, 'call', return_value=0) as play:
            self.assertEqual(learn.say('молоко́'), 0)
        self.assertEqual(calls[0][1].decode(), 'молоко')
        self.assertEqual(play.call_args[0][0][:2], ['aplay', '-q'])

    def test_say_rejects_unknown_voice(self):
        with self.assertRaises(ValueError):
            learn.say('да', voice='nobody')

    def test_library_lists_courses(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            learn.library()
        self.assertIn('DLI Russian Basic Course', out.getvalue())
        self.assertRegex(out.getvalue(), r'1 books/workbooks\s+1 audio')

    def test_missing_dictionary_is_reported(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(learn.main(['dictionary']), 1)


class VocabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        words = self.root / 'vocab.tsv'
        words.write_text('# header\n1\tA1\tother\tда\tyes\t\n2\tA1\tnoun\tмолоко́\tmilk\tneut.\n'
                         '3\tA2\tverb\tидти́\tgo\timpf.\n4\tB1\tnoun\tёж\thedgehog\tmasc.\n', encoding='utf-8')
        config = self.root / 'russian.json'
        config.write_text(json.dumps({'vocab': str(words), 'audiobooks': str(self.root / 'books'),
                                      'mezhdunami': str(self.root / 'mn'), 'kiwix': {}}))
        for name, value in (('RUSSIAN_CONFIG', config), ('VOCAB_STATE', self.root / 'state/vocab.json')):
            p = patch.object(learn, name, value); p.start(); self.addCleanup(p.stop)

    def drill(self, answers, **kw):
        replies = iter(answers)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            learn.vocab(ask=lambda prompt: next(replies), **kw)
        return out.getvalue(), json.loads(learn.VOCAB_STATE.read_text(encoding='utf-8'))

    def test_new_words_come_from_the_level_and_below(self):
        import datetime
        today = datetime.date(2026, 10, 26)
        _, state = self.drill(['', 'y', '', 'n'], level='A1', new=5, today=today)
        self.assertEqual(set(state), {'да|other', 'молоко́|noun'})
        self.assertEqual(state['да|other'], {'box': 1, 'seen': 1, 'due': '2026-10-27'})
        self.assertEqual(state['молоко́|noun']['box'], 1)

    def test_known_words_move_up_and_wrong_ones_go_back(self):
        import datetime
        day = datetime.date(2026, 10, 26)
        self.drill(['', 'y'], level='A1', new=1, today=day)
        _, state = self.drill(['', 'y'], level='A1', new=0, today=day + datetime.timedelta(days=1))
        self.assertEqual(state['да|other']['box'], 2)
        self.assertEqual(state['да|other']['due'], '2026-10-29')
        _, state = self.drill(['', 'n'], level='A1', new=0, today=day + datetime.timedelta(days=3))
        self.assertEqual(state['да|other']['box'], 1)

    def test_reverse_accepts_missing_stress_and_yo(self):
        out, state = self.drill(['да', 'молоко', 'идти', 'еж'], level='B1', new=4, reverse=True)
        self.assertEqual(out.count('  yes: '), 4)
        out, _ = self.drill(['нет'] + ['q'], level='B1', new=0, reverse=True,
                            today=__import__('datetime').date.today() + __import__('datetime').timedelta(days=5))
        self.assertIn('  no: да', out)

    def test_quit_saves_progress(self):
        out, state = self.drill(['', 'y', 'q'], level='A2', new=3)
        self.assertEqual(list(state), ['да|other'])

    def test_stats_and_path(self):
        self.drill(['', 'y'], level='A1', new=1)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            learn.main(['vocab', '--stats'])
            learn.main(['path'])
        self.assertIn('A1:     0/2 mastered, 0 learned, 1 started', out.getvalue())
        self.assertIn('B2  Confident Russian', out.getvalue())
        self.assertIn('kirin-learn read mezhdunami', out.getvalue())

    def test_listen_lists_and_plays_by_level(self):
        books = self.root / 'books'
        (books / 'A2/Сказки - Afanasyev').mkdir(parents=True)
        (books / 'catalog.json').write_text(json.dumps([
            {'id': 'a', 'level': 'A2', 'title': 'Сказки', 'creator': 'Afanasyev', 'runtime': '2:00:00',
             'folder': 'A2/Сказки - Afanasyev', 'files': ['1.mp3']},
            {'id': 'b', 'level': 'B2', 'title': 'Обрыв', 'creator': 'Goncharov', 'runtime': '', 'folder': 'B2/x', 'files': []}]))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            learn.listen('A2')
        self.assertIn('[A2] Сказки - Afanasyev', out.getvalue())
        self.assertNotIn('Обрыв', out.getvalue())
        with patch.object(learn.shutil, 'which', lambda n: '/usr/bin/vlc' if n == 'vlc' else None), \
             patch.object(learn.subprocess, 'call', return_value=0) as call:
            learn.listen('A2', 1)
        self.assertEqual(call.call_args[0][0][-1], str(books / 'A2/Сказки - Afanasyev'))

    def test_read_opens_kiwix_or_reports(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(learn.main(['read', 'wikipedia']), 1)
        zim = self.root / 'ws.zim'; zim.write_bytes(b'zim')
        cfg = json.loads(learn.RUSSIAN_CONFIG.read_text()); cfg['kiwix'] = {'wikisource': str(zim)}
        learn.RUSSIAN_CONFIG.write_text(json.dumps(cfg))
        with patch.object(learn.subprocess, 'call', return_value=0) as call:
            learn.read('wikisource')
        call.assert_called_once_with(['flatpak', 'run', 'org.kiwix.desktop', str(zim)])

    def test_real_word_list_is_banded(self):
        words = learn.load_vocab(ROOT / 'packaging/russian/vocab.tsv')
        counts = {lvl: sum(w['level'] == lvl for w in words) for lvl in learn.VOCAB_LEVELS}
        self.assertEqual(counts, {'A1': 780, 'A2': 520, 'B1': 1000, 'B2': 7700})
        self.assertEqual(len({w['key'] for w in words}), len(words))


def subprocess_result(code):
    from types import SimpleNamespace
    return SimpleNamespace(returncode=code, stderr=b'')

if __name__ == '__main__': unittest.main()


welcome_spec = importlib.util.spec_from_file_location('kirin_welcome', ROOT / 'kirin_welcome.py')
welcome = importlib.util.module_from_spec(welcome_spec)
welcome_spec.loader.exec_module(welcome)


class WelcomeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.apps = base / 'apps'; self.apps.mkdir()
        (self.apps / 'kirin-learn.desktop').write_text('[Desktop Entry]\n')
        (self.apps / 'com.jeffser.Alpaca.desktop').write_text('[Desktop Entry]\n')
        for name, value in (('APP_DIRS', (self.apps,)), ('STATE', base / 'state'), ('DONE', base / 'state/welcome-done'),
                            ('ALWAYS', base / 'state/welcome-always'), ('NO_FASTFETCH', base / 'state/no-fastfetch')):
            p = patch.object(welcome, name, value); p.start(); self.addCleanup(p.stop)

    def test_lists_only_installed_items(self):
        titles = [t for _, t, _ in welcome.available_items('en')]
        self.assertEqual(titles, ['Learn Linux', 'AI chat'])
        self.assertEqual([t for _, t, _ in welcome.available_items('ru')], ['Изучить Linux', 'ИИ-чат'])

    def test_shows_once_unless_asked(self):
        self.assertTrue(welcome.should_autostart())
        welcome.set_flag(welcome.DONE, True)
        self.assertFalse(welcome.should_autostart())
        welcome.set_flag(welcome.ALWAYS, True)
        self.assertTrue(welcome.should_autostart())

    def test_language_from_environment(self):
        with patch.dict(welcome.os.environ, {'LANGUAGE': 'ru_RU:ru', 'LANG': 'en_GB.UTF-8'}):
            self.assertEqual(welcome.language(), 'ru')
        with patch.dict(welcome.os.environ, {'LANGUAGE': '', 'LC_ALL': '', 'LC_MESSAGES': '', 'LANG': 'en_GB.UTF-8'}):
            self.assertEqual(welcome.language(), 'en')

    def test_text_fallback_marks_seen(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            welcome.run_text('en')
        self.assertIn('Welcome to Kirin Linux', out.getvalue())
        self.assertFalse(welcome.should_autostart())
