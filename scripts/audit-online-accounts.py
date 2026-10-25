#!/usr/bin/env python3
"""Fail-closed offline Kirin image policy for openKylin cloud accounts.

Read-only. Never purge packages, edit installed files or access live user data.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

# Verified source package on the openKylin Huanghe build service.
FORBIDDEN_PACKAGES = frozenset({'openkylin-token-center'})
# These are pattern candidates, not verified names: inspect when present.
REVIEW_PACKAGE_RE = re.compile(
    r'(?:^|[-_])(?:openkylin[-_]?id|kylin[-_]?id|kylin[-_]?cloud|cloud[-_]?sync|token[-_]?center)(?:$|[-_])',
    re.I,
)
# Account-related interfaces only, not generic Linux users or browser sign-in.
ACCOUNT_SIGNATURES = [
    ('Token Centre', re.compile(r'(?i)\b(?:openkylin[-_ ]?token[-_ ]?center|token[ -]?cent(?:re|er))\b')),
    ('Kylin ID', re.compile(r'(?i)\b(?:openkylin|kylin)[ -]?id\b')),
    ('Kylin cloud account', re.compile(r'(?i)\b(?:cloud[ -]?account|cloud[ -]?(?:setting|configuration)[ -]?sync)\b')),
    ('Cloud AI gateway', re.compile(r'(?i)llm-gateway\.openkylin\.top')),
    ('Device registration', re.compile(r'(?i)\b(?:bind (?:your )?device|daily check-in for tokens)\b')),
]
SCAN_PATHS = (
    'usr/share/applications', 'usr/local/share/applications',
    'etc/xdg/autostart', 'usr/share/desktop-directories',
    'usr/share/dbus-1/services', 'usr/share/dbus-1/system-services',
    'etc/systemd/system', 'usr/lib/systemd/system',
)
EXCLUDE_SUFFIXES = {'.png', '.jpg', '.svg', '.so', '.bin', '.mo', '.qm', '.pyc'}
# Local accounts and security services must never be removed as "cloud accounts".
PROTECTED = frozenset({
    'accountsservice', 'passwd', 'login', 'libpam0g', 'libpam-modules',
    'libpam-runtime', 'systemd', 'systemd-sysv', 'systemd-logind',
    'polkitd', 'sudo', 'lightdm', 'ukui-session-manager', 'ukui-control-center',
    'ollama', 'neovim', 'vim',
})


def image_root(root: Path) -> Path:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir() or root.resolve() == Path('/'):
        raise ValueError('use an existing offline image directory other than /')
    return root


def within(root: Path, rel: str) -> Path:
    p = root
    for bit in Path(rel).parts:
        p = p / bit
        if p.is_symlink():
            raise ValueError(f'refusing symlinked path: {p.relative_to(root)}')
    return p


def packages(root: Path) -> dict[str, dict[str, str]]:
    status = within(root, 'var/lib/dpkg/status')
    if not status.is_file():
        raise ValueError('image has no dpkg status database: cannot verify installed packages')
    out = {}
    for stanza in re.split(r'\n\s*\n', status.read_text(encoding='utf-8')):
        entry = {}
        for line in stanza.splitlines():
            if ':' in line and not line[0].isspace():
                k, v = line.split(':', 1)
                entry[k] = v.strip()
        if entry.get('Package') and entry.get('Status', '').split()[-1:] == ['installed']:
            out[entry['Package'].split(':')[0]] = entry
    return out


def audit(root: Path) -> list[str]:
    installed = packages(root)
    findings = []
    for name in installed:
        if name in FORBIDDEN_PACKAGES:
            findings.append(f'BLOCK package: {name} (Kirin must not ship Token Centre)')
        elif REVIEW_PACKAGE_RE.search(name) and name not in PROTECTED:
            findings.append(f'REVIEW package: {name} (inspect upstream account integration)')
    for folder_rel in SCAN_PATHS:
        folder = within(root, folder_rel)
        if not folder.exists():
            continue
        if not folder.is_dir():
            raise ValueError(f'non-directory policy scan root: {folder_rel}')
        for path in folder.rglob('*'):
            if path.is_symlink():
                # Unit aliases and masked units are normal on merged-/usr systems.
                # Never follow links into the host when inspecting an offline root.
                if REVIEW_PACKAGE_RE.search(path.name) or any(sig.search(path.name) for _, sig in ACCOUNT_SIGNATURES):
                    findings.append(f'REVIEW account-related symlink: {path.relative_to(root)}')
                continue
            if not path.is_file() or path.suffix.lower() in EXCLUDE_SUFFIXES:
                continue
            if path.stat().st_size > 256_000:
                findings.append(f'REVIEW oversized launcher/service: {path.relative_to(root)}')
                continue
            # Only examine declarative launcher and service files; no arbitrary user data.
            if path.suffix not in ('.desktop', '.service', '.conf', '.ini'):
                continue
            content = path.read_text(encoding='utf-8', errors='replace')
            matches = [label for label, pattern in ACCOUNT_SIGNATURES if pattern.search(content)]
            if matches:
                findings.append(f'BLOCK launcher/service: {path.relative_to(root)} ({", ".join(matches)})')
    return sorted(findings)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Audit offline Kirin image for upstream cloud-account integrations')
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--plan', action='store_true', help='explain removal steps; never alter the image')
    args = ap.parse_args(argv)
    try:
        root = image_root(args.root)
        findings = audit(root)
        if args.plan:
            print('Known removable upstream component: openkylin-token-center')
            print('In the disposable openKylin image build environment, simulate first:')
            print('    apt-get -s purge openkylin-token-center')
            print('Inspect dependency removals. Preserve UKUI, login/PAM, offline AI and Ollama.')
            print('Patch/rebuild any UKUI panel that still references Kylin ID or cloud sync.')
            print('Re-run this audit after package removal, image updates and localisation.')
        for finding in findings:
            print(finding)
        if findings:
            print('REJECTED: account/cloud integration still present or requires review', file=sys.stderr)
            return 1
        print('No known upstream cloud-account clients or entry points found in scanned locations.')
        print('PASS (static scan only; verify upstream control-centre plugins and online behaviour on ISO).')
        return 0
    except (ValueError, OSError, UnicodeError) as error:
        print(f'UNVERIFIED: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
