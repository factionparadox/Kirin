#!/usr/bin/env python3
"""Pre-connect Alpaca (com.jeffser.Alpaca) to Kirin's system Ollama for new users.

Writes /etc/skel/.var/app/com.jeffser.Alpaca/data/alpaca.db in an offline image
root with one "Ollama (External)" instance at http://127.0.0.1:11434, so Alpaca
opens straight to a chat with Kirin's models instead of its setup guide. Only
the `instance` table is created; Alpaca creates the rest on first start.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
import uuid

DB = 'etc/skel/.var/app/com.jeffser.Alpaca/data/alpaca.db'


def seed(root: Path, model: str, name: str = 'Kirin (local)') -> Path:
    if not root.is_absolute() or root.resolve() == Path('/') or not root.is_dir():
        raise ValueError('requires an offline image root other than /')
    path = root / DB
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS instance (id TEXT NOT NULL PRIMARY KEY, pinned INTEGER NOT NULL, '
                   'type TEXT NOT NULL, properties TEXT NOT NULL)')
        db.execute('INSERT INTO instance (id, pinned, type, properties) VALUES (?, ?, ?, ?)',
                   (str(uuid.uuid4()), 1, 'ollama',
                    json.dumps({'name': name, 'url': 'http://127.0.0.1:11434', 'api': '',
                                'default_model': model, 'title_model': model})))
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--model', required=True, help='default chat model tag')
    args = ap.parse_args(argv)
    try:
        print(f'Alpaca pre-connected to Ollama: {seed(args.root, args.model).relative_to(args.root)}')
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f'ALPACA SEED FAILED: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
