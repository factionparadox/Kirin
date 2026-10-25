#!/usr/bin/env python3
"""Fetch the newest Kiwix ZIM matching a prefix and verify Kiwix's published SHA-256.

Reads the download directory listing, picks the newest `<prefix>YYYY-MM.zim`
(or the file given by --name), downloads it with resume, checks it against the
`.sha256` file Kiwix publishes next to it, and removes older ZIMs of the same
prefix from the destination. Prints the chosen file name.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import sys
from urllib import error, request

CHUNK = 4 << 20
USER_AGENT = 'kirin-build/1 (+https://github.com/factionparadox/Kirin)'


def get(url: str, headers: dict | None = None, timeout: int = 60):
    return request.urlopen(request.Request(url, headers={'User-Agent': USER_AGENT, **(headers or {})}),
                           timeout=timeout)


def newest(listing: str, prefix: str) -> str:
    pattern = re.compile(re.escape(prefix) + r'(\d{4}-\d{2})\.zim')
    names = sorted({m.group(0) for m in pattern.finditer(listing)}, key=lambda n: pattern.fullmatch(n).group(1))
    if not names:
        raise ValueError(f'no {prefix}YYYY-MM.zim in the listing')
    return names[-1]


def published_sha(index: str, name: str) -> str:
    with get(index + name + '.sha256') as response:
        text = response.read().decode('ascii', 'replace')
    match = re.search(r'\b([0-9a-f]{64})\b', text)
    if not match:
        raise ValueError(f'no SHA-256 in {name}.sha256')
    return match.group(1)


def sha256_file(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def download_resumable(url: str, part: Path) -> None:
    have = part.stat().st_size if part.exists() else 0
    headers = {'Range': f'bytes={have}-'} if have else {}
    try:
        response = get(url, headers, timeout=120)
    except error.HTTPError as exc:
        if exc.code == 416 and have:        # already complete
            return
        raise
    with response:
        resumed = have and response.status == 206
        with part.open('ab' if resumed else 'wb') as out:
            while chunk := response.read(CHUNK):
                out.write(chunk)


def fetch(index: str, prefix: str, dest: Path, name: str | None = None) -> str:
    if not index.endswith('/'):
        index += '/'
    if not name:
        with get(index) as response:
            name = newest(response.read().decode('utf-8', 'replace'), prefix)
    elif not re.fullmatch(re.escape(prefix) + r'\d{4}-\d{2}\.zim', name):
        raise ValueError(f'{name!r} does not match {prefix}YYYY-MM.zim')
    expected = published_sha(index, name)
    dest.mkdir(parents=True, exist_ok=True)
    final = dest / name
    if not (final.is_file() and sha256_file(final) == expected):
        part = dest / (name + '.part')
        for _ in range(2):
            download_resumable(index + name, part)
            if sha256_file(part) == expected:
                break
            part.unlink()                     # corrupt or wrongly resumed: start over once
        else:
            raise ValueError(f'{name} does not match its published SHA-256')
        os.replace(part, final)
    for old in dest.glob(prefix + '*.zim'):
        if old.name != name:
            old.unlink()
    return name


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--index', required=True, help='Kiwix directory URL, e.g. https://download.kiwix.org/zim/wiktionary/')
    ap.add_argument('--prefix', required=True, help='e.g. wiktionary_en_all_nopic_')
    ap.add_argument('--dest', type=Path, required=True)
    ap.add_argument('--name', help='pin an exact file instead of the newest')
    args = ap.parse_args(argv)
    try:
        print(fetch(args.index, args.prefix, args.dest, args.name))
        return 0
    except (OSError, ValueError) as exc:
        print(f'KIWIX FETCH FAILED: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
