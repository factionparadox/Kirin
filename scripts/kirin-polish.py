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
* Terminal: if kitty is installed it becomes the default terminal (translucent,
  blurred, Kirin colours, running fish if installed) and MATE Terminal is hidden
  from the menu but kept, because parts of UKUI call it directly.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
BRANDING = REPO / 'packaging/branding'
TERMINAL_DIR = REPO / 'packaging/terminal'

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
PINS = ('peony.desktop', 'kitty.desktop', 'mate-terminal.desktop', 'firefox.desktop', 'com.jeffser.Alpaca.desktop',
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


TERMINAL_SCHEMAS = {   # schema id -> keys; only written when the schema exists in the image
    'org.mate.applications-terminal': {'exec': "'kitty'", 'exec-arg': "'--'"},
    'org.gnome.desktop.default-applications.terminal': {'exec': "'kitty'", 'exec-arg': "'--'"},
}
SCHEMA_OVERRIDE = 'usr/share/glib-2.0/schemas/90_kirin-terminal.gschema.override'


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


def schema_ids(root: Path) -> set[str]:
    ids = set()
    for p in (root / 'usr/share/glib-2.0/schemas').glob('*.gschema.xml'):
        ids.update(re.findall(r'<schema [^>]*id="([^"]+)"', p.read_text(encoding='utf-8', errors='replace')))
    return ids


def hide_desktop(path: Path) -> None:
    lines = path.read_text(encoding='utf-8').splitlines()
    if any(l.strip() == 'NoDisplay=true' for l in lines):
        return
    out, done = [], False
    for line in lines:
        out.append(line)
        if line.strip() == '[Desktop Entry]' and not done:
            out.append('NoDisplay=true')
            done = True
    path.write_text('\n'.join(out) + '\n', encoding='utf-8')


def apply_terminal(root: Path) -> list[str]:
    if not installed(root, 'kitty.desktop'):
        return ['terminal: kitty not installed, keeping MATE Terminal']
    has_fish = (root / 'usr/bin/fish').is_file()
    conf = (TERMINAL_DIR / 'kitty.conf').read_text(encoding='utf-8')
    if has_fish:
        conf += '\n# Kirin: kitty starts fish (your login shell is unchanged)\nshell /usr/bin/fish\n'
    dest = root / 'etc/xdg/kitty/kitty.conf'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(conf, encoding='utf-8')
    if has_fish:
        fish = root / 'etc/fish/conf.d/kirin.fish'
        fish.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TERMINAL_DIR / 'kirin.fish', fish)
    (root / 'etc/xdg/xdg-terminals.list').write_text('kitty.desktop\n', encoding='utf-8')
    known = schema_ids(root)
    blocks = [f'[{sid}]\n' + ''.join(f'{k}={v}\n' for k, v in keys.items())
              for sid, keys in TERMINAL_SCHEMAS.items() if sid in known]
    override = root / SCHEMA_OVERRIDE
    if blocks:
        override.write_text('# Kirin: kitty is the default terminal\n' + '\n'.join(blocks), encoding='utf-8')
    mate = root / 'usr/share/applications/mate-terminal.desktop'
    if mate.is_file() and not mate.is_symlink():
        hide_desktop(mate)
    return [f'terminal: kitty (translucent, blurred{", fish" if has_fish else ""}); MATE Terminal hidden']


FRAMEWORK_UDEV = 'etc/udev/rules.d/90-kirin-framework.rules'
FRAMEWORK_RULES = '''# Kirin: Framework Laptop hardware tweaks (harmless on other machines)
# Ethernet Expansion Card (Realtek 0bda:8156): short autosuspend delay so it saves power when idle
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="0bda", ATTR{idProduct}=="8156", ATTR{power/autosuspend}="20"
'''
FRAMEWORK_MODPROBE = 'etc/modprobe.d/kirin-framework.conf'
FRAMEWORK_OPTIONS = '''# Kirin: Framework Laptop module options (from NixOS's Framework 13 Intel module)
# Lower NVMe power use in suspend; ignored by drives that do not use ACPI hints.
options nvme noacpi=1
# Chromebook USB-PD charger driver: the Framework EC does not provide it and it logs a boot error.
blacklist cros-usbpd-charger
'''


WALLPAPER_DIR = 'usr/share/backgrounds/kirin'
WALLPAPER = f'/{WALLPAPER_DIR}/kirin.jpg'
WALLPAPER_OVERRIDE = 'usr/share/glib-2.0/schemas/91_kirin-wallpaper.gschema.override'
IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.svg', '.webp', '.bmp')
WALLPAPER_KEY = re.compile(r'picture|background|wallpaper|bg', re.I)


def wallpaper_keys(root: Path) -> list[tuple[str, str, str]]:
    """(schema id, key, current default) for every string setting whose default is a picture."""
    import xml.etree.ElementTree as ET
    found = []
    for xml in sorted((root / 'usr/share/glib-2.0/schemas').glob('*.gschema.xml')):
        try:
            tree = ET.parse(xml)
        except ET.ParseError:
            continue
        for schema in tree.getroot().iter('schema'):
            for key in schema.iter('key'):
                default = (key.findtext('default') or '').strip()
                value = default.strip('\'"')
                if (key.get('type') == 's' and WALLPAPER_KEY.search(key.get('name', ''))
                        and value.startswith('/') and value.lower().endswith(IMAGE_EXT)):
                    found.append((schema.get('id'), key.get('name'), value))
    return found


