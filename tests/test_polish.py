import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kirin_polish', ROOT / 'scripts/kirin-polish.py')
polish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(polish)
MIME = (ROOT / 'tests/fixtures/openkylin-3.0-mimeapps.list').read_text()


def quiet(*args):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return polish.main(list(args))


class TestPolish(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'root'
        apps = self.root / 'usr/share/applications'
        apps.mkdir(parents=True)
        for d in ('libreoffice-writer', 'libreoffice-calc', 'libreoffice-impress', 'libreoffice-startcenter',
                  'vlc', 'atril', 'peony', 'mate-terminal', 'kirin-learn'):
            (apps / f'{d}.desktop').write_text('[Desktop Entry]\n')
        flat = self.root / 'var/lib/flatpak/exports/share/applications'
        flat.mkdir(parents=True)
        (flat / 'com.jeffser.Alpaca.desktop').write_text('[Desktop Entry]\n')
        (apps / 'ukui-mimeapps.list').write_text(MIME)
        (apps / 'mimeapps.list').write_text('[Default Applications]\ntext/csv=wps-office-et.desktop\n'
                                            'application/msword=wps-office-wps.desktop\n[Added Associations]\nx=y\n')
        etc = self.root / 'etc'; etc.mkdir()
        (etc / 'hostname').write_text('localhost.localdomain\n')
        (etc / 'hosts').write_text('')
        (etc / 'bash.bashrc').write_text('# system bashrc\n')
        (etc / 'casper.conf').write_text('export USERNAME="ubuntu"\nexport HOST="ubuntu"\n# export FLAVOUR="Ubuntu"\n')

    def test_apply_then_audit(self):
        self.assertEqual(quiet('--root', str(self.root), '--audit'), 1)
        self.assertEqual(quiet('--root', str(self.root), '--apply'), 0)
        self.assertEqual(quiet('--root', str(self.root), '--audit'), 0)

    def test_default_apps_from_real_openkylin_list(self):
        quiet('--root', str(self.root), '--apply')
        ukui = (self.root / 'usr/share/applications/ukui-mimeapps.list').read_text()
        self.assertIn('video/mp4=vlc.desktop', ukui)
        self.assertIn('audio/mpeg=vlc.desktop', ukui)
        self.assertIn('application/pdf=atril.desktop', ukui)
        self.assertIn('image/png=kylin-photo-viewer.desktop', ukui)       # untouched: no replacement chosen
        self.assertIn('application/x-cd-image=engrampa.desktop;kylin-burner.desktop', ukui)
        self.assertIn('application/vnd.oasis.opendocument.text=libreoffice-writer.desktop', ukui)
        xdg = (self.root / 'usr/share/applications/mimeapps.list').read_text()
        self.assertIn('text/csv=libreoffice-calc.desktop', xdg)
        self.assertIn('[Added Associations]\nx=y', xdg)                  # other sections preserved
        self.assertNotIn('wps-office', xdg)

    def test_missing_target_leaves_mapping(self):
        (self.root / 'usr/share/applications/vlc.desktop').unlink()
        quiet('--root', str(self.root), '--apply')
        self.assertIn('video/mp4=kylin-video.desktop', (self.root / 'usr/share/applications/ukui-mimeapps.list').read_text())

    def test_identity_and_live_session(self):
        quiet('--root', str(self.root), '--apply')
        self.assertEqual((self.root / 'etc/hostname').read_text(), 'kirin\n')
        self.assertIn('127.0.1.1\tkirin', (self.root / 'etc/hosts').read_text())
        casper = (self.root / 'etc/casper.conf').read_text()
        self.assertIn('export HOST="kirin"', casper)
        self.assertIn('export USERNAME="kirin"', casper)
        self.assertIn('export FLAVOUR="Kirin"', casper)
        self.assertIn('KIRIN_VERSION="1.0"', (self.root / 'etc/kirin-release').read_text())

    def test_fastfetch_hook_once_with_opt_out(self):
        quiet('--root', str(self.root), '--apply')
        quiet('--root', str(self.root), '--apply')
        bashrc = (self.root / 'etc/bash.bashrc').read_text()
        self.assertEqual(bashrc.count(polish.BASHRC_BEGIN), 1)
        self.assertIn('no-fastfetch', bashrc)
        self.assertIn('KIRIN_FASTFETCH_SHOWN', bashrc)

    def test_taskbar_pins_only_installed(self):
        quiet('--root', str(self.root), '--apply')
        pins = json.loads((self.root / polish.PINS_FILE).read_text())['quickLaunchers']
        self.assertEqual(pins[:2], ['/usr/share/applications/peony.desktop', '/usr/share/applications/mate-terminal.desktop'])
        self.assertIn('/var/lib/flatpak/exports/share/applications/com.jeffser.Alpaca.desktop', pins)
        self.assertNotIn('/usr/share/applications/firefox.desktop', pins)

    def add_kitty(self, fish=True):
        apps = self.root / 'usr/share/applications'
        (apps / 'kitty.desktop').write_text('[Desktop Entry]\n')
        (apps / 'mate-terminal.desktop').write_text('[Desktop Entry]\nName=MATE Terminal\nExec=mate-terminal\n')
        if fish:
            (self.root / 'usr/bin').mkdir(parents=True, exist_ok=True)
            (self.root / 'usr/bin/fish').write_text('')
        schemas = self.root / 'usr/share/glib-2.0/schemas'
        schemas.mkdir(parents=True)
        (schemas / 'org.mate.applications.gschema.xml').write_text(
            '<schemalist><schema id="org.mate.applications-terminal" path="/x/"></schema></schemalist>')

    def test_kitty_becomes_default_with_fish(self):
        self.add_kitty()
        quiet('--root', str(self.root), '--apply')
        conf = (self.root / 'etc/xdg/kitty/kitty.conf').read_text()
        self.assertIn('background_opacity         0.85', conf)
        self.assertIn('background_blur            32', conf)
        self.assertIn('shell /usr/bin/fish', conf)
        self.assertIn('fastfetch', (self.root / 'etc/fish/conf.d/kirin.fish').read_text())
        self.assertEqual((self.root / 'etc/xdg/xdg-terminals.list').read_text(), 'kitty.desktop\n')
        override = (self.root / polish.SCHEMA_OVERRIDE).read_text()
        self.assertIn("[org.mate.applications-terminal]\nexec='kitty'", override)
        self.assertNotIn('org.gnome.desktop.default-applications.terminal', override)   # schema absent: skipped
        mate = (self.root / 'usr/share/applications/mate-terminal.desktop').read_text()
        self.assertIn('[Desktop Entry]\nNoDisplay=true\n', mate)
        pins = json.loads((self.root / polish.PINS_FILE).read_text())['quickLaunchers']
        self.assertIn('/usr/share/applications/kitty.desktop', pins)
        self.assertNotIn('/usr/share/applications/mate-terminal.desktop', pins)
        self.assertEqual(quiet('--root', str(self.root), '--audit'), 0)
        quiet('--root', str(self.root), '--apply')
        self.assertEqual((self.root / 'usr/share/applications/mate-terminal.desktop').read_text().count('NoDisplay'), 1)

    def test_kitty_without_fish_keeps_default_shell(self):
        self.add_kitty(fish=False)
        quiet('--root', str(self.root), '--apply')
        self.assertNotIn('shell /usr/bin/fish', (self.root / 'etc/xdg/kitty/kitty.conf').read_text())
        self.assertFalse((self.root / 'etc/fish/conf.d/kirin.fish').exists())

    def test_no_kitty_keeps_mate(self):
        quiet('--root', str(self.root), '--apply')
        self.assertFalse((self.root / 'etc/xdg/kitty/kitty.conf').exists())
        pins = json.loads((self.root / polish.PINS_FILE).read_text())['quickLaunchers']
        self.assertIn('/usr/share/applications/mate-terminal.desktop', pins)

    def test_framework_ethernet_rule(self):
        quiet('--root', str(self.root), '--apply')
        rule = (self.root / polish.FRAMEWORK_UDEV).read_text()
        self.assertIn('ATTR{idVendor}=="0bda", ATTR{idProduct}=="8156", ATTR{power/autosuspend}="20"', rule)

    def test_refuses_live_root(self):
        self.assertEqual(quiet('--root', '/', '--apply'), 2)


if __name__ == '__main__':
    unittest.main()
