import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/audit-software-image.py"
spec = importlib.util.spec_from_file_location("kirin_software_audit", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class TestSoftwareImage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write_packages("apt", "dpkg", "flatpak")
        for appid in module.FLATPAKS:
            appdir = self.root / "var/lib/flatpak/app" / appid / "x86_64/stable"
            appdir.mkdir(parents=True)
            launcher = self.root / "var/lib/flatpak/exports/share/applications" / (appid + ".desktop")
            launcher.parent.mkdir(parents=True, exist_ok=True)
            launcher.write_text("[Desktop Entry]\nType=Application\nName=Test\n", encoding="utf-8")

    def write_packages(self, *packages):
        status = self.root / "var/lib/dpkg/status"
        status.parent.mkdir(parents=True, exist_ok=True)
        status.write_text("\n\n".join(
            f"Package: {p}\nStatus: install ok installed\nVersion: 1.0" for p in packages
        ) + "\n", encoding="utf-8")

    def test_complete_stack(self):
        self.assertEqual(module.main(["--root", str(self.root)]), 0)

    def test_store_detected(self):
        self.write_packages("apt", "dpkg", "flatpak", "kylin-software-center")
        self.assertEqual(module.main(["--root", str(self.root)]), 1)

    def test_missing_flatpak(self):
        self.write_packages("apt", "dpkg")
        self.assertEqual(module.main(["--root", str(self.root)]), 1)

    def test_missing_warehouse(self):
        (self.root / "var/lib/flatpak/exports/share/applications/io.github.flattool.Warehouse.desktop").unlink()
        self.assertEqual(module.main(["--root", str(self.root)]), 1)

    def test_live_root_refused(self):
        self.assertEqual(module.main(["--root", "/"]), 2)

if __name__ == "__main__":
    unittest.main()
