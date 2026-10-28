"""scripts/kirin-installer.py: no swap, English installer messages."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('kinst', Path(__file__).resolve().parents[1] / 'scripts/kirin-installer.py')
ki = importlib.util.module_from_spec(spec); spec.loader.exec_module(ki)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rccfixture import fake_installer_programs  # noqa: E402

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
CFG = '''[config]
automatic-installation=1
# 使用 swapfile 替代swap分区，false 为不使用 swapfile，990/9A0 使用swapfile
enable-swapfile=false
[custompartition]
custom-partitions="efi;boot;root;backup;data;swap;"
custom-swap="fs=linux-swap;mount=[swap];size=default;"
[setting]
EnableSwap=false
'''
SIZES = '''ram=$(cat < /proc/meminfo  | grep ^MemTotal: | awk '{print $2}')

### backup
backup_size=0
systemd-detect-virt || do_backup_size

### swap
swap=$(( ram * 12 / 1024 / 10 ))
if [ $swap -gt 64000 ]; then
    swap=64000
fi
'''
UTILS = '''#虚拟机去掉备份还原分区
readonly virtual_machine=$(get_value virtual-machine)
'''
SWAPFILE = '''#!/bin/bash

set -e

is_automatic=$(get_value automatic-installation)
'''
GENFSTAB = '''  while read -r device type _ _ prio; do
    # skip files marked deleted by the kernel
    [[ $device = *'\\040(deleted)' ]] && continue

    if [[ $type = file ]]; then
'''


class TestInstaller(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        s = self.root / ki.SCRIPTS / 'prepare'
        s.mkdir(parents=True)
        self.script = s / '16copy-basic-filesystem'
        self.script.write_text(SCRIPT); self.script.chmod(0o755)
        self.files = {}
        for rel, text in [(ki.CFGS[0], CFG), (ki.CFGS[1], CFG), (f'{ki.INSTALLER}/data/systemdatasize.sh', SIZES),
                          (f'{ki.SCRIPTS}/autopart.sh', SIZES), (f'{ki.SCRIPTS}/autopart-efi.sh', SIZES),
                          (f'{ki.SCRIPTS}/prepare/18setup-swapfile', SWAPFILE), (f'{ki.SCRIPTS}/utils', UTILS), (f'{ki.SCRIPTS}/in_chroot/genfstab', GENFSTAB)]:
            f = self.root / rel; f.parent.mkdir(parents=True, exist_ok=True); f.write_text(text)
            self.files[rel] = f
        fake_installer_programs(self.root, ki.branding_spec(), ki.BRANDING)

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
        for c in ki.CFGS:
            cfg = self.files[c].read_text()
            self.assertIn('\nenable-swapfile=true\n', cfg)
            self.assertIn('custom-partitions="efi;boot;root;data;"', cfg)
        for rel in ('data/systemdatasize.sh', 'scripts/autopart.sh', 'scripts/autopart-efi.sh'):
            sizes = self.files[f'{ki.INSTALLER}/{rel}'].read_text()
            self.assertIn('\nswap=0   # Kirin:', sizes)
            self.assertNotIn('ram * 12', sizes)
        self.assertIn('set -e\nreturn 0   # Kirin: no swap file\n\nis_automatic',
                      self.files[f'{ki.SCRIPTS}/prepare/18setup-swapfile'].read_text())
        self.assertIn('\nreadonly virtual_machine=true   # Kirin', self.files[f'{ki.SCRIPTS}/utils'].read_text())
        sizes = self.files[f'{ki.INSTALLER}/data/systemdatasize.sh'].read_text()
        self.assertIn('\n: # Kirin: no backup partition\n', sizes)
        self.assertNotIn('do_backup_size', sizes)
        fstab = self.files[f'{ki.SCRIPTS}/in_chroot/genfstab'].read_text()
        self.assertIn("continue\n    [[ $device = /dev/zram* ]] && continue   # Kirin", fstab)

    def test_branding_in_the_programs(self):
        q, spec = ki.qtres(), ki.branding_spec()
        self.assertTrue(any('still openKylin' in p for p in ki.audit(self.root)))
        ki.apply(self.root)
        for rel, res in spec['resources'].items():
            buf = (self.root / rel).read_bytes()
            found = {r.path: r for r in q.resources(buf)}
            for rpath, src in res.items():
                want = (q.content(buf, found[src[9:]]) if src.startswith('resource:')
                        else (ki.BRANDING / src).read_bytes())
                self.assertEqual(q.content(buf, found[rpath]), want, rpath)
        prog = (self.root / 'usr/bin/kylin-os-installer').read_bytes()
        self.assertNotIn(b'KylinOS', prog)
        self.assertIn(b'Private, local AI @ ', prog)
        self.assertIn(b'unrelated text\0', prog)
        self.assertEqual((self.root / 'usr/bin/kylin-os-installer').stat().st_mode & 0o777, 0o755)

    def test_captions_fit_and_licence_is_kirins(self):
        spec = ki.branding_spec()
        for old, new in spec['strings']['usr/bin/kylin-os-installer']:
            self.assertLessEqual(len(new.encode()), len(old.encode()), new)
            self.assertEqual(' @ ' in old, ' @ ' in new, new)
        self.assertIn('Kirin Linux', (ki.BRANDING / 'licence.txt').read_text())

    def test_apply_is_idempotent(self):
        ki.apply(self.root)
        progs = [self.root / r for r in ki.branding_spec()['resources']]
        first = [f.read_text() for f in [self.script, *self.files.values()]] + [p.read_bytes() for p in progs]
        notes = ki.apply(self.root)
        self.assertFalse([n for n in notes if n.startswith(('partition layout', 'branding', 'WARNING'))], notes)
        self.assertEqual(first, [f.read_text() for f in [self.script, *self.files.values()]] + [p.read_bytes() for p in progs])

    def test_changed_upstream_is_reported(self):
        f = self.files[f'{ki.SCRIPTS}/autopart-efi.sh']
        f.write_text(SIZES.replace('ram * 12', 'ram * 15'))
        self.assertTrue(any('autopart-efi.sh has changed upstream' in n for n in ki.apply(self.root)))
        self.assertTrue(any('autopart-efi.sh: changed upstream' in p for p in ki.audit(self.root)))

    def test_no_installer_is_fine(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(ki.audit(Path(d)), [])

    def test_refuses_live_root(self):
        with self.assertRaises(ValueError):
            ki.apply(Path('/'))


if __name__ == '__main__':
    unittest.main()
