#!/usr/bin/env python3
"""Apply or audit Kirin's changes to openKylin's graphical installer in an OFFLINE
image root. Never runs on /.

* No swap: Kirin swaps to compressed RAM (zram), and hibernation is not supported,
  so the installer must not make a swap partition or swap file. Every installer
  settings file that has them gets EnableSwap=false and enable-swapfile=false.
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
SWAP_KEYS = {'enableswap': 'EnableSwap', 'enable-swapfile': 'enable-swapfile'}
SETTINGS_SUFFIXES = ('.ini', '.cfg', '.conf')

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
}
# Patterns, for paths: 开始处理/opt/kare -> Copying /opt/kare.
PATTERNS = [
    (re.compile(r'^开始处理(\S+)$'), r'Copying \1'),
    (re.compile(r'^处理(\S+)完成$'), r'Copied \1'),
    (re.compile(r'^处理(/\S+)$'), r'Copied \1'),
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


def installer_files(root: Path) -> list[Path]:
    """Files owned by the installer packages, plus anything under its share dir."""
    files: set[Path] = set()
    info = root / 'var/lib/dpkg/info'
    for lst in info.glob('*os-installer*.list') if info.is_dir() else []:
        for rel in lst.read_text(errors='replace').splitlines():
            p = root / rel.lstrip('/')
            if rel and p.is_file() and not p.is_symlink():
                files.add(p)
    share = root / INSTALLER
    if share.is_dir():
        files.update(p for p in share.rglob('*') if p.is_file() and not p.is_symlink())
    etc = root / 'etc'
    if etc.is_dir():
        for p in etc.glob('*installer*'):
            if p.is_file():
                files.add(p)
            elif p.is_dir():
                files.update(q for q in p.rglob('*') if q.is_file() and not q.is_symlink())
    return sorted(files)


def set_swap_off(text: str) -> tuple[str, bool]:
    found = False
    def repl(m):
        nonlocal found
        found = True
        return f'{m.group(1)}{m.group(2)}false'
    # Keep openKylin's spelling, spacing and any trailing comment out of the value.
    pattern = re.compile(r'^(\s*)((?i:EnableSwap|enable-swapfile)\s*=\s*)[^;#\n]*?(?=\s*(?:[;#；].*)?$)', re.M)
    return pattern.sub(repl, text), found


def swap_settings(root: Path) -> list[tuple[Path, str]]:
    out = []
    for p in installer_files(root):
        if p.suffix not in SETTINGS_SUFFIXES and 'setting' not in p.name.lower():
            continue
        try:
            text = p.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        if re.search(r'^\s*(?i:EnableSwap|enable-swapfile)\s*=', text, re.M):
            out.append((p, text))
    return out


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
    settings = swap_settings(root)
    for p, text in settings:
        new, _ = set_swap_off(text)
        if new != text:
            write(p, new)
            notes.append(f'swap off: /{p.relative_to(root)}')
    if not settings:
        notes.append('WARNING: no installer setting for swap found (EnableSwap / enable-swapfile)')
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
    settings = swap_settings(root)
    if not settings:
        problems.append('no installer swap setting found to turn off (EnableSwap / enable-swapfile)')
    for p, text in settings:
        for m in re.finditer(r'^\s*((?i:EnableSwap|enable-swapfile))\s*=\s*([^;#；\n]*)', text, re.M):
            if m.group(2).strip().lower() != 'false':
                problems.append(f'/{p.relative_to(root)}: {m.group(1)}={m.group(2).strip()} (want false)')
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
