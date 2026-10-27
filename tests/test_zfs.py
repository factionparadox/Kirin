"""Kirin ZFS tools: the installer (dry run), kirin-be and the APT snapshot hook, against stub commands."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / 'scripts/kirin-zfs-install'
BE = ROOT / 'scripts/kirin-be'
HOOK = ROOT / 'scripts/zfs-apt-snapshot'

# A fake zfs/zpool that keeps snapshots and datasets in a state directory and logs every call.
FAKE_ZFS = r'''#!/usr/bin/env python3
import json, os, sys, time
state = os.environ['ZSTATE']; log = open(os.path.join(state, 'calls'), 'a')
log.write(os.path.basename(sys.argv[0]) + ' ' + ' '.join(sys.argv[1:]) + '\n')
db_path = os.path.join(state, 'db.json')
db = json.load(open(db_path)) if os.path.exists(db_path) else {'ds': ['zroot/ROOT', 'zroot/ROOT/kirin'], 'snaps': [], 'bootfs': 'zroot/ROOT/kirin'}
a = sys.argv[1:]; tool = os.path.basename(sys.argv[0])
def save(): json.dump(db, open(db_path, 'w'))
if tool == 'zpool':
    if a[:3] == ['get', '-Ho', 'value']: print(db['bootfs'])
    elif a[0] == 'set' and a[1].startswith('bootfs='): db['bootfs'] = a[1].split('=', 1)[1]; save()
    sys.exit(0)
if a[0] == 'list':
    target = a[-1]
    if '-t' in a:
        for n, t in db['snaps']:
            if n.startswith(target + '@'):
                cols = a[a.index('-o') + 1].split(',')
                print('\t'.join({'name': n, 'creation': str(t), 'used': '1K'}[c] for c in cols))
        sys.exit(0)
    if '-d' in a:
        for d in db['ds']: print(f'{d}\t1G\tnow')
        sys.exit(0)
    sys.exit(0 if target in db['ds'] or any(n == target for n, _ in db['snaps']) else 1)
if a[0] == 'snapshot': db['snaps'].append([a[1], int(os.environ.get('NOW', time.time()))]); save()
elif a[0] == 'clone': db['ds'].append(a[-1]); save()
elif a[0] == 'destroy':
    db['snaps'] = [s for s in db['snaps'] if s[0] != a[1]]; db['ds'] = [d for d in db['ds'] if d != a[1]]; save()
'''


class Stubs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.bin = self.dir / 'bin'; self.bin.mkdir()
        self.state = self.dir / 'state'; self.state.mkdir()
        for tool in ('zfs', 'zpool'):
            (self.bin / tool).write_text(FAKE_ZFS); (self.bin / tool).chmod(0o755)
        self.stub('findmnt', 'case "$*" in *FSTYPE*) echo "${FS:-zfs}" ;; *SOURCE*) echo zroot/ROOT/kirin ;; esac')
        self.stub('id', 'echo 0')

    def stub(self, name, body):
        p = self.bin / name
        p.write_text('#!/bin/sh\n' + body + '\n'); p.chmod(0o755)

    def run_tool(self, tool, *args, env=None, input=''):
        e = {**os.environ, 'PATH': f'{self.bin}:{os.environ["PATH"]}', 'ZSTATE': str(self.state), **(env or {})}
        return subprocess.run([str(tool), *args], capture_output=True, text=True, env=e, input=input)

    def calls(self):
        p = self.state / 'calls'
        return p.read_text() if p.exists() else ''


class TestKirinBe(Stubs):
    def test_list_marks_running_and_default(self):
        out = self.run_tool(BE, 'list').stdout
        self.assertRegex(out, r'kirin .*\[running default\]')

    def test_create_clones_with_noauto(self):
        r = self.run_tool(BE, 'create', 'test')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(self.calls(), r'zfs clone -o mountpoint=/ -o canmount=noauto zroot/ROOT/kirin@be-test-\S+ zroot/ROOT/test')

    def test_rollback_makes_new_default_and_keeps_current(self):
        self.run_tool(BE, 'snapshot', 'before')
        r = self.run_tool(BE, 'rollback', 'before')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('zfs clone -o mountpoint=/ -o canmount=noauto zroot/ROOT/kirin@before zroot/ROOT/rollback-', self.calls())
        self.assertRegex(self.calls(), r'zpool set bootfs=zroot/ROOT/rollback-\d')
        self.assertNotIn('zfs rollback', self.calls())
        self.assertNotIn('destroy', self.calls())

    def test_destroy_refuses_running_and_default(self):
        self.assertNotEqual(self.run_tool(BE, 'destroy', 'kirin').returncode, 0)
        self.run_tool(BE, 'create', 'other')
        self.run_tool(BE, 'activate', 'other')
        self.assertIn('running system', self.run_tool(BE, 'destroy', 'kirin').stderr)
        self.run_tool(BE, 'activate', 'kirin')
        self.assertEqual(self.run_tool(BE, 'destroy', 'other').returncode, 0)

    def test_bad_names_and_non_root(self):
        self.assertIn('invalid name', self.run_tool(BE, 'create', '../x').stderr)
        self.stub('id', 'echo 1000')
        self.assertIn('sudo kirin-be', self.run_tool(BE, 'snapshot').stderr)

    def test_refuses_without_zfs_root(self):
        self.assertIn('not on ZFS', self.run_tool(BE, 'list', env={'FS': 'ext4'}).stderr)


class TestAptHook(Stubs):
    def test_snapshot_once_per_run_and_prune(self):
        self.stub('date', 'case "$1" in +%s) echo "$NOW" ;; *) echo "t$NOW" ;; esac')
        for n in range(25):
            self.run_tool(HOOK, env={'NOW': str(1000 + n * 600)})
        db = (self.state / 'db.json').read_text()
        self.assertEqual(db.count('@apt-'), 20)
        r = self.run_tool(HOOK, env={'NOW': str(1000 + 24 * 600 + 10)})      # same APT run: no new snapshot
        self.assertEqual(r.returncode, 0)
        self.assertEqual((self.state / 'db.json').read_text().count('@apt-'), 20)
        self.assertIn('zroot/ROOT/kirin@apt-t15400', (self.state / 'db.json').read_text())   # newest kept
        self.assertNotIn('zroot/ROOT/kirin@apt-t1000"', (self.state / 'db.json').read_text())  # oldest pruned

    def test_nothing_on_other_filesystems(self):
        r = self.run_tool(HOOK, env={'FS': 'ext4'})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.calls(), '')


class TestInstallerDryRun(Stubs):
    def install(self, *extra):
        pw = self.dir / 'pw'; pw.write_text('hunter2\n')
        enc = self.dir / 'enc'; enc.write_text('correct horse battery\n')
        args = ['--dry-run', '--disk', '/dev/nvme0n1', '--username', 'stephen', '--fullname', 'Stephen',
                '--password-file', str(pw), '--yes', '--source', '/cdrom/casper/filesystem.squashfs', *extra]
        if '--encrypt' in extra:
            args.remove('--encrypt'); args += ['--encrypt-passphrase-file', str(enc)]
        return self.run_tool(INSTALL, *args)

    def test_plain_install_plan(self):
        r = self.install('--no-encrypt')
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        out = r.stdout
        for line in ('+ sgdisk --zap-all /dev/nvme0n1',
                     '+ sgdisk -n 1:1m:+1g -t 1:ef00 -c 1:EFI /dev/nvme0n1',
                     '+ mkfs.vfat -F 32 -n KIRIN-EFI /dev/nvme0n1p1',
                     '-o compatibility=openzfs-2.3-linux', '-m none zroot /dev/nvme0n1p2',
                     '+ zfs create -o mountpoint=/ -o canmount=noauto zroot/ROOT/kirin',
                     '+ zfs create -o mountpoint=/home zroot/home',
                     '+ zpool set bootfs=zroot/ROOT/kirin zroot',
                     '+ unsquashfs -f -d /mnt/kirin-target /cdrom/casper/filesystem.squashfs',
                     "(empty /mnt/kirin-target/sysroot: openKylin's OSTree repository)",
                     'useradd -m -s /bin/bash -c Stephen',
                     '+ cp /usr/share/kirin/zfsbootmenu/VMLINUZ.EFI /mnt/kirin-target/boot/efi/EFI/ZBM/VMLINUZ.EFI',
                     "efibootmgr -c -d /dev/nvme0n1 -p 1 -L Kirin (ZFSBootMenu) -l \\EFI\\ZBM\\VMLINUZ.EFI",
                     '+ zfs snapshot zroot/ROOT/kirin@installed', '+ zpool export zroot'):
            self.assertIn(line, out)
        self.assertNotIn('encryption=', out)
        self.assertNotIn('hunter2', out)
        self.assertLess(out.index('zap-all'), out.index('zpool create'))
        self.assertLess(out.index('unsquashfs'), out.index('efibootmgr'))

    def test_encrypted_install_plan(self):
        r = self.install('--encrypt')
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn('-O encryption=aes-256-gcm -O keylocation=file:///etc/zfs/zroot.key -O keyformat=passphrase', r.stdout)
        self.assertIn('+ zfs set org.zfsbootmenu:keysource=zroot/ROOT/kirin zroot', r.stdout)
        self.assertIn('+ zfs load-key zroot', r.stdout)
        self.assertNotIn('correct horse', r.stdout + r.stderr)

    def test_short_passphrase_and_bad_user_refused(self):
        enc = self.dir / 'short'; enc.write_text('abc\n')
        pw = self.dir / 'pw'; pw.write_text('x\n')
        r = self.run_tool(INSTALL, '--dry-run', '--disk', '/dev/sda', '--username', 'stephen', '--password-file', str(pw),
                          '--encrypt-passphrase-file', str(enc), '--yes')
        self.assertIn('at least 8 characters', r.stderr)
        r = self.run_tool(INSTALL, '--dry-run', '--disk', '/dev/sda', '--username', 'Root!', '--password-file', str(pw),
                          '--no-encrypt', '--yes', input='')
        self.assertNotEqual(r.returncode, 0)

    def test_confirmation_must_match_disk(self):
        pw = self.dir / 'pw'; pw.write_text('x\n')
        r = self.run_tool(INSTALL, '--dry-run', '--disk', '/dev/sda', '--username', 'stephen', '--password-file', str(pw),
                          '--no-encrypt', input='sdb\n')
        self.assertIn('not confirmed; nothing was changed', r.stderr)
        self.assertNotIn('zap-all', r.stdout)

    def test_partition_names(self):
        r = self.run_tool('bash', '-c', f'source <(sed -n "/^part()/p" {INSTALL}); part /dev/sda 2; part /dev/nvme0n1 1; part /dev/mmcblk0 1')
        self.assertEqual(r.stdout.split(), ['/dev/sda2', '/dev/nvme0n1p1', '/dev/mmcblk0p1'])


if __name__ == '__main__':
    unittest.main()
