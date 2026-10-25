import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/audit-online-accounts.py'
spec = importlib.util.spec_from_file_location('kirin_account_policy', SOURCE)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

class AccountAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.status = self.root / 'var/lib/dpkg/status'
        self.status.parent.mkdir(parents=True)

    def add(self, packages):
        self.status.write_text(''.join(
            f'Package: {p}\nStatus: install ok installed\nVersion: 1.0\n\n' for p in packages),
            encoding='utf-8')

    def launcher(self, name, text):
        path = self.root / 'usr/share/applications' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def test_block_verified_token_package(self):
        self.add(['accountsservice', 'openkylin-token-center'])
        self.assertEqual(policy.main(['--root', str(self.root)]), 1)

    def test_local_users_are_not_cloud_accounts(self):
        self.add(['accountsservice', 'passwd', 'login', 'ukui-control-center', 'ollama'])
        self.launcher('users.desktop', '[Desktop Entry]\nName=Local User Accounts\nExec=ukui-control-center\n')
        self.assertEqual(policy.main(['--root', str(self.root)]), 0)

    def test_cloud_sync_launcher_blocks(self):
        self.add(['accountsservice'])
        self.launcher('cloud.desktop', '[Desktop Entry]\nName=Cloud Account\nExec=cloud-account\n')
        self.assertEqual(policy.main(['--root', str(self.root)]), 1)

    def test_device_binding_blocks(self):
        self.add(['ukui-session-manager'])
        self.launcher('tokens.desktop', '[Desktop Entry]\nName=Token Center\nComment=Bind your device\n')
        self.assertEqual(policy.main(['--root', str(self.root)]), 1)

    def test_web_apps_allowed(self):
        self.add(['accountsservice'])
        self.launcher('claude.desktop', '[Desktop Entry]\nName=Claude\nExec=chromium --app=https://claude.ai\n')
        self.assertEqual(policy.main(['--root', str(self.root)]), 0)

    def test_does_not_scan_ai_payload(self):
        self.add(['accountsservice'])
        data = self.root / 'usr/share/ollama/models/blobs/sha256-blob'
        data.parent.mkdir(parents=True, exist_ok=True)
        data.write_bytes(b'openkylin-token-center')
        self.assertEqual(policy.main(['--root', str(self.root)]), 0)
        self.assertEqual(data.read_bytes(), b'openkylin-token-center')

    def test_missing_dpkg_db_is_unknown_not_pass(self):
        self.assertEqual(policy.main(['--root', str(self.root)]), 2)

    def test_no_live_root(self):
        self.assertEqual(policy.main(['--root', '/']), 2)

    def test_no_symlinks_in_scan(self):
        self.add(['accountsservice'])
        d = self.root / 'usr/share/applications'
        d.mkdir(parents=True)
        (d / 'link.desktop').symlink_to(self.status)
        self.assertEqual(policy.main(['--root', str(self.root)]), 2)

    def test_unverified_package_must_review(self):
        self.add(['kylin-cloud-sync'])
        self.assertEqual(policy.main(['--root', str(self.root)]), 1)

if __name__ == '__main__':
    unittest.main()
