#!/usr/bin/env python3
"""Apply or audit Kirin branding in an OFFLINE image root. Never runs on /.

* Menu names: in .desktop display keys (Name, GenericName, Comment, Keywords and
  their translations), "openKylin"/"Kylin" become "Kirin". Exec, Icon and other
  keys are untouched, so programs and their files keep working.
* OS name: NAME/PRETTY_NAME in os-release and DISTRIB_DESCRIPTION in lsb-release
  say Kirin Linux. ID, VERSION_ID and codenames stay openKylin's, because
  openKylin's updater and packages identify the system by them.
* GRUB_DISTRIBUTOR, Fastfetch config and logo, the kirin icon and the Plymouth
  theme files. Selecting the Plymouth theme and rebuilding the initramfs is
  done by the image builder inside the chroot.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
BRANDING = REPO / 'packaging/branding'
OS_NAME = 'Kirin Linux'
KIRIN_VERSION = '1.0'
DISPLAY_KEY = re.compile(r'^((?:Name|GenericName|Comment|Keywords|X-[A-Za-z-]*Name)(?:\[[^\]]+\])?)=(.*)$')
KYLIN = re.compile(r'(?<![A-Za-z])(?:open[Kk]ylin|OPENKYLIN|Kylin|KYLIN|kylin)(?![A-Za-z])')
DESKTOP_DIRS = ('usr/share/applications', 'etc/xdg/autostart', 'usr/share/desktop-directories')
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)   # pre-rendered in packaging/branding/icons


def image_root(root: Path) -> Path:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir() or root.resolve() == Path('/'):
        raise ValueError('requires an offline image root other than /')
    return root


def inside(root: Path, rel: str) -> Path:
    """rel under root; a symlinked final component is resolved, but only within root."""
    path = root
    parts = Path(rel).parts
    for i, part in enumerate(parts):
        path = path / part
        if path.is_symlink():
            if i < len(parts) - 1:
                raise ValueError(f'symlinked directory in image path: {path}')
            target = Path(os.readlink(path))
            resolved = (root / str(target).lstrip('/')) if target.is_absolute() else (path.parent / target)
            resolved = Path(os.path.normpath(resolved))
            if root not in resolved.parents:
                raise ValueError(f'{rel} links outside the image')
            return resolved
    return path


def load_names(path: Path = BRANDING / 'desktop-names.json') -> dict:
    if not path.is_file():
        return {}
    return {k: v for k, v in json.loads(path.read_text(encoding='utf-8')).items() if not k.startswith('_')}


def rename(text: str, names: dict) -> str:
    """Set Name= (and Name[ru]=) from an explicit override."""
    out, have_ru = [], False
    in_entry = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith('['):
            if in_entry and names.get('ru') and not have_ru:
                out.append(f'Name[ru]={names["ru"]}\n')
            in_entry = stripped == '[Desktop Entry]'
        elif in_entry and stripped.startswith('Name='):
            line = f'Name={names["en"]}\n'
        elif in_entry and stripped.startswith('Name[ru]=') and names.get('ru'):
            line, have_ru = f'Name[ru]={names["ru"]}\n', True
        out.append(line)
    if in_entry and names.get('ru') and not have_ru:
        out.append(f'Name[ru]={names["ru"]}\n')
    return ''.join(out)


def rebrand_desktop(text: str, names: dict | None = None) -> str:
    if names:
        text = rename(text, names)
    out = []
    for line in text.splitlines(keepends=True):
        m = DISPLAY_KEY.match(line.rstrip('\r\n'))
        if m and KYLIN.search(m.group(2)):
            ending = line[len(line.rstrip('\r\n')):]
            line = f'{m.group(1)}={KYLIN.sub("Kirin", m.group(2))}{ending}'
        out.append(line)
    return ''.join(out)


def desktop_changes(root: Path):
    overrides = load_names()
    for rel in DESKTOP_DIRS:
        folder = root / rel
        if not folder.is_dir() or folder.is_symlink():
            continue
        for p in sorted(folder.rglob('*.desktop')):
            if p.is_symlink() or not p.is_file():
                continue
            raw = p.read_text(encoding='utf-8', errors='surrogateescape')
            new = rebrand_desktop(raw, overrides.get(p.name))
            if new != raw:
                yield p, new


def set_keys(text: str, values: dict[str, str]) -> str:
    lines, seen = [], set()
    for line in text.splitlines():
        key = line.split('=', 1)[0] if '=' in line else None
        if key in values:
            lines.append(f'{key}="{values[key]}"')
            seen.add(key)
        else:
            lines.append(line)
    lines += [f'{k}="{v}"' for k, v in values.items() if k not in seen]
    return '\n'.join(lines) + '\n'


def os_release_values(text: str) -> dict[str, str]:
    version = re.search(r'^VERSION_ID="?([^"\n]*)"?', text, re.M)
    base = f'openKylin {version.group(1)}' if version else 'openKylin'
    return {'NAME': OS_NAME, 'PRETTY_NAME': f'{OS_NAME} {KIRIN_VERSION} ({base} base)',
            'VARIANT': OS_NAME, 'VARIANT_ID': 'kirin',
            'HOME_URL': 'https://github.com/factionparadox/Kirin'}


def files_to_install(root: Path):
    for size in ICON_SIZES:
        yield (root / f'usr/share/icons/hicolor/{size}x{size}/apps/kirin.png',
               BRANDING / f'icons/{size}x{size}/kirin.png')
    yield root / 'usr/share/kirin/branding/fastfetch-logo.txt', BRANDING / 'fastfetch-logo.txt'
    yield root / 'etc/xdg/fastfetch/config.jsonc', BRANDING / 'fastfetch.jsonc'
    yield root / 'usr/share/kirin/branding/kirin-logo.png', BRANDING / 'kirin-logo.png'
    yield root / 'usr/share/kirin/branding/kirin-splash.png', BRANDING / 'kirin-splash.png'
    yield root / 'usr/share/pixmaps/kirin.png', BRANDING / 'kirin-logo.png'
    theme = root / 'usr/share/plymouth/themes/kirin'
    yield theme / 'kirin.plymouth', BRANDING / 'plymouth/kirin.plymouth'
    yield theme / 'kirin.script', BRANDING / 'plymouth/kirin.script'
    yield theme / 'splash.png', BRANDING / 'kirin-splash.png'


def apply(root: Path) -> list[str]:
    done = []
    for p, new in desktop_changes(root):
        p.write_text(new, encoding='utf-8', errors='surrogateescape')
        done.append(f'renamed: {p.relative_to(root)}')
    for rel in ('usr/lib/os-release', 'etc/os-release'):
        p = inside(root, rel)
        if p.is_file():
            text = p.read_text(encoding='utf-8')
            p.write_text(set_keys(text, os_release_values(text)), encoding='utf-8')
            done.append(f'os name: {rel}')
    lsb = inside(root, 'etc/lsb-release')
    if lsb.is_file():
        text = lsb.read_text(encoding='utf-8')
        version = re.search(r'^DISTRIB_RELEASE="?([^"\n]*)"?', text, re.M)
        base = f'openKylin {version.group(1)}' if version else 'openKylin'
        lsb.write_text(set_keys(text, {'DISTRIB_DESCRIPTION': f'{OS_NAME} {KIRIN_VERSION} ({base} base)'}), encoding='utf-8')
    grub = inside(root, 'etc/default/grub.d/90-kirin.cfg')
    grub.parent.mkdir(parents=True, exist_ok=True)
    grub.write_text(f'# Kirin branding for boot menu entries\nGRUB_DISTRIBUTOR="{OS_NAME}"\n', encoding='utf-8')
    for dest, src in files_to_install(root):
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    done.append('installed logo, icons, Fastfetch config and Plymouth theme files')
    return done


def audit(root: Path) -> list[str]:
    problems = [f'Kylin in menu name: {p.relative_to(root)}' for p, _ in desktop_changes(root)]
    osr = inside(root, 'usr/lib/os-release')
    if not osr.is_file():
        osr = inside(root, 'etc/os-release')
    if not osr.is_file() or f'NAME="{OS_NAME}"' not in osr.read_text(encoding='utf-8'):
        problems.append('os-release NAME is not Kirin Linux')
    for dest, _ in files_to_install(root):
        if not dest.is_file():
            problems.append(f'missing branding file: {dest.relative_to(root)}')
    if not (root / 'etc/default/grub.d/90-kirin.cfg').is_file():
        problems.append('GRUB_DISTRIBUTOR not set')
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Apply or audit Kirin branding in an offline image')
    ap.add_argument('--root', type=Path, required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--audit', action='store_true')
    args = ap.parse_args(argv)
    try:
        root = image_root(args.root)
        if args.apply:
            done = apply(root)
            renamed = sum(1 for d in done if d.startswith('renamed'))
            print(f'Kirin branding applied: {renamed} menu entries renamed')
            return 0
        problems = audit(root)
    except (OSError, ValueError) as exc:
        print(f'REBRAND FAILED: {exc}', file=sys.stderr)
        return 2
    for p in problems:
        print('FAIL:', p)
    if problems:
        return 1
    print('Kirin branding check passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
