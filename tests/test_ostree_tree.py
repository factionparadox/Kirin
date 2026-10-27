"""scripts/build/ostree-tree.sh lays out a system root the way openKylin's OSTree commit does."""
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/build/ostree-tree.sh'


class TestOstreeTree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root, self.tree = base / 'root', base / 'tree'
        r = self.root
        for d in ['usr/bin', 'usr/lib/modules/7.0.0-3-generic', 'etc', 'var/lib', 'boot', 'opt/kirin',
                  'proc', 'sys', 'dev', 'run', 'tmp', 'home/live', 'root', 'kirin-build', 'sysroot/ostree/repo', 'srv']:
            (r / d).mkdir(parents=True)
        (r / 'usr/bin/kirin-learn').write_text('#!/bin/sh\n')
        (r / 'etc/os-release').write_text('NAME="Kirin Linux"\n')
        (r / 'etc/machine-id').write_text('abc123\n')
        (r / 'opt/kirin/piper').write_text('piper')
        (r / 'boot/vmlinuz-7.0.0-3-generic').write_text('kernel')
        (r / 'boot/initrd.img-7.0.0-3-generic').write_text('initrd')
        (r / 'root/.bashrc').write_text('# root\n')
        (r / 'home/live/secret').write_text('x')
        (r / 'tmp/junk').write_text('x')
        for name in ['bin', 'lib', 'sbin']:
            (r / name).symlink_to(f'usr/{name}')

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self):
        return subprocess.run(['sh', str(SCRIPT), str(self.root), str(self.tree)],
                              capture_output=True, text=True, input='')

    def test_layout_matches_openkylin(self):
        res = self.run_script()
        self.assertEqual(res.returncode, 0, res.stderr)
        t = self.tree
        self.assertFalse((t / 'etc').exists())
        self.assertEqual((t / 'usr/etc/os-release').read_text(), 'NAME="Kirin Linux"\n')
        mid = t / 'usr/etc/machine-id'
        self.assertEqual(mid.read_text(), '')
        self.assertEqual(stat.S_IMODE(mid.stat().st_mode), 0o444)
        for link, target in {'opt': 'var/opt', 'mnt': 'var/mnt', 'srv': 'var/srv', 'tmp': 'var/tmp',
                             'media': 'run/media', 'ostree': 'sysroot/ostree', 'bin': 'usr/bin'}.items():
            self.assertTrue((t / link).is_symlink(), link)
            self.assertEqual(os.readlink(t / link), target)
        self.assertEqual((t / 'var/opt/kirin/piper').read_text(), 'piper')
        mods = t / 'usr/lib/modules/7.0.0-3-generic'
        self.assertEqual((mods / 'vmlinuz').read_text(), 'kernel')
        self.assertEqual((mods / 'initramfs.img').read_text(), 'initrd')
        for d in ['proc', 'sys', 'dev', 'run', 'sysroot', 'home', 'data', 'backup', 'eth']:
            self.assertTrue((t / d).is_dir() and not any((t / d).iterdir()), d)
        self.assertEqual(stat.S_IMODE((t / 'root').stat().st_mode), 0o700)
        self.assertTrue((t / 'root/.bashrc').is_file())
        self.assertFalse((t / 'kirin-build').exists())
        self.assertFalse(any((t / 'var/tmp').iterdir()))

    def test_hard_links_and_root_untouched(self):
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(os.stat(self.root / 'usr/bin/kirin-learn').st_ino,
                         os.stat(self.tree / 'usr/bin/kirin-learn').st_ino)
        self.assertEqual((self.root / 'etc/machine-id').read_text(), 'abc123\n')
        self.assertTrue((self.root / 'etc/os-release').is_file())
        self.assertTrue((self.root / 'opt/kirin/piper').is_file())

    def test_needs_a_kernel(self):
        (self.root / 'boot/vmlinuz-7.0.0-3-generic').unlink()
        res = self.run_script()
        self.assertNotEqual(res.returncode, 0)
        self.assertIn('no kernel', res.stderr)


if __name__ == '__main__':
    unittest.main()
