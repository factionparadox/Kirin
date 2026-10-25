#!/usr/bin/env python3
"""Fail-closed offline checks for Kirin image staging. Does not build an ISO."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

MODEL_TAG = 'qwen2.5-coder:7b-instruct'

def verify_existing_models(inventory_file: Path, candidate_root: Path) -> list[str]:
    inventory = json.loads(inventory_file.read_text(encoding='utf-8'))
    if not isinstance(inventory, dict) or not inventory:
        raise ValueError('An explicit non-empty upstream AI inventory is required')
    problems = []
    for relative, expected in inventory.items():
        rel = Path(relative)
        if not isinstance(relative, str) or not relative or rel.is_absolute() or '..' in rel.parts:
            problems.append(f'invalid upstream path: {relative!r}')
            continue
        if not isinstance(expected, str) or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
            problems.append(f'invalid SHA-256 for: {relative}')
            continue
        candidate = candidate_root / rel
        if not candidate.is_file() or candidate.is_symlink():
            problems.append(f'upstream model file missing or symlinked: {relative}')
            continue
        with candidate.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        if digest != expected:
            problems.append(f'upstream model changed: {relative}')
    return problems

def verify_qwen(model_index: Path, blobs_root: Path) -> list[str]:
    entry = json.loads(model_index.read_text(encoding='utf-8'))
    if entry.get('model') != MODEL_TAG:
        return [f'coding model must be {MODEL_TAG}']
    if not entry.get('blobs') or not isinstance(entry['blobs'], list):
        return ['coding-model blob inventory is missing']
    problems = []
    for blob in entry['blobs']:
        sha = blob.get('sha256') if isinstance(blob, dict) else None
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
            problems.append('invalid blob SHA-256'); continue
        expected_size = blob.get('size')
        if not isinstance(expected_size, int) or expected_size <= 0:
            problems.append(f'invalid blob size: {sha}'); continue
        path = blobs_root / ('sha256-' + sha)
        if not path.is_file() or path.is_symlink():
            problems.append(f'Qwen blob missing: {sha}'); continue
        if path.stat().st_size != expected_size:
            problems.append(f'Qwen blob size mismatch: {sha}'); continue
        with path.open('rb') as handle:
            actual = hashlib.file_digest(handle, 'sha256').hexdigest()
        if actual != sha:
            problems.append(f'Qwen blob checksum mismatch: {sha}')
    return problems

def main(argv=None):
    p = argparse.ArgumentParser(description='Validate staged Kirin image model payloads')
    p.add_argument('--upstream-inventory', type=Path, required=True)
    p.add_argument('--candidate-root', type=Path, required=True)
    p.add_argument('--qwen-index', type=Path, required=True)
    p.add_argument('--qwen-blobs', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        problems = verify_existing_models(args.upstream_inventory, args.candidate_root)
        problems += verify_qwen(args.qwen_index, args.qwen_blobs)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f'IMAGE REJECTED: {exc}', file=sys.stderr)
        return 1
    for item in problems:
        print(f'IMAGE REJECTED: {item}', file=sys.stderr)
    if problems: return 1
    print('AI payload audit passed: upstream inventory unchanged; coding blobs complete')
    return 0

if __name__ == '__main__':
    sys.exit(main())
