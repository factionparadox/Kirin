#!/usr/bin/env python3
"""Apply or audit Kirin's system defaults in an OFFLINE image root. Never runs on /.

* Identity: /etc/kirin-release; hostname `kirin`; the live session's user and
  host are `kirin` (casper.conf).
* Fastfetch when an interactive terminal opens (off: ~/.config/kirin/no-fastfetch,
  or untick it in Welcome to Kirin).
* Default apps: documents open in LibreOffice and audio/video in VLC instead of
  WPS Office and openKylin's players, in both UKUI's and the XDG mimeapps lists.
  Only mappings whose target app is installed are changed.
* Taskbar pins for new users (UKUI task manager quickLaunchers), skipping any
  app that is not installed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

KIRIN_VERSION = '1.0'
HOSTNAME = 'kirin'
APP_DIRS = ('usr/share/applications', 'var/lib/flatpak/exports/share/applications')
MIMEAPPS = ('usr/share/applications/ukui-mimeapps.list', 'usr/share/applications/mimeapps.list')
PDF_VIEWERS = ('atril.desktop', 'org.gnome.Papers.desktop', 'org.gnome.Evince.desktop', 'evince.desktop',
               'okularApplication_pdf.desktop', 'libreoffice-draw.desktop')
REPLACE = {
    'wps-office-wps.desktop': 'libreoffice-writer.desktop',
    'wps-office-et.desktop': 'libreoffice-calc.desktop',
    'wps-office-wpp.desktop': 'libreoffice-impress.desktop',
    'kylin-video.desktop': 'vlc.desktop',
    'kylin-music.desktop': 'vlc.desktop',
}
EXTRA_DEFAULTS = {   # types openKylin leaves unset or sends elsewhere
    'application/vnd.oasis.opendocument.text': 'libreoffice-writer.desktop',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'libreoffice-writer.desktop',
    'application/vnd.oasis.opendocument.spreadsheet': 'libreoffice-calc.desktop',
    'application/vnd.oasis.opendocument.presentation': 'libreoffice-impress.desktop',
    'audio/flac': 'vlc.desktop', 'audio/ogg': 'vlc.desktop', 'audio/mp4': 'vlc.desktop',
    'video/x-ms-wmv': 'vlc.desktop', 'video/ogg': 'vlc.desktop',
}
PINS = ('peony.desktop', 'mate-terminal.desktop', 'firefox.desktop', 'com.jeffser.Alpaca.desktop',
        'libreoffice-startcenter.desktop', 'vlc.desktop', 'kirin-learn.desktop', 'ukui-control-center.desktop')
PINS_FILE = 'etc/skel/.config/org.ukui/_ukui-config-global/org.ukui.panel.taskManager.json'
BASHRC_BEGIN = '# >>> Kirin: Fastfetch in new terminals'
BASHRC_BLOCK = f'''{BASHRC_BEGIN} (turn off: mkdir -p ~/.config/kirin && touch ~/.config/kirin/no-fastfetch)
if [ -n "$PS1" ] && [ -z "$KIRIN_FASTFETCH_SHOWN" ] && [ ! -e "$HOME/.config/kirin/no-fastfetch" ] \\
   && command -v fastfetch >/dev/null 2>&1; then
    export KIRIN_FASTFETCH_SHOWN=1
    fastfetch
fi
# <<< Kirin
'''


def image_root(root: Path) -> Path:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir() or root.resolve() == Path('/'):
        raise ValueError('requires an offline image root other than /')
    return root


def installed(root: Path, desktop: str) -> Path | None:
    return next((root / d / desktop for d in APP_DIRS if (root / d / desktop).is_file()), None)


def mapping(root: Path) -> dict[str, str]:
    m = {old: new for old, new in REPLACE.items() if installed(root, new)}
    pdf = next((v for v in PDF_VIEWERS if installed(root, v)), None)
    if pdf:
        m['wps-office-pdf.desktop'] = pdf
    return m


def rewrite_mimeapps(text: str, m: dict[str, str], extra: dict[str, str]) -> str:
    out, section, seen = [], None, set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('['):
            if section == '[Default Applications]':
                out += [f'{k}={v}' for k, v in extra.items() if k not in seen]
            section = stripped
        elif section == '[Default Applications]' and '=' in line:
            key, value = line.split('=', 1)
            seen.add(key)
            items = [m.get(x, x) for x in value.split(';') if x]
            if key in extra and not any(x in m.values() for x in items):
                items = [extra[key]]
            items = list(dict.fromkeys(items))
            line = f'{key}={";".join(items)}' + (';' if value.endswith(';') else '')
        out.append(line)
    if section == '[Default Applications]':
        out += [f'{k}={v}' for k, v in extra.items() if k not in seen]
    return '\n'.join(out) + '\n'


def set_casper(text: str) -> str:
    values = {'USERNAME': 'kirin', 'USERFULLNAME': 'Kirin live session', 'HOST': HOSTNAME, 'FLAVOUR': 'Kirin'}
    out, seen = [], set()
    for line in text.splitlines():
        m = re.match(r'^\s*#?\s*export\s+(\w+)=', line)
        if m and m.group(1) in values:
            line = f'export {m.group(1)}="{values[m.group(1)]}"'
            seen.add(m.group(1))
        out.append(line)
    out += [f'export {k}="{v}"' for k, v in values.items() if k not in seen]
    return '\n'.join(out) + '\n'


def apply(root: Path) -> list[str]:
    notes = []
    (root / 'etc/kirin-release').write_text(
        f'KIRIN_VERSION="{KIRIN_VERSION}"\nKIRIN_NAME="Kirin Linux"\nKIRIN_BASE="openKylin 3.0"\n', encoding='utf-8')
    (root / 'etc/hostname').write_text(HOSTNAME + '\n', encoding='utf-8')
    hosts = root / 'etc/hosts'
    lines = hosts.read_text(encoding='utf-8').splitlines() if hosts.is_file() else []
    lines = [l for l in lines if not re.match(r'^127\.0\.1\.1\s', l)]
    if not any(re.match(r'^127\.0\.0\.1\s', l) for l in lines):
        lines.insert(0, '127.0.0.1\tlocalhost')
    lines.insert(1, f'127.0.1.1\t{HOSTNAME}')
    hosts.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    casper = root / 'etc/casper.conf'
    if casper.is_file():
        casper.write_text(set_casper(casper.read_text(encoding='utf-8')), encoding='utf-8')
        notes.append('live session user and host: kirin')
    bashrc = root / 'etc/bash.bashrc'
    if bashrc.is_file():
        text = bashrc.read_text(encoding='utf-8')
        if BASHRC_BEGIN not in text:
            bashrc.write_text(text.rstrip('\n') + '\n\n' + BASHRC_BLOCK, encoding='utf-8')
    m = mapping(root)
    extra = {k: v for k, v in EXTRA_DEFAULTS.items() if installed(root, v)}
    for rel in MIMEAPPS:
        p = root / rel
        if p.is_file() and not p.is_symlink():
            p.write_text(rewrite_mimeapps(p.read_text(encoding='utf-8'), m, extra), encoding='utf-8')
    notes.append(f'default apps: {", ".join(sorted(set(m.values()))) or "none available"}')
    pins = [str(Path('/') / d / p) for p in PINS for d in APP_DIRS if (root / d / p).is_file()]
    pins = list(dict.fromkeys(pins))
    pin_file = root / PINS_FILE
    pin_file.parent.mkdir(parents=True, exist_ok=True)
    pin_file.write_text(json.dumps({'quickLaunchers': pins}, indent=2) + '\n', encoding='utf-8')
    notes.append(f'taskbar pins: {", ".join(Path(p).stem for p in pins)}')
    return notes


def audit(root: Path) -> list[str]:
    problems = []
    if (root / 'etc/hostname').read_text(encoding='utf-8').strip() != HOSTNAME:
        problems.append('hostname is not kirin')
    if not (root / 'etc/kirin-release').is_file():
        problems.append('/etc/kirin-release missing')
    if (root / 'etc/bash.bashrc').is_file() and BASHRC_BEGIN not in (root / 'etc/bash.bashrc').read_text(encoding='utf-8'):
        problems.append('Fastfetch terminal hook missing')
    m = mapping(root)
    for rel in MIMEAPPS:
        p = root / rel
        if p.is_file():
            text = p.read_text(encoding='utf-8')
            for old in m:
                if re.search(rf'[=;]{re.escape(old)}(;|$)', text, re.M):
                    problems.append(f'{rel} still opens files with {old}')
    if not (root / PINS_FILE).is_file():
        problems.append('taskbar pins missing')
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Apply or audit Kirin system defaults in an offline image')
    ap.add_argument('--root', type=Path, required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--audit', action='store_true')
    args = ap.parse_args(argv)
    try:
        root = image_root(args.root)
        if args.apply:
            for note in apply(root):
                print(note)
            return 0
        problems = audit(root)
    except (OSError, ValueError) as exc:
        print(f'POLISH FAILED: {exc}', file=sys.stderr)
        return 2
    for p in problems:
        print('FAIL:', p)
    if problems:
        return 1
    print('Kirin defaults check passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
