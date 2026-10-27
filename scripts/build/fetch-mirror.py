#!/usr/bin/env python3
"""Fetch a content pack from Kirin's own mirror (GitHub release assets).

packaging/content/mirror.json (written by scripts/publish-content.sh) lists, per
pack, the release asset parts (each under GitHub's 2 GB limit) with their SHA-256
and the SHA-256 of the whole tar. Every part is verified, the parts are joined
and verified again, and the tar is unpacked safely (no absolute paths, links out
of the destination or device files) into --dest, replacing what was there. If the
pack has a SHA256SUMS inside, every file is checked against it too.

Exit status: 0 done, 1 failed (try the original sources), 3 pack not mirrored.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import time
from urllib import request

USER_AGENT = 'kirin-build/1 (+https://github.com/factionparadox/Kirin)'
CHUNK = 4 << 20


def sha256_file(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def download(url: str, target: Path, sha: str, size: int, attempts: int = 3) -> None:
    if target.is_file() and target.stat().st_size == size and sha256_file(target) == sha:
        return
    part = target.with_name(target.name + '.part')
    for attempt in range(1, attempts + 1):
        try:
            req = request.Request(url, headers={'User-Agent': USER_AGENT})
            with request.urlopen(req, timeout=120) as response, part.open('wb') as out:
                while chunk := response.read(CHUNK):
                    out.write(chunk)
            if part.stat().st_size != size or sha256_file(part) != sha:
                raise OSError('checksum mismatch')
            os.replace(part, target)
            return
        except OSError as exc:
            part.unlink(missing_ok=True)
            if attempt == attempts:
                raise OSError(f'{target.name}: {exc}') from exc
            time.sleep(2 * attempt)


def check_sums(folder: Path) -> list[str]:
    sums = folder / 'SHA256SUMS'
    if not sums.is_file():
        return []
    bad = []
    for line in sums.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition('  ')
        path = folder / name
        if not path.is_file() or sha256_file(path) != digest:
            bad.append(name)
    return bad


def fetch(mirror: dict, pack: str, dest: Path, base: str | None = None) -> str:
    entry = mirror['packs'][pack]
    base = (base or mirror['url']).rstrip('/') + '/'
    dest.parent.mkdir(parents=True, exist_ok=True)
    work = dest.parent / f'.kirin-mirror-{pack}'
    work.mkdir(exist_ok=True)
    for p in entry['parts']:
        print(f'  {p["name"]} ({p["size"] / 1e9:.2f} GB)', flush=True)
        download(base + p['name'], work / p['name'], p['sha256'], p['size'])
    whole, digest = work / f'{pack}.tar', hashlib.sha256()
    with whole.open('wb') as out:
        for p in entry['parts']:
            with (work / p['name']).open('rb') as part:
                while chunk := part.read(CHUNK):
                    digest.update(chunk)
                    out.write(chunk)
    if digest.hexdigest() != entry['sha256']:
        raise OSError('joined parts do not match the recorded checksum')
    staging = work / 'unpacked'
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    with tarfile.open(whole) as tar:
        tar.extractall(staging, filter='data')
    top = [p for p in staging.iterdir()]
    if len(top) != 1 or not top[0].is_dir():
        raise OSError('unexpected archive layout')
    bad = check_sums(top[0])
    if bad:
        raise OSError(f'{len(bad)} files do not match SHA256SUMS, e.g. {bad[0]}')
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(top[0]), dest)
    shutil.rmtree(work, ignore_errors=True)
    return f'{entry.get("files", "?")} files, {entry["size"] / 1e9:.2f} GB, verified'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--mirror', type=Path, required=True, help='mirror.json')
    ap.add_argument('--pack', required=True)
    ap.add_argument('--dest', type=Path, required=True)
    ap.add_argument('--base', help='override the release download URL (tests)')
    args = ap.parse_args(argv)
    try:
        mirror = json.loads(args.mirror.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        print('Kirin mirror: not set up yet', file=sys.stderr)
        return 3
    if args.pack not in mirror.get('packs', {}):
        print(f'Kirin mirror: {args.pack} not mirrored', file=sys.stderr)
        return 3
    try:
        print(f'Kirin mirror ({mirror.get("release", "?")}): {args.pack}: {fetch(mirror, args.pack, args.dest, args.base)}')
        return 0
    except (OSError, KeyError, ValueError, tarfile.TarError) as exc:
        print(f'Kirin mirror: {args.pack} failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
