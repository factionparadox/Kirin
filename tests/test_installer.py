"""scripts/kirin-installer.py: no swap, English installer messages."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('kinst', Path(__file__).resolve().parents[1] / 'scripts/kirin-installer.py')
ki = importlib.util.module_from_spec(spec); spec.loader.exec_module(ki)

SCRIPT = '''#!/bin/bash
case ${LANGUAGES} in
        'zh_CN')
                echo "磁盘挂载完成" >>${LOG_PROGRESS_FILE}
                ;;
        'en_US')
                echo "Disk mounting completed" >>${LOG_PROGRESS_FILE}
                ;;
              *)
                echo "磁盘挂载完成" >>${LOG_PROGRESS_FILE}
                ;;
esac
msg "正在拷贝基础文件系统..."
        		msg "开始处理/opt/kare"
        		msg "处理/opt/kare完成"
        		msg "处理/var/kare-shadow"
msg "某个未知消息"
msg "设置用户 ${USERNAME}"
            msg "跳过 $i"
#    	msg "更新 initramfs"
echo "ghost镜像在磁盘跟目录"
'''
INI = '''[config]
automatic-installation = 1
enable-swapfile=true; 使用 swapfile
[setting]
EnableSwap = true
FileSystem="ext4;linux-swap"
'''


class TestInstaller(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        s = self.root / ki.SCRIPTS / 'prepare'
        s.mkdir(parents=True)
        self.script = s / '16copy-basic-filesystem'
        self.script.write_text(SCRIPT); self.script.chmod(0o755)
        self.ini = self.root / ki.INSTALLER / 'systemsetting.ini'
        self.ini.write_text(INI)

    def tearDown(self):
        self.tmp.cleanup()

    def test_apply_then_audit_passes(self):
        self.assertTrue(ki.audit(self.root))
        notes = ki.apply(self.root)
        self.assertIn('untranslated installer message: 某个未知消息', notes)
        self.assertEqual(ki.audit(self.root), [])
        text = self.script.read_text()
        star = text.split('*)')[1].split(';;')[0]
        self.assertIn('Disk mounting completed', star)
        self.assertIn('echo "磁盘挂载完成"', text.split("'en_US'")[0])   # zh_CN branch kept
        self.assertIn('msg "Copying the base file system..."', text)
        self.assertIn('msg "Copying /opt/kare"', text)
        self.assertIn('msg "Copied /opt/kare"', text)
        self.assertIn('msg "Copied /var/kare-shadow"', text)
        self.assertIn('echo "ghost镜像在磁盘跟目录"', text)
        self.assertIn('msg "Setting up user ${USERNAME}"', text)
        self.assertIn('msg "Skipping $i"', text)
        self.assertIn('#    	msg "更新 initramfs"', text)   # comments left alone
        self.assertEqual(self.script.stat().st_mode & 0o777, 0o755)
        ini = self.ini.read_text()
        self.assertIn('enable-swapfile=false; 使用 swapfile', ini)
        self.assertIn('EnableSwap = false', ini)
        self.assertIn('FileSystem="ext4;linux-swap"', ini)

    def test_apply_is_idempotent(self):
        ki.apply(self.root)
        first = self.script.read_text(), self.ini.read_text()
        ki.apply(self.root)
        self.assertEqual(first, (self.script.read_text(), self.ini.read_text()))

    def test_missing_swap_setting_is_reported(self):
        self.ini.unlink()
        self.assertIn('WARNING: no installer setting for swap found (EnableSwap / enable-swapfile)', ki.apply(self.root))
        self.assertTrue(any('no installer swap setting' in p for p in ki.audit(self.root)))

    def test_no_installer_is_fine(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(ki.audit(Path(d)), [])

    def test_refuses_live_root(self):
        with self.assertRaises(ValueError):
            ki.apply(Path('/'))


if __name__ == '__main__':
    unittest.main()
