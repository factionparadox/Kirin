#!/usr/bin/env python3
"""Kirin Learn: offline lessons, safe command explanations, editor tutors, local coding help and Russian study."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from urllib import error, request

TOPIC_PATH = Path(os.environ.get('KIRIN_LESSONS_DIR', '/usr/share/kirin/learn/topics'))
MODEL = 'qwen2.5-coder:7b-instruct'
API = 'http://127.0.0.1:11434/api/chat'
RUSSIAN_CONFIG = Path(os.environ.get('KIRIN_RUSSIAN_CONFIG', '/usr/share/kirin/russian.json'))
RUSSIAN_DEFAULTS = {
    'model': 'qwen3:30b-a3b-instruct-2507-q4_K_M',
    'piper': '/opt/kirin/piper/piper',
    'voices': '/opt/kirin/russian/voices',
    'library': '/opt/kirin/russian/library',
    'dictionary': '',
}
VOICES = ('irina', 'denis', 'dmitri', 'ruslan')
LEVELS = ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')
PLAYERS = (['pw-play'], ['paplay'], ['aplay', '-q'])
TUTOR_PROMPT = '''You are a patient Russian tutor for a British English speaker at CEFR level {level}.
- If the learner writes Russian: list each mistake, give the corrected sentence, and explain every
  correction briefly in British English (name the case, aspect or agreement rule involved).
- If the learner writes English or asks a question: answer in English and give the Russian with
  stress marks (e.g. молоко́), and a short grammar note where it helps.
- Mark stress with an acute accent on Russian words you teach. Keep Russian at level {level}.
- End with one short question in Russian, suited to level {level}, to keep the conversation going.
- Be honest: if you are not sure about a stress, ending or usage, say so and suggest checking the
  Wiktionary dictionary or the FSI Russian course in the Kirin library. Never invent sources.'''
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

def russian_config():
    config = dict(RUSSIAN_DEFAULTS)
    if RUSSIAN_CONFIG.is_file():
        config.update(json.loads(RUSSIAN_CONFIG.read_text(encoding='utf-8')))
    return config


def chat(model, messages, stream_to=None):
    """Send a chat to the local Ollama; stream tokens to `stream_to` if given. Returns the reply."""
    payload = json.dumps({'model': model, 'stream': stream_to is not None, 'messages': messages}).encode('utf-8')
    req = request.Request(API, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with request.urlopen(req, timeout=600) as response:
            if stream_to is None:
                answer = json.load(response).get('message', {}).get('content')
            else:
                parts = []
                for line in response:
                    if not line.strip():
                        continue
                    piece = json.loads(line).get('message', {}).get('content', '')
                    parts.append(piece)
                    stream_to.write(piece)
                    stream_to.flush()
                stream_to.write('\n')
                answer = ''.join(parts)
    except (error.URLError, TimeoutError) as exc:
        raise RuntimeError(f'Local Ollama unavailable at {API}: {exc}. Is the ollama service running?') from exc
    if not isinstance(answer, str) or not answer:
        raise RuntimeError('Ollama returned no text response')
    return answer


def russian(text, level='A1'):
    """One question to the Russian tutor, or an interactive lesson when text is empty."""
    config = russian_config()
    messages = [{'role': 'system', 'content': TUTOR_PROMPT.format(level=level)}]
    if text:
        messages.append({'role': 'user', 'content': text})
        chat(config['model'], messages, sys.stdout)
        print('\nAI tutor: a practice partner that can be wrong. Check stress and endings in the dictionary.')
        return
    print(f'Kirin Russian tutor (level {level}). Write in Russian or English.')
    print('Commands: /say TEXT speaks Russian aloud, /level B1 changes level, /quit ends.\n')
    while True:
        try:
            line = input('you> ').strip()
        except EOFError:
            print()
            return
        if not line:
            continue
        if line in ('/quit', '/q', '/exit'):
            return
        if line.startswith('/say '):
            try:
                say(line[5:])
            except (FileNotFoundError, RuntimeError) as exc:
                print(f'kirin-learn: {exc}', file=sys.stderr)
            continue
        if line.startswith('/level '):
            new = line[7:].strip().upper()
            if new in LEVELS:
                level = new
                messages[0] = {'role': 'system', 'content': TUTOR_PROMPT.format(level=level)}
                print(f'Level set to {level}.')
            else:
                print(f'Choose one of: {", ".join(LEVELS)}')
            continue
        messages.append({'role': 'user', 'content': line})
        print('tutor> ', end='', flush=True)
        messages.append({'role': 'assistant', 'content': chat(config['model'], messages, sys.stdout)})


def strip_stress(text):
    """Remove combining stress accents, which the speech engine may misread."""
    return unicodedata.normalize('NFC', ''.join(c for c in unicodedata.normalize('NFD', text)
                                                if c not in ('\u0301', '\u0300')))


def say(text, voice='irina', output=None):
    """Speak Russian text with Piper; write a WAV to `output` instead of playing it, if given."""
    config = russian_config()
    piper = Path(config['piper'])
    model = Path(config['voices']) / f'ru_RU-{voice}-medium.onnx'
    if voice not in VOICES:
        raise ValueError(f'Unknown voice {voice!r}; choose {", ".join(VOICES)}')
    if not piper.is_file():
        raise FileNotFoundError(f'Piper speech engine not installed at {piper}')
    if not model.is_file():
        raise FileNotFoundError(f'Russian voice not installed: {model}')
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(output) if output else Path(tmp) / 'speech.wav'
        result = subprocess.run([str(piper), '--model', str(model), '--output_file', str(wav)],
                                input=strip_stress(text).encode('utf-8'), capture_output=True)
        if result.returncode != 0 or not wav.is_file():
            raise RuntimeError('Piper could not synthesise speech: ' + result.stderr.decode('utf-8', 'replace')[-300:])
        if output:
            print(f'Saved {wav}')
            return 0
        for player in PLAYERS:
            if shutil.which(player[0]):
                return subprocess.call(player + [str(wav)])
        raise FileNotFoundError('No audio player found (pw-play, paplay or aplay); use --output FILE.wav')


def library(open_folder=False):
    root = Path(russian_config()['library'])
    if not root.is_dir():
        raise FileNotFoundError(f'Russian course library not installed at {root}')
    if open_folder:
        return subprocess.call(['xdg-open', str(root)])
    print(f'Russian course library: {root}\n')
    for course in sorted(p for p in root.iterdir() if p.is_dir()):
        pdfs = sum(1 for _ in course.rglob('*.pdf'))
        audio = sum(1 for _ in course.rglob('*.mp3'))
        print(f'  {course.name:32} {pdfs:3} books/workbooks  {audio:3} audio tracks')
    print('\nStart with: FSI Russian/FAST/FsiRussianFast-Lessons1-5.pdf with FSI Russian FAST - Tape 1.mp3.')
    print('Open the folder: kirin-learn library --open')
    return 0


def dictionary():
    zim = russian_config().get('dictionary')
    if not zim or not Path(zim).is_file():
        raise FileNotFoundError('Wiktionary dictionary not installed')
    return subprocess.call(['flatpak', 'run', 'org.kiwix.desktop', zim])


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
    ru = sub.add_parser('russian', help='AI Russian tutor (no text: interactive lesson)')
    ru.add_argument('text', nargs='?', default='')
    ru.add_argument('--level', choices=LEVELS, default='A1')
    speak = sub.add_parser('say', help='speak Russian text aloud')
    speak.add_argument('text')
    speak.add_argument('--voice', choices=VOICES, default='irina')
    speak.add_argument('--output', help='save a WAV file instead of playing')
    lib = sub.add_parser('library', help='list the Russian course library')
    lib.add_argument('--open', action='store_true', help='open it in the file manager')
    sub.add_parser('dictionary', help='open the offline Wiktionary')
    args = parser.parse_args(argv)
    try:
        if args.action == 'topics': list_topics()
        elif args.action == 'browse': browse()
        elif args.action == 'learn': show(args.topic)
        elif args.action == 'explain': explain(args.command)
        elif args.action == 'doctor': doctor()
        elif args.action == 'tutor': return tutor(args.editor)
        elif args.action == 'ask-code': ask_code(args.question)
        elif args.action == 'russian': russian(args.text, args.level)
        elif args.action == 'say': return say(args.text, args.voice, args.output)
        elif args.action == 'library': return library(args.open)
        elif args.action == 'dictionary': return dictionary()
    except (ValueError, FileNotFoundError, RuntimeError, json.JSONDecodeError) as exc:
        print(f'kirin-learn: {exc}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