def apply_wallpaper(root: Path) -> list[str]:
    dest = root / WALLPAPER_DIR
    dest.mkdir(parents=True, exist_ok=True)
    for name in ('kirin.jpg', 'kirin.png'):
        shutil.copyfile(BRANDING / 'wallpaper' / name, dest / name)
    keys = wallpaper_keys(root)
    lines = ['# Kirin: the Kirin wallpaper wherever openKylin set a default picture']
    seen = set()
    for schema, key, old in keys:
        if (schema, key) in seen or not schema:
            continue
        seen.add((schema, key))
        lines += [f'# was {old}', f'[{schema}]', f"{key}='{WALLPAPER}'", '']
    (root / WALLPAPER_OVERRIDE).parent.mkdir(parents=True, exist_ok=True)
    (root / WALLPAPER_OVERRIDE).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    greeters = 0
    lightdm = root / 'etc/lightdm'
    for conf in sorted(lightdm.glob('*.conf')) + sorted(lightdm.glob('*.conf.d/*.conf')) if lightdm.is_dir() else []:
        if conf.is_symlink() or not conf.is_file():
            continue
        text = conf.read_text(encoding='utf-8', errors='surrogateescape')
        new = re.sub(r'^(\s*(?:background|background-image|background-path)\s*=\s*)(/\S+)$',
                     lambda m: m.group(1) + WALLPAPER if m.group(2).lower().endswith(IMAGE_EXT) else m.group(0),
                     text, flags=re.M)
        if new != text:
            conf.write_text(new, encoding='utf-8', errors='surrogateescape')
            greeters += 1
    return [f'wallpaper: {len(seen)} desktop/lock-screen settings and {greeters} login-screen files now use Kirin\'s']


ZRAM_CONF = 'etc/systemd/zram-generator.conf'
ZRAM_SETTINGS = '''# Kirin: compressed swap in RAM, so a large AI model and a browser fit together.
# Half the RAM (at most 16 GB) of zstd-compressed swap, used before any disk swap.
[zram0]
zram-size = min(ram / 2, 16384)
compression-algorithm = zstd
swap-priority = 100
'''
ZRAM_SYSCTL = 'etc/sysctl.d/90-kirin-zram.conf'
ZRAM_TUNING = '''# Kirin: tuning for zram swap (only installed with systemd-zram-generator).
# Swapping to compressed RAM is cheap, so swap earlier and read one page at a time.
vm.swappiness = 180
vm.page-cluster = 0
'''


def apply_zram(root: Path) -> list[str]:
    generator = any((root / d / 'zram-generator').exists()
                    for d in ('usr/lib/systemd/system-generators', 'lib/systemd/system-generators'))
    if not generator:
        (root / ZRAM_SYSCTL).unlink(missing_ok=True)
        return ['zram: systemd-zram-generator not installed; left as openKylin had it']
    for rel, text in ((ZRAM_CONF, ZRAM_SETTINGS), (ZRAM_SYSCTL, ZRAM_TUNING)):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding='utf-8')
    return ['zram: half the RAM as compressed swap (max 16 GB)']


def apply(root: Path) -> list[str]:
    rules = root / FRAMEWORK_UDEV
    rules.parent.mkdir(parents=True, exist_ok=True)
    rules.write_text(FRAMEWORK_RULES, encoding='utf-8')
    modprobe = root / FRAMEWORK_MODPROBE
    modprobe.parent.mkdir(parents=True, exist_ok=True)
    modprobe.write_text(FRAMEWORK_OPTIONS, encoding='utf-8')
    notes = apply_terminal(root) + apply_zram(root) + apply_wallpaper(root)
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
    if installed(root, 'kitty.desktop'):
        pins = [p for p in pins if not p.endswith('/mate-terminal.desktop')]
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
    if not (root / WALLPAPER_DIR / 'kirin.jpg').is_file():
        problems.append('Kirin wallpaper missing')
    override = root / WALLPAPER_OVERRIDE
    if not override.is_file() or '[' not in override.read_text(encoding='utf-8'):
        problems.append("no default-wallpaper setting found to replace; openKylin's wallpaper may still show")
    for schema, key, old in wallpaper_keys(root):
        override = root / WALLPAPER_OVERRIDE
        if not override.is_file() or f'[{schema}]\n{key}=' not in override.read_text(encoding='utf-8'):
            problems.append(f'wallpaper setting {schema} {key} still points at {old}')
    if not (root / FRAMEWORK_MODPROBE).is_file():
        problems.append('Framework module options missing')
    if installed(root, 'kitty.desktop'):
        if not (root / 'etc/xdg/kitty/kitty.conf').is_file():
            problems.append('kitty installed but not configured')
        if (root / 'usr/bin/fish').is_file() and not (root / 'etc/fish/conf.d/kirin.fish').is_file():
            problems.append('fish installed but Kirin fish config missing')
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
