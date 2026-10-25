#!/usr/bin/env python3
"""Download Proton's official Linux packages and verify them.

* VPN: the repository release package, checked against a pinned SHA-256.
* Pass, Mail: the newest .deb listed in Proton's version.json, checked against
  the SHA-512 given there.
Each item is independent: a failure is reported and skipped, never fatal.
Writes <dest>/<name>.deb and prints one status line per item.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib import request
from urllib.parse import urljoin

USER_AGENT = 'kirin-build/1 (+https://github.com/factionparadox/Kirin)'


def get(url: str) -> bytes:
    with request.urlopen(request.Request(url, headers={'User-Agent': USER_AGENT}), timeout=60) as r:
        return r.read()


def deb_entries(node, base: str):
    """Yield (url, sha512) for every .deb entry in a Proton version.json, newest first as listed."""
    if isinstance(node, dict):
        sha = next((v for k, v in node.items() if re.fullmatch(r'(?i)sha512.*', k) and isinstance(v, str)), None)
        url = next((v for k, v in node.items() if isinstance(v, str) and k.lower() in ('url', 'identifier', 'file', 'name')
                    and v.lower().endswith('.deb')), None)
        if sha and url and re.fullmatch(r'[0-9a-fA-F]{128}', sha):
            yield urljoin(base, url), sha.lower()
        for v in node.values():
            yield from deb_entries(v, base)
    elif isinstance(node, list):
        for v in node:
            yield from deb_entries(v, base)


def fetch_vpn(item: dict, dest: Path) -> str:
    data = get(item['url'])
    if hashlib.sha256(data).hexdigest() != item['sha256']:
        raise ValueError('release package does not match the pinned SHA-256')
    (dest / 'protonvpn-release.deb').write_bytes(data)
    (dest / 'protonvpn-package').write_text(item['package'] + '\n')
    return 'vpn: release package verified'


def fetch_listed(name: str, item: dict, dest: Path) -> str:
    listing = json.loads(get(item['version_json']))
    entries = list(deb_entries(listing, item['version_json']))
    if not entries:
        raise ValueError('version.json lists no .deb with a SHA-512')
    url, sha = entries[0]
    data = get(url)
    if hashlib.sha512(data).hexdigest() != sha:
        raise ValueError(f'{url} does not match its published SHA-512')
    (dest / f'proton{name}.deb').write_bytes(data)
    return f'{name}: {url.rsplit("/", 1)[-1]} verified'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--config', type=Path, required=True)
    ap.add_argument('--dest', type=Path, required=True)
    args = ap.parse_args(argv)
    config = json.loads(args.config.read_text(encoding='utf-8'))
    args.dest.mkdir(parents=True, exist_ok=True)
    for old in args.dest.glob('*.deb'):
        old.unlink()
    jobs = [('vpn', lambda: fetch_vpn(config['vpn'], args.dest))]
    jobs += [(n, (lambda n=n: fetch_listed(n, config[n], args.dest))) for n in ('pass', 'mail') if n in config]
    for name, job in jobs:
        try:
            print(job())
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f'SKIPPED {name}: {exc}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
