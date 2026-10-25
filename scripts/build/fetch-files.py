#!/usr/bin/env python3
"""Download files listed in a manifest, pinning each file's SHA-256 on first fetch.

Manifest: one `destination<TAB>url` per line; `#` comments and blank lines ignored.
Lock file: {destination: {"url", "sha256", "size"}}. A file already in the lock is
re-used if it still matches, and any new download of it must match the pinned
hash, so a source that later changes (or is tampered with) is refused.

Without --required a failed file is reported and skipped; with it, any failure
fails the run. Writes SHA256SUMS in the destination directory.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import time
from urllib import request

CHUNK = 1 << 20
USER_AGENT = 'kirin-build/1 (+https://github.com/factionparadox/Kirin)'


def read_manifest(path: Path) -> list[tuple[str, str]]:
    rows, seen = [], set()
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        parts = line.split('\t')
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f'{path}:{number}: expected destination<TAB>url')
        dest, url = parts[0].strip(), parts[1].strip()
        pure = PurePosixPath(dest)
        if pure.is_absolute() or '..' in pure.parts or dest.startswith('/'):
            raise ValueError(f'{path}:{number}: unsafe destination {dest!r}')
        if not url.startswith(('https://', 'http://', 'file://')):
            raise ValueError(f'{path}:{number}: unsupported URL {url!r}')
        if dest in seen:
            raise ValueError(f'{path}:{number}: duplicate destination {dest!r}')
        seen.add(dest)
        rows.append((dest, url))
    return rows


def sha256_file(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def download(url: str, target: Path, attempts: int = 3) -> tuple[str, int]:
    """Stream url to target; return (sha256, size)."""
    last = None
    for attempt in range(1, attempts + 1):
        try:
            req = request.Request(url, headers={'User-Agent': USER_AGENT})
            digest, size = hashlib.sha256(), 0
            with request.urlopen(req, timeout=60) as response, target.open('wb') as out:
                while chunk := response.read(CHUNK):
                    digest.update(chunk)
                    out.write(chunk)
                    size += len(chunk)
            if size == 0:
                raise OSError('empty response')
            return digest.hexdigest(), size
        except OSError as exc:      # URLError and HTTPError are OSErrors
            last = exc
            target.unlink(missing_ok=True)
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise OSError(f'{last}')


def fetch_one(dest_root: Path, dest: str, url: str, pinned: dict | None) -> tuple[str, str, dict | None]:
    """Return (status, message, lock entry)."""
    path = dest_root / dest
    if pinned and path.is_file() and path.stat().st_size == pinned['size'] and sha256_file(path) == pinned['sha256']:
        return 'cached', dest, pinned
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + '.part')
    try:
        sha, size = download(url, part)
    except OSError as exc:
        return 'failed', f'{dest}: {exc}', pinned
    if pinned and (sha != pinned['sha256'] or size != pinned['size']):
        part.unlink(missing_ok=True)
        return 'failed', f'{dest}: content differs from the pinned SHA-256; refused', pinned
    os.replace(part, path)
    return 'fetched', dest, {'url': url, 'sha256': sha, 'size': size}


def run(manifest: Path, dest_root: Path, lock_path: Path, required: bool, jobs: int) -> int:
    rows = read_manifest(manifest)
    lock = json.loads(lock_path.read_text(encoding='utf-8')) if lock_path.is_file() else {}
    dest_root.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        results = list(pool.map(lambda r: (r[0], fetch_one(dest_root, r[0], r[1], lock.get(r[0]))), rows))
    counts = {'fetched': 0, 'cached': 0, 'failed': 0}
    failures = []
    for dest, (status, message, entry) in results:
        counts[status] += 1
        if entry:
            lock[dest] = entry
        if status == 'failed':
            failures.append(message)
    tmp = lock_path.with_name(lock_path.name + '.tmp')
    tmp.write_text(json.dumps(lock, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(tmp, lock_path)
    present = sorted(d for d, _ in rows if d in lock and (dest_root / d).is_file())
    (dest_root / 'SHA256SUMS').write_text(''.join(f'{lock[d]["sha256"]}  {d}\n' for d in present), encoding='utf-8')
    for message in failures:
        print(f'  not available: {message}', file=sys.stderr)
    print(f'{len(rows)} files: {counts["fetched"]} downloaded, {counts["cached"]} already verified, '
          f'{counts["failed"]} unavailable')
    return 1 if failures and required else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--manifest', type=Path, required=True)
    ap.add_argument('--dest', type=Path, required=True)
    ap.add_argument('--lock', type=Path, required=True)
    ap.add_argument('--required', action='store_true', help='fail if any file cannot be fetched')
    ap.add_argument('--jobs', type=int, default=4)
    args = ap.parse_args(argv)
    try:
        return run(args.manifest, args.dest, args.lock, args.required, args.jobs)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f'FETCH FAILED: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
