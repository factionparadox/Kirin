#!/usr/bin/env python3
"""Apply or audit Kirin's changes to openKylin's graphical installer in an OFFLINE
image root. Never runs on /.

* No swap partition or swap file: Kirin swaps to compressed RAM (zram), and
  hibernation is not supported. openKylin sizes a swap partition at 1.2 x RAM (up
  to 64 GB). Its own "swap file" mode is the one that makes no swap partition, so
  Kirin turns that on (enable-swapfile=true), makes the size 0 in the scripts that
  compute it (so the root partition is not padded by it either), stops the swap
  file being created, and keeps the live session's zram out of the new fstab.
* English progress messages: the installer's scripts pick a message with
  `case ${LANGUAGES}`, and anything not listed (Kirin's en_GB) falls through to
  Chinese. The fallback branch now says what the en_US branch says. Hard-coded
  Chinese `msg` lines (the installer's log) are translated.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys

INSTALLER = 'usr/share/kylin-os-installer'
SCRIPTS = f'{INSTALLER}/scripts'
CJK = re.compile(r'[一-鿿]')
# Swap edits: (file, pattern, replacement, marker present once applied).
SWAP_RAM = (r'^(\s*)swap=\$\(\( ram \* 12 / 1024 / 10 \)\)$',
            r'\1swap=0   # Kirin: no swap partition or file; zram swaps to compressed RAM',
            'swap=0   # Kirin:')
CFGS = (f'{INSTALLER}/ky-installer.cfg', 'var/log/installer/ky-installer.cfg')
SWAP_EDITS = [
    *[(c, r'^enable-swapfile=\S*$', 'enable-swapfile=true', '\nenable-swapfile=true\n') for c in CFGS],
    *[(c, r'^(custom-partitions="[^"\n]*?)swap;', r'\1', None) for c in CFGS],
    *[(f'{INSTALLER}/{f}', *SWAP_RAM) for f in ('data/systemdatasize.sh', 'scripts/autopart.sh', 'scripts/autopart-efi.sh')],
    (f'{SCRIPTS}/prepare/18setup-swapfile', r'\A(#!/bin/bash\n\nset -e\n)(?!return 0)',
     r'\1return 0   # Kirin: no swap file\n', '\nreturn 0   # Kirin: no swap file\n'),
    (f'{SCRIPTS}/in_chroot/genfstab', r"^(\s*)(\[\[ \$device = \*'\\040\(deleted\)' \]\] && continue)$(?!\n\s*\[\[ \$device = /dev/zram)",
     r'\1\2\n\1[[ $device = /dev/zram* ]] && continue   # Kirin: zram-generator sets up zram', '/dev/zram* ]] && continue   # Kirin'),
]

# Hard-coded log messages, exact.
MESSAGES = {
    '正在拷贝基础文件系统...': 'Copying the base file system...',
    '正在处理squashfs...': 'Copying the squashfs...',
    'squashfs处理完成': 'Squashfs copied',
    '文件系统拷贝完成': 'File system copied',
    '开始处理kare': 'Setting up KARE applications',
    '挂载squashfs': 'Mounting the squashfs',
    'kare处理完成': 'KARE applications set up',
    '正在配置系统...': 'Configuring the system...',
    '磁盘挂载完成': 'Disks mounted',
    '运行remove deb 脚本结束': 'Package removal script finished',
    '正在拷贝安装日志...': 'Copying the installation logs...',
    '正在进行系统备份...': 'Backing up the system...',
    '系统备份完成': 'System backup complete',
    'k.sh 运行结束': 'k.sh finished',
    '更新 initramfs': 'Updating the initramfs',
    '安装光盘源列表包': "Installing the disc's package source list",
    '设置备份还原分区完成': 'Backup and restore partition set up',
    '正在卸载文件系统...': 'Unmounting file systems...',
    '卸载完成': 'Unmounted',
}
# Patterns, for paths: 开始处理/opt/kare -> Copying /opt/kare.
PATTERNS = [
    (re.compile(r'^开始处理(\S+)$'), r'Copying \1'),
    (re.compile(r'^处理(\S+)完成$'), r'Copied \1'),
    (re.compile(r'^处理(/\S+)$'), r'Copied \1'),
    (re.compile(r'^设置用户 (\S+)$'), r'Setting up user \1'),
    (re.compile(r'^设置时区为 (\S+)$'), r'Setting the time zone to \1'),
    (re.compile(r'^设置语言为 (\S+)$'), r'Setting the language to \1'),
    (re.compile(r'^移除 (\S+)$'), r'Removing \1'),
    (re.compile(r'^跳过 (\S+)$'), r'Skipping \1'),
]
MSG_LINE = re.compile(r'^(\s*msg\s+)"([^"]*)"(.*)$')


def image_root(root: Path) -> Path:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir() or root.resolve() == Path('/'):
        raise ValueError('requires an offline image root other than /')
    return root


def translate(text: str) -> str | None:
    if text in MESSAGES:
        return MESSAGES[text]
    for pattern, repl in PATTERNS:
        if pattern.match(text):
            return pattern.sub(repl, text)
    return None


def fix_case_defaults(text: str) -> str:
    """In each `case ${LANGUAGES}` block, make `*)` say what `'en_US')` says."""
    lines = text.split('\n')
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if re.match(r'\s*case\s+"?\$\{?LANGUAGES\}?"?\s+in\b', line):
            end = i
            while end < len(lines) and not re.match(r'\s*esac\b', lines[end]):
                end += 1
            block = lines[i:end + 1]
            en = branch(block, r"""['"]?en_US['"]?\)""")
            star = branch(block, r'\*\)')
            if en and star and CJK.search('\n'.join(block[star[0]:star[1]])):
                new = block[:star[0]] + block[en[0]:en[1]] + block[star[1]:]
                out.extend(new)
            else:
                out.extend(block)
            i = end + 1
            continue
        out.append(line)
        i += 1
    return '\n'.join(out)


