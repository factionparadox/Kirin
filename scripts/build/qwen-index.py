#!/usr/bin/env python3
"""Build qwen-blobs.json from a real, pulled Ollama model directory.

Reads the Ollama manifest for the tag, hashes every referenced blob and
refuses to write an index if anything is missing or does not match.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

DEFAULT_TAG = 'qwen2.5-coder:7b-instruct'
DIGEST = re.compile(r'^sha256:([0-9a-f]{64})$')


def manifest_path(models: Path, tag: str) -> Path:
    name, _, version = tag.partition(':')
    if not name or not version or '/' in version or '..' in name:
        raise ValueError(f'unsupported model tag: {tag!r}')
    namespace = name if '/' in name else f'library/{name}'
    return models / 'manifests' / 'registry.ollama.ai' / namespace / version


def build_index(models: Path, tag: str) -> tuple[dict, list[str]]:
    manifest = json.loads(manifest_path(models, tag).read_text(encoding='utf-8'))
    layers = list(manifest.get('layers') or [])
    if manifest.get('config'):
        layers.append(manifest['config'])
    if not layers:
        raise ValueError('manifest lists no blobs')
    blobs, problems = [], []
    for layer in layers:
        match = DIGEST.match(str(layer.get('digest', '')))
        size = layer.get('size')
        if not match or type(size) is not int or size <= 0:
            problems.append(f'malformed manifest entry: {layer!r}')
            continue
        sha = match.group(1)
        path = models / 'blobs' / f'sha256-{sha}'
        if not path.is_file() or path.is_symlink():
            problems.append(f'blob missing: {sha}')
            continue
        if path.stat().st_size != size:
            problems.append(f'blob size mismatch: {sha}')
            continue
        with path.open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != sha:
                problems.append(f'blob checksum mismatch: {sha}')
                continue
        blobs.append({'sha256': sha, 'size': size, 'mediaType': layer.get('mediaType', '')})
    return {'model': tag, 'blobs': blobs}, problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--models', type=Path, required=True, help='OLLAMA_MODELS directory')
    ap.add_argument('--tag', default=DEFAULT_TAG)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        index, problems = build_index(args.models, args.tag)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f'INDEX FAILED: {exc}', file=sys.stderr)
        return 2
    for problem in problems:
        print(f'INDEX FAILED: {problem}', file=sys.stderr)
    if problems:
        return 1
    args.out.write_text(json.dumps(index, indent=2) + '\n', encoding='utf-8')
    total = sum(b['size'] for b in index['blobs'])
    print(f'{args.tag}: {len(index["blobs"])} verified blobs, {total / 1e9:.2f} GB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
