#!/usr/bin/env python3
"""Build Kirin's own .deb packages from packaging/debs/*/spec.json.

Each spec lists upstream files by URL with a pinned SHA-256, where they go, and
the package's dependencies. Sources are downloaded (or reused from --cache),
verified, laid out and packed with dpkg-deb. Used inside the image build and by
the GitHub workflow that publishes the signed Kirin APT repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from urllib import request

REQUIRED = ('package', 'version', 'architecture', 'summary', 'description', 'files')
NAME = re.compile(r'^[a-z0-9][a-z0-9+.-]+$')
VERSION = re.compile(r'^[0-9][A-Za-z0-9.+~:-]*$')
MAINTAINER = 'Kirin Linux <https://github.com/factionparadox/Kirin>'


def load_spec(path: Path) -> dict:
    spec = json.loads(path.read_text(encoding='utf-8'))
    missing = [k for k in REQUIRED if not spec.get(k)]
    if missing:
        raise ValueError(f'{path}: missing {", ".join(missing)}')
    if not NAME.match(spec['package']) or not VERSION.match(spec['version']):
        raise ValueError(f'{path}: invalid package name or version')
    for f in spec['files']:
        dest = PurePosixPath(f.get('dest', ''))
        if not f.get('url') or not re.fullmatch(r'[0-9a-f]{64}', f.get('sha256', '')):
            raise ValueError(f'{path}: every file needs a url and a sha256')
        if dest.is_absolute() or '..' in dest.parts or not dest.parts:
            raise ValueError(f'{path}: unsafe destination {f.get("dest")!r}')
    return spec


def fetch(url: str, sha256: str, cache: Path) -> Path:
    target = cache / sha256
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == sha256:
        return target
    cache.mkdir(parents=True, exist_ok=True)
    req = request.Request(url, headers={'User-Agent': 'kirin-build/1'})
    with request.urlopen(req, timeout=60) as response:
        data = response.read()
    actual = hashlib.sha256(data).hexdigest()
    if actual != sha256:
        raise ValueError(f'{url}: SHA-256 {actual} does not match the pinned {sha256}')
    tmp = target.with_suffix('.part')
    tmp.write_bytes(data)
    os.replace(tmp, target)
    return target


def control(spec: dict, installed_kb: int) -> str:
    fields = [('Package', spec['package']), ('Version', spec['version']),
              ('Architecture', spec['architecture']), ('Maintainer', MAINTAINER),
              ('Installed-Size', str(installed_kb)), ('Section', spec.get('section', 'misc')),
              ('Priority', 'optional')]
    for key in ('depends', 'recommends', 'suggests', 'conflicts', 'provides', 'replaces'):
        if spec.get(key):
            fields.append((key.capitalize(), spec[key]))
    if spec.get('homepage'):
        fields.append(('Homepage', spec['homepage']))
    body = '\n'.join(' ' + (line if line.strip() else '.') for line in spec['description'].splitlines())
    return ''.join(f'{k}: {v}\n' for k, v in fields) + f'Description: {spec["summary"]}\n{body}\n'


def build(spec_path: Path, out: Path, cache: Path) -> Path:
    spec = load_spec(spec_path)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / 'root'
        (root / 'DEBIAN').mkdir(parents=True)
        for f in spec['files']:
            src = fetch(f['url'], f['sha256'], cache)
            dest = root / f['dest']
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            os.chmod(dest, int(f.get('mode', '0644'), 8))
        size_kb = sum(p.stat().st_size for p in root.rglob('*') if p.is_file()) // 1024 + 1
        (root / 'DEBIAN/control').write_text(control(spec, size_kb), encoding='utf-8')
        for d in [root, *[p for p in root.rglob('*') if p.is_dir()]]:
            os.chmod(d, 0o755)
        out.mkdir(parents=True, exist_ok=True)
        deb = out / f'{spec["package"]}_{spec["version"].split(":")[-1]}_{spec["architecture"]}.deb'
        subprocess.run(['dpkg-deb', '--root-owner-group', '-Zxz', '--build', str(root), str(deb)],
                       check=True, capture_output=True)
    return deb


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--specs', type=Path, required=True, help='directory of <package>/spec.json')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--cache', type=Path, help='download cache (default: OUT/.cache)')
    args = ap.parse_args(argv)
    cache = args.cache or args.out / '.cache'
    if not shutil.which('dpkg-deb'):
        print('BUILD FAILED: dpkg-deb is required', file=sys.stderr)
        return 2
    failed = 0
    for spec_path in sorted(args.specs.glob('*/spec.json')):
        try:
            print(build(spec_path, args.out, cache))
        except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
            detail = exc.stderr.decode('utf-8', 'replace') if isinstance(exc, subprocess.CalledProcessError) else exc
            print(f'BUILD FAILED: {spec_path.parent.name}: {detail}', file=sys.stderr)
            failed += 1
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
