#!/usr/bin/env python3
"""Re-read a squashfs that ISO extraction cut short at a 4 GiB boundary.

Some ISOs (openKylin 3.0's among them) record files over 4 GiB with a size
that wraps at 2^32 in the ISO 9660 directory, so extraction yields only the
first (size mod 4 GiB) bytes. The file's own squashfs superblock still states
its true length, and ISO writers store file data contiguously, so the whole
file can be copied straight out of the ISO:

1. read the true length from the truncated copy's superblock;
2. check it is consistent with the wrapped size (true ≡ wrapped mod 2^32);
3. find the 2048-byte sector where the file starts, by matching its first MiB;
4. copy the full length, proving the copy matches every byte already extracted.

Read-only on the ISO. Replaces the truncated file only once the copy is proven.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import struct
import sys

SECTOR = 2048
MAGIC = b'hsqs'
PROBE = 1 << 20
CHUNK = 16 << 20
WRAP = 1 << 32


def true_length(head: bytes, wrapped: int, wrap: int) -> int:
    if len(head) < 96 or head[:4] != MAGIC:
        raise ValueError('not a squashfs (no superblock at the start of the extracted file)')
    used = struct.unpack_from('<Q', head, 40)[0]
    if used <= wrapped:
        return wrapped
    for candidate in ((used + 4095) // 4096 * 4096, used):
        if candidate % wrap == wrapped % wrap:
            return candidate
    raise ValueError(f'superblock length {used} is not consistent with the extracted size {wrapped}: '
                     'this is not a wrapped size, the ISO itself is probably damaged')


def find_offsets(iso: Path, probe: bytes):
    """Yield sector-aligned offsets in the ISO where `probe` starts."""
    with iso.open('rb') as handle:
        base, tail = 0, b''
        while True:
            chunk = handle.read(CHUNK)
            if not chunk:
                return
            data = tail + chunk
            start = base - len(tail)
            pos = data.find(MAGIC)
            while pos != -1:
                offset = start + pos
                if offset % SECTOR == 0:
                    if pos + len(probe) <= len(data):
                        if data[pos:pos + len(probe)] == probe:
                            yield offset
                    else:
                        here = handle.tell()
                        handle.seek(offset)
                        if handle.read(len(probe)) == probe:
                            yield offset
                        handle.seek(here)
                pos = data.find(MAGIC, pos + 1)
            tail = data[-(len(MAGIC) - 1):]
            base += len(chunk)


def copy_proven(iso: Path, offset: int, length: int, extracted: Path, part: Path) -> bool:
    """Copy `length` bytes from `offset`; True only if the start matches `extracted` exactly."""
    known = extracted.stat().st_size
    with iso.open('rb') as src, extracted.open('rb') as old, part.open('wb') as dst:
        src.seek(offset)
        done = 0
        while done < length:
            block = src.read(min(CHUNK, length - done))
            if not block:
                return False
            if done < known:
                overlap = block[:known - done]
                if old.read(len(overlap)) != overlap:
                    return False
            dst.write(block)
            done += len(block)
    return True


def recover(iso: Path, extracted: Path, wrap: int = WRAP) -> str:
    wrapped = extracted.stat().st_size
    with extracted.open('rb') as handle:
        head = handle.read(PROBE)
    length = true_length(head, wrapped, wrap)
    if length == wrapped:
        return 'already complete'
    probe = head[:min(len(head), wrapped)]
    part = extracted.with_name(extracted.name + '.part')
    try:
        for offset in find_offsets(iso, probe):
            if offset + length > iso.stat().st_size:
                continue
            if copy_proven(iso, offset, length, extracted, part):
                os.replace(part, extracted)
                return f'recovered {length} bytes from ISO offset {offset}'
        raise ValueError('could not locate the complete file inside the ISO')
    finally:
        part.unlink(missing_ok=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--iso', type=Path, required=True)
    ap.add_argument('--file', type=Path, required=True, help='the truncated, extracted squashfs')
    ap.add_argument('--wrap', type=int, default=WRAP, help=argparse.SUPPRESS)  # tests only
    args = ap.parse_args(argv)
    try:
        print(recover(args.iso, args.file, args.wrap))
        return 0
    except (OSError, ValueError, struct.error) as exc:
        print(f'RECOVERY FAILED: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
