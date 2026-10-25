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


def subprocess_result(code):
    from types import SimpleNamespace
    return SimpleNamespace(returncode=code, stderr=b'')

if __name__ == '__main__': unittest.main()
