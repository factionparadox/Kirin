#!/usr/bin/env python3
"""Fail-closed review of an `apt-get -s purge` transaction.

Reads the simulation on stdin. Passes only when APT would remove exactly the
requested packages (plus any explicitly allowed after human review) and none
of them is protected. Never runs APT itself.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ACTION = re.compile(r'^(Remv|Purg) (\S+)')
PROTECTED_NAMES = frozenset({
    'apt', 'dpkg', 'login', 'passwd', 'sudo', 'polkitd', 'pkexec', 'accountsservice',
    'libpam0g', 'libpam-modules', 'libpam-runtime', 'systemd', 'systemd-sysv',
    'lightdm', 'flatpak', 'xdg-desktop-portal', 'vim', 'neovim', 'python3',
    'network-manager', 'grub-efi-amd64-signed', 'shim-signed', 'casper', 'initramfs-tools',
})
PROTECTED_PATTERNS = (
    re.compile(r'^ukui-'), re.compile(r'^libukui'), re.compile(r'^peony'),
    re.compile(r'^kylin-os-installer'), re.compile(r'^kylin-installer'),
    re.compile(r'^(?:kylin|ukui)-system-updater'), re.compile(r'^kylin-update'),
    re.compile(r'^linux-(?:image|modules)'), re.compile(r'^libapt'),
)


def removals(simulation: str) -> list[str]:
    out = []
    for line in simulation.splitlines():
        match = ACTION.match(line)
        if match:
            out.append(match.group(2).split(':')[0])
    return out


def is_protected(name: str, model_owners: set[str]) -> bool:
    return name in PROTECTED_NAMES or name in model_owners or any(p.match(name) for p in PROTECTED_PATTERNS)


def review(simulation: str, requested: set[str], allowed: set[str], model_owners: set[str]) -> list[str]:
    removed = removals(simulation)
    problems = []
    for name in removed:
        if is_protected(name, model_owners):
            problems.append(f'protected package would be removed: {name}')
        elif name not in requested and name not in allowed:
            problems.append(f'unrequested removal: {name} (review it, then pass --allow-removal {name})')
    for name in sorted(requested - set(removed)):
        problems.append(f'requested package not removed by APT: {name}')
    return problems


def load_owners(path: Path | None) -> set[str]:
    if not path:
        return set()
    report = json.loads(path.read_text(encoding='utf-8'))
    return {entry['package'] for entry in report.values() if isinstance(entry, dict) and entry.get('package')}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--requested', nargs='+', required=True)
    ap.add_argument('--allow', nargs='*', default=[])
    ap.add_argument('--model-owners', type=Path, help='ownership report from inventory-models.py')
    args = ap.parse_args(argv)
    try:
        owners = load_owners(args.model_owners)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f'REMOVAL REFUSED: cannot read model owners: {exc}', file=sys.stderr)
        return 2
    simulation = sys.stdin.read()
    problems = review(simulation, set(args.requested), set(args.allow), owners)
    for name in removals(simulation):
        print(f'APT would remove: {name}')
    for problem in problems:
        print(f'REMOVAL REFUSED: {problem}', file=sys.stderr)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
