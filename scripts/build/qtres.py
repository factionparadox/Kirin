#!/usr/bin/env python3
"""Read and replace Qt 5 resources (rcc format 2/3) compiled into an ELF program or
library, in place, without rebuilding it.

Qt keeps each compiled .qrc as three tables: a tree of entries, their names and the
file data, each blob stored as [u32 size][bytes] (or, when compressed, [u32 size]
[u32 unpacked size][zlib]). A replacement is written over the old blob: it must fit
in the old blob's space, the size field is updated, the rest is zeroed, and the
entry's compression flag is set to match. Nothing else in the file moves.

    qtres.py list FILE
    qtres.py extract FILE OUTDIR
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import struct
import sys
import zlib

ENTRY = 22            # rcc format 2+: 14 bytes plus an 8-byte modification time
COMPRESSED = 0x01     # zlib (qCompress)
COMPRESSED_ZSTD = 0x04
DIRECTORY = 0x02


@dataclass
class Resource:
    path: str
    entry: int        # file offset of the tree entry
    flags: int
    blob: int         # file offset of the [u32 size] field
    stored: int       # bytes after the size field now
    capacity: int     # bytes available after the size field (up to the next blob)


def qt_hash(name: str) -> int:
    h = 0
    for ch in name:
        h = ((h << 4) + ord(ch)) & 0xffffffff
        h ^= (h & 0xf0000000) >> 23
        h &= 0x0fffffff
    return h


def _name(buf: bytes, base: int, off: int) -> str | None:
    try:
        n, h = struct.unpack_from('>HI', buf, base + off)
        s = buf[base + off + 6: base + off + 6 + 2 * n].decode('utf-16-be')
    except (struct.error, UnicodeDecodeError):
        return None
    if n == 0 or h != qt_hash(s) or not s.isprintable() or '/' in s:
        return None
    return s


def _walk(buf: bytes, tree: int, i: int = 0, depth: int = 0):
    if depth > 32:
        raise ValueError('too deep')
    off = tree + i * ENTRY
    name_off, flags = struct.unpack_from('>IH', buf, off)
    if flags & DIRECTORY:
        count, first = struct.unpack_from('>II', buf, off + 6)
        if count > 5000:
            raise ValueError('too many children')
        yield i, name_off, flags, None, (count, first)
        for c in range(first, first + count):
            yield from _walk(buf, tree, c, depth + 1)
    else:
        (data_off,) = struct.unpack_from('>I', buf, off + 10)
        yield i, name_off, flags, data_off, None


# A name entry: u16 length, u32 hash (top nibble 0), then UTF-16BE text (ASCII here).
_NAME_ENTRY = re.compile(rb'(?=\x00[\x01-\xff][\x00-\x0f][\x00-\xff]{3}\x00[\x20-\x7e])', re.S)


def _names_base(buf: bytes, tree: int, offs: list[int], window: int = 0x400000):
    lo, hi = max(0, tree - window), min(len(buf), tree + window)
    for m in _NAME_ENTRY.finditer(buf, lo, hi):
        base = m.start() - offs[0]
        if base < 0 or _name(buf, base, offs[0]) is None:
            continue
        if all(_name(buf, base, o) is not None for o in offs[1:]):
            return base
    return None


def _fits(buf: bytes, base: int, offsets: list[int]):
    """(fits, exact, nonzero) for a candidate data table base."""
    exact = nonzero = 0
    for a, b in zip(offsets, offsets[1:]):
        if base + b + 4 > len(buf):
            return False, 0, 0
        (size,) = struct.unpack_from('>I', buf, base + a)
        if size + 4 > b - a:
            return False, 0, 0
        exact += size + 4 == b - a
        nonzero += size > 0
    (size,) = struct.unpack_from('>I', buf, base + offsets[-1])
    if base + offsets[-1] + 4 + size > len(buf):
        return False, 0, 0
    return True, exact, nonzero + (size > 0)


def _data_base(buf: bytes, offsets: list[int], after: int, near: int, window: int = 0x2000000):
    """Base of the data table: each blob must fit before the next one starts. rcc puts
    the table right after the names (checked first); a blob Kirin replaced may be
    shorter than its space, so an exact fit is only required in the wide search."""
    offsets = sorted(set(offsets))
    pairs = max(1, len(offsets) - 1)
    for base in range(after, after + 64):
        ok, exact, nonzero = _fits(buf, base, offsets)
        if ok and nonzero * 2 >= len(offsets):
            return base
    for base in range(max(0, near - window), min(len(buf), near + window)):
        ok, exact, _ = _fits(buf, base, offsets)
        if ok and exact * 2 >= pairs:
            return base
    return None


def tables(buf: bytes):
    """(tree, names, data, entries) for every rcc tree in buf."""
    pos = 0
    root = b'\x00\x00\x00\x00\x00\x02'
    while (pos := buf.find(root, pos)) >= 0:
        tree, pos = pos, pos + 1
        try:
            count, first = struct.unpack_from('>II', buf, tree + 6)
            if first != 1 or not 0 < count < 500:
                continue
            ents = list(_walk(buf, tree))
        except (struct.error, ValueError, RecursionError):
            continue
        files = [e for e in ents if e[3] is not None]
        if not files:
            continue
        names = _names_base(buf, tree, sorted({e[1] for e in ents[1:]}))
        if names is None:
            continue
        last = max({e[1] for e in ents[1:]})
        names_end = names + last + 6 + 2 * len(_name(buf, names, last))
        data = _data_base(buf, [e[3] for e in files], names_end, tree)
        if data is None:
            continue
        yield tree, names, data, ents
        pos = tree + len(ents) * ENTRY


def resources(buf: bytes) -> list[Resource]:
    """Every resource file in every rcc tree in buf."""
    found: list[Resource] = []
    for tree, names, data, ents in tables(buf):
        files = [e for e in ents if e[3] is not None]
        parent = {}
        for i, _, _, _, d in ents:
            if d:
                for c in range(d[1], d[1] + d[0]):
                    parent[c] = i
        label = {i: _name(buf, names, no) for i, no, *_ in ents if i}

        def path(i):
            parts = []
            while i:
                parts.append(label[i]); i = parent[i]
            return ':/' + '/'.join(reversed(parts))
        starts = sorted({e[3] for e in files})
        following = dict(zip(starts, starts[1:]))
        for i, _, flags, data_off, _ in files:
            blob = data + data_off
            (stored,) = struct.unpack_from('>I', buf, blob)
            capacity = following[data_off] - data_off - 4 if data_off in following else stored
            found.append(Resource(path(i), tree + i * ENTRY, flags, blob, stored, capacity))
    return found


def content(buf: bytes, r: Resource) -> bytes:
    raw = bytes(buf[r.blob + 4: r.blob + 4 + r.stored])
    if r.flags & COMPRESSED_ZSTD:
        raise ValueError(f'{r.path}: zstd-compressed resources are not supported')
    return zlib.decompress(raw[4:]) if r.flags & COMPRESSED else raw


def replace(buf: bytearray, r: Resource, new: bytes) -> None:
    """Write new over r in buf. Raises ValueError if it does not fit."""
    capacity = r.capacity
    if len(new) <= capacity:
        stored, flags = new, r.flags & ~(COMPRESSED | COMPRESSED_ZSTD)
    else:
        stored = struct.pack('>I', len(new)) + zlib.compress(new, 9)
        flags = (r.flags & ~COMPRESSED_ZSTD) | COMPRESSED
        if len(stored) > capacity:
            raise ValueError(f'{r.path}: replacement is {len(new)} bytes ({len(stored)} compressed); '
                             f'only {capacity} fit')
    buf[r.blob: r.blob + 4] = struct.pack('>I', len(stored))
    buf[r.blob + 4: r.blob + 4 + len(stored)] = stored
    buf[r.blob + 4 + len(stored): r.blob + 4 + capacity] = bytes(capacity - len(stored))
    struct.pack_into('>H', buf, r.entry + 4, flags)
    r.flags, r.stored = flags, len(stored)


def main(argv=None) -> int:
    import os
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2 or args[0] not in ('list', 'extract'):
        print(__doc__.split('\n\n')[-1], file=sys.stderr)
        return 2
    buf = open(args[1], 'rb').read()
    for r in resources(buf):
        if args[0] == 'list':
            print(f'{r.path}\t{r.stored}\t{"zlib" if r.flags & COMPRESSED else "raw"}')
        else:
            dest = os.path.join(args[2], r.path[2:])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'wb') as fh:
                fh.write(content(buf, r))
    return 0


if __name__ == '__main__':
    sys.exit(main())
