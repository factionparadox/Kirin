import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("kirin_localise", Path(__file__).resolve().parents[1] / "scripts/kirin-localise.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class TestImageLocale(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for filename in ("usr/share/locale/zh_CN/LC_MESSAGES/panel.mo",
                         "usr/share/locale/ru_RU/LC_MESSAGES/panel.mo",
                         "usr/share/qt6/translations/qt_zh_CN.qm",
                         "usr/share/fonts/noto-cjk.otf",
                         "usr/share/ollama/models/blobs/sha256-upstream"):
            path = self.root / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"untouched")
        desktop = self.root / "usr/share/applications/demo.desktop"
        desktop.parent.mkdir(parents=True, exist_ok=True)
        desktop.write_text("[Desktop Entry]\nName=Example\nName[zh_CN]=例子\nName[ru]=Пример\n", encoding="utf-8")

    def test_plan_no_mutation(self):
        self.assertEqual(mod.main(["--root", str(self.root), "--plan"]), 0)
        self.assertTrue((self.root / "usr/share/locale/zh_CN/LC_MESSAGES/panel.mo").is_file())

    def test_apply_and_audit(self):
        self.assertEqual(mod.main(["--root", str(self.root), "--apply"]), 0)
        self.assertEqual(mod.main(["--root", str(self.root), "--audit"]), 0)
        self.assertFalse((self.root / "usr/share/locale/zh_CN").exists())
        self.assertFalse((self.root / "usr/share/qt6/translations/qt_zh_CN.qm").exists())
        self.assertTrue((self.root / "usr/share/locale/ru_RU/LC_MESSAGES/panel.mo").exists())
        self.assertTrue((self.root / "usr/share/fonts/noto-cjk.otf").exists())
        self.assertTrue((self.root / "usr/share/ollama/models/blobs/sha256-upstream").exists())
        self.assertIn("Name[ru]", (self.root / "usr/share/applications/demo.desktop").read_text())
        self.assertNotIn("Name[zh_CN]", (self.root / "usr/share/applications/demo.desktop").read_text())
        self.assertIn("ru_RU.UTF-8", (self.root / "etc/locale.gen").read_text())

    def test_known_chinese_default_translated(self):
        p = self.root / "usr/share/applications/ukui-control-center.desktop"
        p.write_text("[Desktop Entry]\nName=Settings\nComment=UKUI控制面板\nComment[zh_CN]=UKUI控制面板\n", encoding="utf-8")
        self.assertEqual(mod.main(["--root", str(self.root), "--apply"]), 0)
        self.assertEqual(mod.main(["--root", str(self.root), "--audit"]), 0)
        text = p.read_text(encoding="utf-8")
        self.assertIn("Comment=UKUI control panel\n", text)
        self.assertIn("Comment[ru]=Панель управления UKUI\n", text)
        self.assertNotIn("控制", text)

    def test_untranslated_default_fails(self):
        p = self.root / "usr/share/applications/untranslated.desktop"
        p.write_text("[Desktop Entry]\nName=中文\n", encoding="utf-8")
        self.assertEqual(mod.main(["--root", str(self.root), "--apply"]), 1)

    def test_no_live_root(self):
        self.assertEqual(mod.main(["--root", "/", "--apply"]), 2)

    def test_symlinks_removed_without_following(self):
        parent = self.root / "usr/share/locale"
        (parent / "zh_TW").symlink_to(parent / "ru_RU", target_is_directory=True)
        inner = parent / "zh_CN/LC_MESSAGES/link.mo"
        inner.symlink_to(parent / "ru_RU/LC_MESSAGES/panel.mo")
        qt = self.root / "usr/share/qt6/translations/qtbase_zh_CN.qm"
        qt.symlink_to(parent / "ru_RU/LC_MESSAGES/panel.mo")
        self.assertEqual(mod.main(["--root", str(self.root), "--apply"]), 0)
        self.assertEqual(mod.main(["--root", str(self.root), "--audit"]), 0)
        for link in (parent / "zh_TW", inner, qt):
            self.assertFalse(link.is_symlink(), link)
        self.assertEqual((parent / "ru_RU/LC_MESSAGES/panel.mo").read_bytes(), b"untouched")

    def test_symlinked_policy_file_replaced_not_followed(self):
        etc = self.root / "etc"
        (etc / "default").mkdir(parents=True)
        (etc / "locale.conf").write_text("LANG=zh_CN.UTF-8\n")
        (etc / "default/locale").symlink_to("../locale.conf")
        self.assertEqual(mod.main(["--root", str(self.root), "--apply"]), 0)
        self.assertFalse((etc / "default/locale").is_symlink())
        self.assertEqual(mod.main(["--root", str(self.root), "--audit"]), 0)
        self.assertEqual((etc / "locale.conf").read_text(), "LANG=en_GB.UTF-8\n")

    def test_symlinked_scan_root_still_refused(self):
        real = self.root / "elsewhere"
        real.mkdir()
        share = self.root / "usr/share"
        (share / "locale").rename(real / "locale")
        (share / "locale").symlink_to(real / "locale", target_is_directory=True)
        self.assertEqual(mod.main(["--root", str(self.root), "--apply"]), 2)
