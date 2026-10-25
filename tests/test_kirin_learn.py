import contextlib
import importlib.util
import io
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
            self.assertEqual(len(list((Path(td)/'usr/share/kirin/learn/topics').glob('*.md'))), 6)

if __name__ == '__main__': unittest.main()
