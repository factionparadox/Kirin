"""Build a fake program holding a Qt 5 resource tree (rcc format 2) and C strings,
laid out like openKylin's installer programs: code-ish bytes, tree, names, data."""
import os
import struct


def qt_hash(name: str) -> int:
    h = 0
    for ch in name:
        h = ((h << 4) + ord(ch)) & 0xffffffff
        h ^= (h & 0xf0000000) >> 23
        h &= 0x0fffffff
    return h


def make_program(files: dict, strings=(), compress=()) -> bytes:
    """files: {':/dir/sub/name': bytes}; compress: paths stored zlib-compressed."""
    import zlib
    root: dict = {}
    for path, data in files.items():
        node = root
        parts = path[2:].split('/')
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = (path, data)
    names, name_off = bytearray(), {}

    def name(n):
        if n not in name_off:
            name_off[n] = len(names)
            names.extend(struct.pack('>HI', len(n), qt_hash(n)) + n.encode('utf-16-be'))
        return name_off[n]
    entries = [None]           # breadth-first, children sorted by hash as rcc does
    data = bytearray()
    queue = [(0, root)]
    entries[0] = ('dir', 0, root)
    while queue:
        idx, node = queue.pop(0)
        kids = sorted(node.items(), key=lambda kv: qt_hash(kv[0]))
        first = len(entries)
        for k, v in kids:
            entries.append(('dir', name(k), v) if isinstance(v, dict) else ('file', name(k), v))
        entries[idx] = entries[idx] + (len(kids), first)
        for j, (k, v) in enumerate(kids):
            if isinstance(v, dict):
                queue.append((first + j, v))
    tree = bytearray()
    for e in entries:
        if e[0] == 'dir':
            tree += struct.pack('>IHII', e[1], 2, e[3], e[4]) + bytes(8)
        else:
            path, blob = e[2]
            flags = 0
            if path in compress:
                blob = struct.pack('>I', len(blob)) + zlib.compress(blob); flags = 1
            tree += struct.pack('>IHHHI', e[1], flags, 0, 1, len(data)) + bytes(8)   # any country, QLocale::C
            data += struct.pack('>I', len(blob)) + blob
    text = b''.join(s.encode() + b'\0' * (8 - len(s.encode()) % 8 or 8) for s in strings)
    head = b'\x7fELF' + os.urandom(4096)
    return head + b'\0' * 8 + text + b'\0' * 16 + bytes(tree) + bytes(names) + bytes(data) + os.urandom(256)


def fake_installer_programs(root, spec: dict, assets) -> None:
    """Write openKylin-like installer programs under root holding every resource and
    string Kirin's branding spec replaces, with room for Kirin's files."""
    from pathlib import Path
    root, assets = Path(root), Path(assets)
    for rel in set(spec['resources']) | set(spec['strings']):
        files = {}
        for rpath, src in spec['resources'].get(rel, {}).items():
            if src.startswith('resource:'):
                files[src[len('resource:'):]] = b'generic picture ' * 200
                files[rpath] = b'openKylin picture ' * 200
            else:
                files[rpath] = b'openKylin ' * ((assets / src).stat().st_size // 10 + 8)
        files.setdefault(':/data/qss/main.css', b'QLabel { color: white; }')
        strings = ['unrelated text'] + [old for old, _ in spec['strings'].get(rel, [])]
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(make_program(files, strings))
        path.chmod(0o755)
