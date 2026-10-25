import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rebrand = load(ROOT / 'scripts/kirin-rebrand.py', 'kirin_rebrand')
pgp = load(ROOT / 'scripts/build/pgp-fingerprint.py', 'pgp_fingerprint')


def quiet(fn, *args):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*args)


class TestRebrand(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'root'
        apps = self.root / 'usr/share/applications'
        apps.mkdir(parents=True)
        (apps / 'kylin-music.desktop').write_text(
            '[Desktop Entry]\nName=Kylin Music\nName[ru]=Музыка Kylin\nComment=Play music on openKylin\n'
            'Exec=/usr/bin/kylin-music %U\nIcon=kylin-music\nKeywords=kylin;music;\n', encoding='utf-8')
        (apps / 'files.desktop').write_text('[Desktop Entry]\nName=Files\nExec=peony\n', encoding='utf-8')
        lib = self.root / 'usr/lib'; lib.mkdir(parents=True)
        (lib / 'os-release').write_text('NAME="openKylin"\nID=openkylin\nVERSION_ID="3.0"\nPRETTY_NAME="openKylin 3.0"\n')
        (self.root / 'etc').mkdir()
        (self.root / 'etc/os-release').symlink_to('../usr/lib/os-release')
        (self.root / 'etc/lsb-release').write_text('DISTRIB_ID=openKylin\nDISTRIB_RELEASE=3.0\nDISTRIB_DESCRIPTION="openKylin 3.0"\n')

    def test_apply_then_audit(self):
        self.assertEqual(quiet(rebrand.main, ['--root', str(self.root), '--audit']), 1)
        self.assertEqual(quiet(rebrand.main, ['--root', str(self.root), '--apply']), 0)
        self.assertEqual(quiet(rebrand.main, ['--root', str(self.root), '--audit']), 0)
        music = (self.root / 'usr/share/applications/kylin-music.desktop').read_text(encoding='utf-8')
        self.assertIn('Name=Kirin Music\n', music)
        self.assertIn('Name[ru]=Музыка Kirin\n', music)
        self.assertIn('Comment=Play music on Kirin\n', music)
        self.assertIn('Exec=/usr/bin/kylin-music %U\n', music)      # programs untouched
        self.assertIn('Icon=kylin-music\n', music)

    def test_os_identity_keeps_id(self):
        quiet(rebrand.main, ['--root', str(self.root), '--apply'])
        osr = (self.root / 'usr/lib/os-release').read_text()
        self.assertIn('NAME="Kirin Linux"', osr)
        self.assertIn('PRETTY_NAME="Kirin Linux (openKylin 3.0 base)"', osr)
        self.assertIn('ID=openkylin', osr)                            # updater and packages still recognise it
        self.assertTrue((self.root / 'etc/os-release').is_symlink())  # link preserved, target edited
        self.assertIn('DISTRIB_ID=openKylin', (self.root / 'etc/lsb-release').read_text())
        self.assertIn('Kirin Linux (openKylin 3.0 base)', (self.root / 'etc/lsb-release').read_text())

    def test_installs_assets(self):
        quiet(rebrand.main, ['--root', str(self.root), '--apply'])
        for rel in ('etc/xdg/fastfetch/config.jsonc', 'usr/share/kirin/branding/fastfetch-logo.txt',
                    'usr/share/plymouth/themes/kirin/kirin.plymouth', 'usr/share/plymouth/themes/kirin/splash.png',
                    'usr/share/icons/hicolor/48x48/apps/kirin.png', 'etc/default/grub.d/90-kirin.cfg'):
            self.assertTrue((self.root / rel).is_file(), rel)

    def test_link_outside_image_refused(self):
        (self.root / 'etc/os-release').unlink()
        (self.root / 'etc/os-release').symlink_to('../../../../../../../../etc/hostname')
        (self.root / 'usr/lib/os-release').unlink()
        self.assertEqual(quiet(rebrand.main, ['--root', str(self.root), '--apply']), 2)

    def test_explicit_names_with_russian(self):
        apps = self.root / 'usr/share/applications'
        (apps / 'kylin-os-installer.desktop').write_text(
            '[Desktop Entry]\nName=Install openKylin\nExec=kylin-os-installer\n\n[Desktop Action x]\nName=Other\n', encoding='utf-8')
        quiet(rebrand.main, ['--root', str(self.root), '--apply'])
        text = (apps / 'kylin-os-installer.desktop').read_text(encoding='utf-8')
        self.assertIn('Name=Install Kirin Linux\n', text)
        self.assertIn('Name[ru]=Установить Kirin Linux\n', text)
        self.assertIn('Name=Other\n', text)                 # only the main entry is renamed
        self.assertEqual(text.count('Name[ru]='), 1)
        self.assertEqual(quiet(rebrand.main, ['--root', str(self.root), '--audit']), 0)

    def test_word_boundaries(self):
        self.assertEqual(rebrand.rebrand_desktop('Name=Kylinware and openKylin\n'), 'Name=Kylinware and Kirin\n')

    def test_refuses_live_root(self):
        self.assertEqual(quiet(rebrand.main, ['--root', '/', '--apply']), 2)


class TestFingerprint(unittest.TestCase):
    FIX = ROOT / 'tests/fixtures'

    def test_matches_gnupg_fingerprints(self):
        rsa, ed = (self.FIX / 'test-key-fingerprints.txt').read_text().split()
        self.assertEqual(pgp.primary_fingerprints((self.FIX / 'test-key-rsa.asc').read_bytes()), [rsa])
        self.assertEqual(sorted(pgp.primary_fingerprints((self.FIX / 'test-keys-two.gpg').read_bytes())), sorted([rsa, ed]))

    def test_wrong_or_extra_key_rejected(self):
        rsa, ed = (self.FIX / 'test-key-fingerprints.txt').read_text().split()
        self.assertEqual(quiet(pgp.main, [str(self.FIX / 'test-key-rsa.asc'), '--expect', ed]), 1)
        self.assertEqual(quiet(pgp.main, [str(self.FIX / 'test-keys-two.gpg'), '--expect', rsa]), 1)
        self.assertEqual(quiet(pgp.main, [str(self.FIX / 'test-key-rsa.asc'), '--expect', ' '.join(rsa[i:i+4] for i in range(0, 40, 4))]), 0)

    def test_binary_out_only_after_verification(self):
        rsa, ed = (self.FIX / 'test-key-fingerprints.txt').read_text().split()
        out = Path(tempfile.mkdtemp()) / 'k.gpg'
        self.assertEqual(quiet(pgp.main, [str(self.FIX / 'test-key-rsa.asc'), '--expect', ed, '--binary-out', str(out)]), 1)
        self.assertFalse(out.exists())
        self.assertEqual(quiet(pgp.main, [str(self.FIX / 'test-key-rsa.asc'), '--expect', rsa, '--binary-out', str(out)]), 0)
        self.assertEqual(pgp.primary_fingerprints(out.read_bytes()), [rsa])
        self.assertNotIn(b'BEGIN PGP', out.read_bytes())

    def test_garbage_rejected(self):
        bad = Path(tempfile.mkdtemp()) / 'bad.asc'
        bad.write_text('-----BEGIN PGP PUBLIC KEY BLOCK-----\n\n!!!\n-----END PGP PUBLIC KEY BLOCK-----\n')
        self.assertEqual(quiet(pgp.main, [str(bad), '--expect', '0' * 40]), 2)


if __name__ == '__main__':
    unittest.main()
