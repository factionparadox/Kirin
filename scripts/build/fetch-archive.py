#!/usr/bin/env python3
"""Fetch LibriVox audiobooks from the Internet Archive, verified against the Archive's own checksums.

Manifest: one `archive-identifier<TAB>level` per line (`#` comments allowed).
For each item the Archive's metadata (https://archive.org/metadata/ID) is read;
the item must be in Russian. Its "64Kbps MP3" files are downloaded (resuming
complete, verified files) and each is checked against the MD5 *and* SHA-1 the
Archive publishes. Output, under --dest:

    LEVEL/<title> - <creator>/NN - track.mp3
    catalog.json      [{id, level, title, creator, runtime, folder, files}]
    SHA256SUMS        for the Kirin image audit

A missing or failed item is reported and skipped (the Archive is a volunteer
service), unless --required is given.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib import parse, request

USER_AGENT = 'kirin-build/1 (+https://github.com/factionparadox/Kirin)'
CHUNK = 1 << 20
FORMAT = '64Kbps MP3'
LEVELS = ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')
RUSSIAN = {'rus', 'russian', 'ru', 'русский'}


def read_manifest(path: Path) -> list[tuple[str, str]]:
    rows, seen = [], set()
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        parts = [p.strip() for p in line.split('\t')]
        if len(parts) != 2 or not re.fullmatch(r'[A-Za-z0-9._-]+', parts[0]) or parts[1] not in LEVELS:
            raise ValueError(f'{path}:{number}: expected identifier<TAB>level (A1-C2)')
        if parts[0] in seen:
            raise ValueError(f'{path}:{number}: duplicate {parts[0]}')
        seen.add(parts[0])
        rows.append((parts[0], parts[1]))
    return rows


def get(url: str, timeout: int = 60):
    return request.urlopen(request.Request(url, headers={'User-Agent': USER_AGENT}), timeout=timeout)


def safe_name(text: str, limit: int = 80) -> str:
    text = re.sub(r'[\x00-\x1f/\\:*?"<>|]+', ' ', text).strip(' .')
    return re.sub(r'\s+', ' ', text)[:limit].strip() or 'untitled'


def first(value, default=''):
    if isinstance(value, list):
        return str(value[0]) if value else default
    return str(value) if value is not None else default


def digests(path: Path) -> tuple[str, str]:
    md5, sha1 = hashlib.md5(), hashlib.sha1()
    with path.open('rb') as handle:
        while chunk := handle.read(CHUNK):
            md5.update(chunk)
            sha1.update(chunk)
    return md5.hexdigest(), sha1.hexdigest()


def download(url: str, target: Path, md5: str, sha1: str, attempts: int = 3) -> None:
    part = target.with_name(target.name + '.part')
    for attempt in range(1, attempts + 1):
        try:
            with get(url, timeout=120) as response, part.open('wb') as out:
                while chunk := response.read(CHUNK):
                    out.write(chunk)
            if digests(part) != (md5, sha1):
                raise OSError('checksum mismatch')
            os.replace(part, target)
            return
        except OSError as exc:
            part.unlink(missing_ok=True)
            if attempt == attempts:
                raise OSError(f'{target.name}: {exc}') from exc
            time.sleep(2 * attempt)


def fetch_item(base: str, ident: str, level: str, dest: Path) -> dict:
    with get(f'{base}metadata/{ident}') as response:
        meta = json.load(response)
    info = meta.get('metadata') or {}
    if not info:
        raise ValueError('no such item')
    languages = info.get('language') or []
    languages = {str(l).strip().lower() for l in (languages if isinstance(languages, list) else [languages])}
    if not languages & RUSSIAN:
        raise ValueError(f'not a Russian recording (language: {", ".join(sorted(languages)) or "none"})')
    tracks = sorted((f for f in meta.get('files', []) if f.get('format') == FORMAT and f.get('md5') and f.get('sha1')),
                    key=lambda f: f['name'])
    if not tracks:
        raise ValueError(f'no {FORMAT} files with checksums')
    title, creator = first(info.get('title'), ident), first(info.get('creator'), 'unknown')
    folder = Path(level) / safe_name(f'{title} - {creator}', 120)
    out = dest / folder
    out.mkdir(parents=True, exist_ok=True)
    names = []
    for f in tracks:
        name = safe_name(Path(f['name']).name, 150)
        target = out / name
        if not (target.is_file() and digests(target) == (f['md5'], f['sha1'])):
            url = f'{base}download/{ident}/{parse.quote(f["name"])}'
            download(url, target, f['md5'], f['sha1'])
        names.append(name)
    for stale in out.iterdir():
        if stale.name not in names:
            stale.unlink()
    return {'id': ident, 'level': level, 'title': title, 'creator': creator,
            'runtime': first(info.get('runtime')), 'folder': str(folder), 'files': names}


def write_sums(dest: Path, catalog: list[dict]) -> None:
    lines = []
    for book in catalog:
        for name in book['files']:
            rel = f'{book["folder"]}/{name}'
            with (dest / rel).open('rb') as handle:
                lines.append(f'{hashlib.file_digest(handle, "sha256").hexdigest()}  {rel}')
    (dest / 'SHA256SUMS').write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--manifest', type=Path, required=True)
    ap.add_argument('--dest', type=Path, required=True)
    ap.add_argument('--base', default='https://archive.org/', help='Archive base URL (tests use a local server)')
    ap.add_argument('--required', action='store_true')
    args = ap.parse_args(argv)
    base = args.base if args.base.endswith('/') else args.base + '/'
    try:
        rows = read_manifest(args.manifest)
    except (OSError, ValueError) as exc:
        print(f'AUDIOBOOKS FAILED: {exc}', file=sys.stderr)
        return 2
    args.dest.mkdir(parents=True, exist_ok=True)
    catalog, failed = [], 0
    for ident, level in rows:
        try:
            book = fetch_item(base, ident, level, args.dest)
            catalog.append(book)
            print(f'{level} {book["title"]} - {book["creator"]}: {len(book["files"])} tracks')
        except (OSError, ValueError) as exc:
            failed += 1
            print(f'not available: {ident}: {exc}')
    order = {lvl: n for n, lvl in enumerate(LEVELS)}
    catalog.sort(key=lambda b: (order[b['level']], b['title']))
    (args.dest / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding='utf-8')
    write_sums(args.dest, catalog)
    print(f'{len(rows)} audiobooks: {len(catalog)} ready, {failed} unavailable')
    return 1 if failed and args.required else 0


if __name__ == '__main__':
    sys.exit(main())
