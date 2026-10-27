#!/usr/bin/env python3
"""Fail-closed offline checks for Kirin image staging. Does not build an ISO."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

MODEL_TAG = 'qwen2.5-coder:7b-instruct'

def verify_models_removed(inventory_file: Path, owners_file: Path | None, kept_file: Path | None,
                          candidate_root: Path) -> tuple[list[str], list[str]]:
    """openKylin's AI models must be gone, except those inside an application Kirin keeps."""
    inventory = json.loads(inventory_file.read_text(encoding='utf-8'))
    if not isinstance(inventory, dict):
        raise ValueError('the upstream AI inventory must be a JSON object')
    owners = json.loads(owners_file.read_text(encoding='utf-8')) if owners_file and owners_file.is_file() else {}
    kept = set(kept_file.read_text(encoding='utf-8').split()) if kept_file and kept_file.is_file() else set()
    problems, notes = [], []
    for relative in inventory:
        rel = Path(relative)
        if not isinstance(relative, str) or not relative or rel.is_absolute() or '..' in rel.parts:
            problems.append(f'invalid upstream path: {relative!r}')
            continue
        if not (candidate_root / rel).exists():
            continue
        owner = (owners.get(relative) or {}).get('package', '')
        if owner and owner in kept:
            notes.append(f'kept inside {owner}: {relative}')
        else:
            problems.append(f'openKylin AI model still present: {relative}' + (f' ({owner})' if owner else ''))
    return problems, notes

def verify_qwen(model_index: Path, blobs_root: Path) -> list[str]:
    entry = json.loads(model_index.read_text(encoding='utf-8'))
    if entry.get('model') != MODEL_TAG:
        return [f'coding model must be {MODEL_TAG}']
    if not entry.get('blobs') or not isinstance(entry['blobs'], list):
        return ['coding-model blob inventory is missing']
    problems = []
    total_size = sum(b.get('size', 0) for b in entry['blobs'] if isinstance(b, dict) and type(b.get('size')) is int and b['size'] > 0)
    if total_size < 4_000_000_000:
        problems.append('Qwen2.5-Coder 7B payload under 4 GB: image is incomplete')
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
    p.add_argument('--owners', type=Path, help='path -> package report from inventory-models.py')
    p.add_argument('--kept', type=Path, help='packages kept because a model is part of an application')
    p.add_argument('--candidate-root', type=Path, required=True)
    p.add_argument('--qwen-index', type=Path, help='coding model blob index (only when models are bundled)')
    p.add_argument('--qwen-blobs', type=Path)
    args = p.parse_args(argv)
    try:
        problems, notes = verify_models_removed(args.upstream_inventory, args.owners, args.kept, args.candidate_root)
        if args.qwen_index:
            problems += verify_qwen(args.qwen_index, args.qwen_blobs)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f'IMAGE REJECTED: {exc}', file=sys.stderr)
        return 1
    for item in notes:
        print(item)
    for item in problems:
        print(f'IMAGE REJECTED: {item}', file=sys.stderr)
    if problems: return 1
    print("AI payload audit passed: openKylin's models removed"
          + ('; coding model complete' if args.qwen_index else '; AI models are downloaded after install (kirin-content)'))
    return 0

if __name__ == '__main__':
    sys.exit(main())