def branch(block: list[str], label: str):
    """(first, after) body line indexes of the branch whose label matches, up to its ;;."""
    for n, line in enumerate(block):
        if re.match(rf'\s*{label}\s*$', line):
            end = n + 1
            while end < len(block) and not re.match(r'\s*;;', block[end]):
                end += 1
            return n + 1, end
    return None


def fix_messages(text: str) -> tuple[str, list[str]]:
    left = []
    lines = text.split('\n')
    for n, line in enumerate(lines):
        m = MSG_LINE.match(line)
        if not m or not CJK.search(m.group(2)):
            continue
        english = translate(m.group(2))
        if english is None:
            left.append(m.group(2))
        else:
            lines[n] = f'{m.group(1)}"{english}"{m.group(3)}'
    return '\n'.join(lines), left


def swap_edit(text: str, pattern: str, repl: str, marker: str | None) -> tuple[str, str]:
    """Returns (new text, state): state is 'applied', 'done' or 'missing'."""
    new = re.sub(pattern, repl, text, count=1, flags=re.M)
    if new != text:
        return new, 'applied'
    if marker is None or marker in text:
        return text, 'done'
    return text, 'missing'


def scripts(root: Path) -> list[Path]:
    d = root / SCRIPTS
    return sorted(p for p in d.rglob('*') if p.is_file() and not p.is_symlink()) if d.is_dir() else []


def read_script(p: Path) -> str | None:
    try:
        return p.read_text()
    except (UnicodeDecodeError, OSError):
        return None


def write(p: Path, text: str) -> None:
    mode = p.stat().st_mode
    p.write_text(text)
    os.chmod(p, mode)


def apply(root: Path) -> list[str]:
    root = image_root(root)
    notes = []
    if not (root / INSTALLER).is_dir():
        return ["openKylin's graphical installer is not in this image; nothing to change"]
    for rel, pattern, repl, marker in SWAP_EDITS:
        p = root / rel
        if not p.is_file():
            notes.append(f'WARNING: /{rel} missing; swap not turned off there'); continue
        new, state = swap_edit(p.read_text(), pattern, repl, marker)
        if state == 'applied':
            write(p, new); notes.append(f'no swap: /{rel}')
        elif state == 'missing':
            notes.append(f'WARNING: /{rel} has changed upstream; swap not turned off there')
    changed, left = 0, []
    for p in scripts(root):
        text = read_script(p)
        if text is None:
            continue
        new = fix_case_defaults(text)
        new, rest = fix_messages(new)
        left += rest
        if new != text:
            write(p, new)
            changed += 1
    notes.append(f'installer messages in English: {changed} script(s) changed')
    for text in sorted(set(left)):
        notes.append(f'untranslated installer message: {text}')
    return notes


def audit(root: Path) -> list[str]:
    root = image_root(root)
    if not (root / INSTALLER).is_dir():
        return []
    problems = []
    for rel, pattern, repl, marker in SWAP_EDITS:
        p = root / rel
        if not p.is_file():
            problems.append(f'/{rel} missing'); continue
        state = swap_edit(p.read_text(), pattern, repl, marker)[1]
        if state != 'done':
            problems.append(f'/{rel}: swap still on' if state == 'applied' else f'/{rel}: changed upstream, swap edit does not fit')
    for p in scripts(root):
        text = read_script(p)
        if text is None:
            continue
        if fix_case_defaults(text) != text:
            problems.append(f'/{p.relative_to(root)}: a language fallback is still Chinese')
        if fix_messages(text)[0] != text:
            problems.append(f'/{p.relative_to(root)}: a translatable Chinese message is left')
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Apply or audit Kirin's installer changes in an offline image")
    ap.add_argument('--root', type=Path, required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--audit', action='store_true')
    args = ap.parse_args(argv)
    try:
        if args.apply:
            for note in apply(args.root):
                print(note)
            return 0
        problems = audit(args.root)
    except (OSError, ValueError) as exc:
        print(f'INSTALLER FAILED: {exc}', file=sys.stderr)
        return 2
    for p in problems:
        print('FAIL:', p)
    if problems:
        return 1
    print('installer check passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
