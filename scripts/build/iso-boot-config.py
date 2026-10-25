#!/usr/bin/env python3
"""Rebrand and re-localise the ISO's own boot menus (GRUB and isolinux).

Reads the extracted ISO tree, writes changed copies of its boot configuration
under --out (same relative paths) and prints each changed path, for the image
builder to map into the new ISO. The extracted tree itself is not modified.

* `locale=zh_CN…` becomes `locale=en_GB.UTF-8`, with a British keyboard, so the
  live session and the installer start in British English.
* "openKylin" in menu titles and labels becomes "Kirin Linux".
* GRUB gets the Kirin background image, if --grub-background is given.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import sys

CONFIGS = ('boot/grub/grub.cfg', 'boot/grub/loopback.cfg')
ISOLINUX_GLOB = 'isolinux/*.cfg'
LOCALE = re.compile(r'\blocale=zh_[A-Za-z]{2}(?:\.[Uu][Tt][Ff]-?8)?\b')
KEYBOARD = 'keyboard-configuration/layoutcode=gb'
TITLE_LINE = re.compile(r'^(\s*(?:menuentry|submenu|menu\s+label|menu\s+title|label)\b)(.*)$', re.I)
OPENKYLIN = re.compile(r'(?<![A-Za-z])open[Kk]ylin(?![A-Za-z])')
CJK = re.compile('[㐀-鿿]')


def rewrite(text: str, background: str | None = None) -> tuple[str, list[str]]:
    out, notes = [], []
    for line in text.splitlines(keepends=True):
        title = TITLE_LINE.match(line)
        if title:
            line = title.group(1) + OPENKYLIN.sub('Kirin Linux', title.group(2))
            if not line.endswith('\n'):
                line += '\n'
            if CJK.search(line):
                notes.append(f'untranslated menu text: {line.strip()}')
        if LOCALE.search(line):
            line = LOCALE.sub('locale=en_GB.UTF-8', line)
            if KEYBOARD not in line:
                line = line.replace('locale=en_GB.UTF-8', f'locale=en_GB.UTF-8 {KEYBOARD}', 1)
        out.append(line)
    result = ''.join(out)
    if background and 'terminal_output gfxterm' in result and 'background_image' not in result:
        result = result.replace('terminal_output gfxterm',
                                f'terminal_output gfxterm\n        insmod png\n        background_image {background}', 1)
    return result, notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--iso-tree', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--grub-background', help='ISO path of a PNG for the GRUB menu, e.g. /boot/grub/kirin.png')
    args = ap.parse_args(argv)
    tree = args.iso_tree
    if not (tree / 'boot').is_dir() and not (tree / 'isolinux').is_dir():
        print(f'BOOT CONFIG FAILED: {tree} does not look like an extracted ISO', file=sys.stderr)
        return 2
    if args.out.exists():
        shutil.rmtree(args.out)
    rels = [r for r in CONFIGS if (tree / r).is_file()]
    rels += sorted(str(p.relative_to(tree)) for p in tree.glob(ISOLINUX_GLOB) if p.is_file())
    for rel in rels:
        src = tree / rel
        if src.is_symlink():
            continue
        text = src.read_text(encoding='utf-8', errors='surrogateescape')
        background = args.grub_background if rel == 'boot/grub/grub.cfg' else None
        new, notes = rewrite(text, background)
        for note in notes:
            print(f'NOTE {rel}: {note}', file=sys.stderr)
        if new != text:
            dest = args.out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(new, encoding='utf-8', errors='surrogateescape')
            print(rel)
    return 0


if __name__ == '__main__':
    sys.exit(main())
