"""scripts/build/qtres.py: find and replace Qt resources in place."""
import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rccfixture import make_program  # noqa: E402

spec = importlib.util.spec_from_file_location('kirin_qtres', Path(__file__).resolve().parents[1] / 'scripts/build/qtres.py')
q = importlib.util.module_from_spec(spec); sys.modules['kirin_qtres'] = q; spec.loader.exec_module(q)

FILES = {':/data/png/bg.jpg': b'J' * 5000, ':/data/png/slides/4.png': b'P' * 3000,
         ':/data/qss/main.css': b'QLabel { color: white; }' * 20, ':/res/file/EULA': b'licence ' * 400}


class TestQtRes(unittest.TestCase):
    def setUp(self):
        self.buf = bytearray(make_program(FILES, compress={':/res/file/EULA'}))

    def found(self):
        return {r.path: r for r in q.resources(self.buf)}

    def test_lists_and_reads(self):
        res = self.found()
        self.assertEqual(set(res), set(FILES))
        for path, data in FILES.items():
            self.assertEqual(q.content(self.buf, res[path]), data, path)
        self.assertTrue(res[':/res/file/EULA'].flags & q.COMPRESSED)

    def test_replace_smaller_keeps_everything_else(self):
        before = bytes(self.buf)
        q.replace(self.buf, self.found()[':/data/png/bg.jpg'], b'kirin')
        self.assertEqual(len(self.buf), len(before))
        res = self.found()
        self.assertEqual(q.content(self.buf, res[':/data/png/bg.jpg']), b'kirin')
        for path in set(FILES) - {':/data/png/bg.jpg'}:
            self.assertEqual(q.content(self.buf, res[path]), FILES[path])
        self.assertEqual(res[':/data/png/bg.jpg'].capacity, 5000)     # space is remembered
        q.replace(self.buf, res[':/data/png/bg.jpg'], b'x' * 5000)     # and can be filled again
        self.assertEqual(q.content(self.buf, self.found()[':/data/png/bg.jpg']), b'x' * 5000)

    def test_compressed_original_becomes_raw(self):
        r = self.found()[':/res/file/EULA']
        q.replace(self.buf, r, b'Kirin licence')
        r = self.found()[':/res/file/EULA']
        self.assertFalse(r.flags & q.COMPRESSED)
        self.assertEqual(q.content(self.buf, r), b'Kirin licence')

    def test_large_replacement_is_compressed_or_refused(self):
        r = self.found()[':/data/png/slides/4.png']
        q.replace(self.buf, r, b'A' * 20000)                          # compresses into 3000
        r = self.found()[':/data/png/slides/4.png']
        self.assertTrue(r.flags & q.COMPRESSED)
        self.assertEqual(q.content(self.buf, r), b'A' * 20000)
        with self.assertRaises(ValueError):
            q.replace(self.buf, r, bytes(range(256)) * 100)          # 25600 random-ish bytes


if __name__ == '__main__':
    unittest.main()
