#!/usr/bin/env python3
"""Find candidate upstream AI model files in an unpacked openKylin root.

Read-only. Produces the explicit SHA-256 inventory that
scripts/check-image-contract.py expects, plus a separate ownership report.
The result is a *candidate* list: a person must review it before the build
continues (docs/IMAGE-BUILD.md: "do not guess their location").
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

# Formats that are almost always model weights or tokenisers.
STRONG_SUFFIXES = frozenset({
    '.gguf', '.ggml', '.onnx', '.ort', '.safetensors', '.pth', '.ckpt',
    '.tflite', '.mnn', '.rknn', '.tiktoken', '.mlmodel',
})
# Ambiguous formats: only counted when the path also looks AI-related.
# (.pt and .nb are also language codes, e.g. Vim's tutor1.pt and tutor1.nb.)
WEAK_SUFFIXES = frozenset({'.bin', '.model', '.param', '.pb', '.h5', '.vocab', '.dat', '.npz', '.npy',
                           '.pt', '.nb', '.om'})
SHARED_LIBRARY = re.compile(r'\.so(?:\.\d+)*$')
KEYWORDS = frozenset({
    'ai', 'llm', 'model', 'models', 'asr', 'tts', 'ocr', 'nlp', 'vision', 'embedding',
    'embeddings', 'tokenizer', 'qwen', 'kylinbot', 'intelligence', 'intelligent',
    'genai', 'aisdk', 'inference', 'neural', 'weights', 'bert', 'whisper', 'paddle',
    'ncnn', 'onnxruntime', 'llama', 'gesture', 'voice', 'speech',
})
TOKEN_SPLIT = re.compile(r'[/._\-\s]+')
SKIP_TOP = frozenset({'proc', 'sys', 'dev', 'run', 'tmp', 'home', 'root', 'boot', 'media', 'mnt', 'lost+found'})
SKIP_PREFIXES = (
    'var/cache', 'var/tmp', 'var/log', 'var/lib/apt', 'var/lib/dpkg',
    'usr/lib/firmware', 'lib/firmware', 'usr/lib/modules', 'lib/modules', 'usr/src',
    'usr/share/ollama', 'var/lib/flatpak', 'kirin-build',
)
WEAK_MIN = 1 << 20          # 1 MiB
STRONG_MIN = 4 << 10        # 4 KiB
LARGE_MIN = 256 << 20       # 256 MiB


def tokens(rel: str) -> set[str]:
    return {t.lower() for t in TOKEN_SPLIT.split(rel) if t}


def is_candidate(rel: str, size: int) -> bool:
    suffix = os.path.splitext(rel)[1].lower()
    ai_path = bool(tokens(rel) & KEYWORDS)
    if suffix in STRONG_SUFFIXES and size >= STRONG_MIN:
        return True
    if suffix in WEAK_SUFFIXES and size >= WEAK_MIN and ai_path:
        return True
    # Big files under an AI path count too, except libraries such as libtorch_cpu.so.
    return size >= LARGE_MIN and ai_path and not SHARED_LIBRARY.search(rel)


def check_root(root: Path) -> Path:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir() or root.resolve() == Path('/'):
        raise ValueError('requires an unpacked image root other than /')
    return root


def scan(root: Path, exclude: tuple[str, ...] = ()) -> list[tuple[str, int]]:
    found = []
    for current, dirs, files in os.walk(root, followlinks=False):
        rel_dir = os.path.relpath(current, root)
        rel_dir = '' if rel_dir == '.' else rel_dir
        keep = []
        for d in dirs:
            rel = f'{rel_dir}/{d}' if rel_dir else d
            if (not rel_dir and d in SKIP_TOP) or rel.startswith(SKIP_PREFIXES) or (rel + '/').startswith(exclude):
                continue
            if os.path.islink(os.path.join(current, d)):
                continue
            keep.append(d)
        dirs[:] = sorted(keep)
        for name in sorted(files):
            path = os.path.join(current, name)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            rel = f'{rel_dir}/{name}' if rel_dir else name
            if rel.startswith(exclude):
                continue
            size = os.path.getsize(path)
            if is_candidate(rel, size):
                found.append((rel, size))
    return found


def owners(root: Path) -> dict[str, str]:
    info = root / 'var/lib/dpkg/info'
    result: dict[str, str] = {}
    if not info.is_dir():
        return result
    for listing in sorted(info.glob('*.list')):
        package = listing.stem.split(':')[0]
        for line in listing.read_text(encoding='utf-8', errors='replace').splitlines():
            if line.startswith('/'):
                result.setdefault(line.lstrip('/'), package)
                # merged-/usr: dpkg may list /lib/x while the file lives at usr/lib/x
                if not line.startswith('/usr/'):
                    result.setdefault('usr' + line, package)
    return result


def digest(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--out', type=Path, help='write {path: sha256} inventory here')
    ap.add_argument('--owners-out', type=Path, required=True, help='write path → package/size report here')
    ap.add_argument('--exclude-file', type=Path,
                    help='file of path prefixes (one per line, # comments) to leave out, e.g. apps Kirin removes')
    ap.add_argument('--inventory', type=Path,
                    help='use this reviewed inventory instead of scanning; only write the ownership report')
    args = ap.parse_args(argv)
    try:
        root = check_root(args.root)
        exclude = ()
        if args.exclude_file:
            exclude = tuple(l.strip().lstrip('/') for l in args.exclude_file.read_text(encoding='utf-8').splitlines()
                            if l.strip() and not l.lstrip().startswith('#'))
        if args.inventory:
            reviewed = json.loads(args.inventory.read_text(encoding='utf-8'))
            if not isinstance(reviewed, dict) or not reviewed:
                raise ValueError('reviewed inventory must be a non-empty {path: sha256} object')
            entries = [(rel, (root / rel).stat().st_size) for rel in sorted(reviewed)]
            inventory = reviewed
        else:
            if not args.out:
                raise ValueError('--out is required when scanning')
            entries = scan(root, exclude)
            inventory = {rel: digest(root / rel) for rel, _ in entries}
        owned = owners(root)
        report = {rel: {'size': size, 'package': owned.get(rel)} for rel, size in entries}
        if not args.inventory:
            args.out.write_text(json.dumps(inventory, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        args.owners_out.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f'INVENTORY FAILED: {exc}', file=sys.stderr)
        return 2
    total = sum(size for _, size in entries)
    for rel, size in entries:
        print(f'{size:>14,}  {report[rel]["package"] or "(no package)":<32} {rel}')
    print(f'{len(entries)} candidate model files, {total / 1e9:.2f} GB')
    if not entries:
        print('No candidates found. Inspect the image by hand and pass a reviewed inventory.', file=sys.stderr)
        return 3
    return 0


if __name__ == '__main__':
    sys.exit(main())
