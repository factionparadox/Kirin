#!/usr/bin/env python3
"""Kirin Learn: offline lessons, safe command explanations, editor tutors and local coding help."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib import error, request

TOPIC_PATH = Path(os.environ.get('KIRIN_LESSONS_DIR', '/usr/share/kirin/learn/topics'))
MODEL = 'qwen2.5-coder:7b-instruct'
API = 'http://127.0.0.1:11434/api/chat'
EXPLANATIONS = {
    ('apt', 'update'): ('APT updates its local package indexes. It does not install newer versions.', 'apt(8), sources.list(5)'),
    ('apt', 'install'): ('APT resolves dependencies and installs specified packages; review the transaction before confirming.', 'apt(8)'),
    ('apt', 'upgrade'): ('APT upgrades installed packages according to configured repositories and package holds.', 'apt(8), apt_preferences(5)'),
    ('apt', 'full-upgrade'): ('APT may remove packages to complete a transition. Review removals and ZFS boot-environment availability.', 'apt(8)'),
    ('zpool', 'status'): ('Displays ZFS pool health and disk errors; reading status does not change the pool.', 'zpool-status(8)'),
    ('zfs', 'snapshot'): ('Creates a point-in-time ZFS snapshot. A snapshot is not automatically a bootable root environment.', 'zfs-snapshot(8)'),
    ('systemctl', 'status'): ('Displays a systemd unit status and recent logs, without changing its service state.', 'systemctl(1)'),
    ('vim',): ('Launches the Vim editor. Start learning via vimtutor, and exit Vim with :q.', 'vim(1), vimtutor(1)'),
    ('nvim',): ('Launches Neovim. Inside it, use :Tutor for its built-in interactive tutorial.', 'nvim(1), :help tutor'),
    ('man',): ('Opens local manual pages. Try man apt, man systemctl, or man zfs.', 'man(1)'),
}

def topics():
    if not TOPIC_PATH.is_dir():
        raise FileNotFoundError(f'Offline lesson directory missing: {TOPIC_PATH}')
    return sorted(TOPIC_PATH.glob('*.md'))

def list_topics():
    for p in topics():
        print(f'{p.stem:20} {p.read_text(encoding="utf-8").splitlines()[0].lstrip("# ")}')

def show(topic):
    candidate = next((p for p in topics() if p.stem == topic), None)
    if candidate is None:
        raise ValueError(f'Unknown topic: {topic!r}. Run kirin-learn topics.')
    print(candidate.read_text(encoding='utf-8'))

def browse():
    available = topics()
    if not sys.stdin.isatty():
        list_topics()
        return
    while True:
        print('\nKirin Learn — offline lessons\n')
        for i, p in enumerate(available, 1):
            print(f'{i}. {p.stem.replace("-", " ")}')
        choice = input('Lesson number (q to quit): ').strip()
        if choice.lower() in ('q', 'quit', ''):
            return
        if choice.isdecimal() and 1 <= int(choice) <= len(available):
            print('\n' + available[int(choice) - 1].read_text(encoding='utf-8'))
        else:
            print('Choose a displayed number.')

def explain(command):
    import shlex
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise ValueError(f'Cannot parse command: {exc}') from exc
    if not tokens:
        raise ValueError('Empty command')
    for prefix, (description, refs) in sorted(EXPLANATIONS.items(), key=lambda x: -len(x[0])):
        if tuple(tokens[:len(prefix)]) == prefix:
            print(f'{command}\n\n{description}\nRead further: {refs}\n')
            print('Explanation only. Kirin did not execute this command.')
            return
    print('No vetted explanation is installed for this command. Use local man pages and inspect its arguments.')
    print('Kirin did not execute this command.')

def doctor():
    for name in ('vim', 'vimtutor', 'nvim', 'apt', 'zfs', 'zpool', 'ollama'):
        print(f'{name:10} {shutil.which(name) or "not found"}')
    print(f'offline lessons: {len(topics())}')
    print('This report is read-only and makes no configuration changes.')

def tutor(editor):
    if editor == 'vim':
        command = ['vimtutor']
    else:
        command = ['nvim', '-c', 'Tutor kirin-01-basics']
    if not shutil.which(command[0]):
        raise FileNotFoundError(f'{command[0]} unavailable; install the editor packages')
    return subprocess.call(command)

def ask_code(question):
    payload = json.dumps({'model': MODEL, 'stream': False, 'messages': [
        {'role': 'system', 'content': 'Act as a programming tutor. Explain tradeoffs, show reasoning in educational steps, and never claim code was executed.'},
        {'role': 'user', 'content': question},
    ]}).encode('utf-8')
    req = request.Request(API, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with request.urlopen(req, timeout=120) as response:
            data = json.load(response)
    except (error.URLError, TimeoutError) as exc:
        raise RuntimeError(f'Local Ollama unavailable at {API}: {exc}') from exc
    answer = data.get('message', {}).get('content')
    if not isinstance(answer, str):
        raise RuntimeError('Ollama returned no text response')
    print(answer)
    print('\nAI-generated guidance. Verify any suggested commands before running them.')

def main(argv=None):
    parser = argparse.ArgumentParser(description='Kirin offline learning centre')
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('topics')
    sub.add_parser('browse')
    one = sub.add_parser('learn'); one.add_argument('topic')
    two = sub.add_parser('explain'); two.add_argument('command')
    sub.add_parser('doctor')
    three = sub.add_parser('tutor'); three.add_argument('editor', choices=('vim', 'neovim'))
    four = sub.add_parser('ask-code'); four.add_argument('question')
    args = parser.parse_args(argv)
    try:
        if args.action == 'topics': list_topics()
        elif args.action == 'browse': browse()
        elif args.action == 'learn': show(args.topic)
        elif args.action == 'explain': explain(args.command)
        elif args.action == 'doctor': doctor()
        elif args.action == 'tutor': return tutor(args.editor)
        elif args.action == 'ask-code': ask_code(args.question)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f'kirin-learn: {exc}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
