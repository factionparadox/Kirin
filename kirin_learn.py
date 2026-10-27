#!/usr/bin/env python3
"""Kirin Learn: offline lessons, safe command explanations, editor tutors, local coding help and Russian study."""
from __future__ import annotations
import argparse
import datetime
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
    'vocab': '/usr/share/kirin/russian/vocab.tsv',
    'audiobooks': '/opt/kirin/russian/audiobooks',
    'mezhdunami': '/opt/kirin/russian/mezhdunami',
    'kiwix': {},
}
VOCAB_STATE = Path(os.environ.get('KIRIN_VOCAB_STATE',
                                  Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'kirin-learn/vocab.json'))
VOCAB_LEVELS = ('A1', 'A2', 'B1', 'B2')
BOX_DAYS = (0, 1, 2, 4, 8, 16, 32, 64)     # Leitner boxes 1-7; box 5+ counts as mastered
STUDY_PATH = [
    ('A1', 'Survival Russian: the alphabet, sounds, greetings, present tense, the nominative and prepositional.', [
        'Между нами Units 1-5 with its audio: kirin-learn read mezhdunami',
        'FSI Russian FAST Lessons 1-5 with Tapes 1-3 (library: FSI Russian/FAST)',
        'Words: kirin-learn vocab --level A1 (780 words)',
        'Listen: Afanasyev fairy tales and Aesop (kirin-learn listen --level A2), with the text on Wikisource',
        'Speak and write: kirin-learn russian --level A1']),
    ('A2', 'Everyday Russian: past and future, aspect basics, all six cases in the singular, motion verbs.', [
        'Между нами Units 6-9 and the epilogue; its workbooks (library: Mezhdu nami)',
        'FSI Russian FAST Lessons 6-11 with Tapes 4-8; Peace Corps Russian course',
        'Words: kirin-learn vocab --level A2 (+520 words)',
        'Listen: fairy tales, fables, Garshin and the children\'s stories (kirin-learn listen --level A2)',
        'Speak and write: kirin-learn russian --level A2']),
    ('B1', 'Independent Russian: plurals of every case, aspect in depth, participles to recognise, opinions.', [
        'DLI Russian Basic Course volumes, Reader Vol II and dialogue guides (library: DLI Russian Basic Course (ERIC))',
        'Peace Corps Kyrgyzstan and Turkmenistan lessons; FSI Active Introduction for review',
        'Words: kirin-learn vocab --level B1 (+1,000 words)',
        'Listen and read: Pushkin, Tolstoy\'s Childhood, Chekhov (kirin-learn listen --level B1), text on Wikisource',
        'Speak and write: kirin-learn russian --level B1; ask it for short essays to correct']),
    ('B2', 'Confident Russian: participles and gerunds, complex sentences, register, reading anything.', [
        'Read a Russian Wikipedia article a day: kirin-learn read wikipedia',
        'Look words up in Russian, not English: kirin-learn read wiktionary-ru',
        'Literature: Turgenev, Goncharov, Dostoevsky, Griboedov, Eugene Onegin (kirin-learn listen --level B2)',
        'Words: kirin-learn vocab --level B2 (+7,700 words)',
        'Speak and write: kirin-learn russian --level B2; discuss what you read'])]
KIWIX_NAMES = {'wiktionary': 'English Wiktionary', 'wiktionary-ru': 'Russian Wiktionary (Викисловарь)',
               'wikisource': 'Russian Wikisource (Викитека): literature', 'wikipedia': 'Russian Wikipedia'}
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
    except error.HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError(f'The coding model {MODEL} is not downloaded yet: sudo kirin-content install ai-coder') from exc
        raise RuntimeError(f'Local Ollama error {exc.code}: {exc.reason}') from exc
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
    except error.HTTPError as exc:
        if exc.code == 404:
            pack = 'ai-tutor' if model.startswith('qwen3') else 'ai-coder'
            raise RuntimeError(f'The AI model {model} is not downloaded yet: sudo kirin-content install {pack}') from exc
        raise RuntimeError(f'Local Ollama error {exc.code}: {exc.reason}') from exc
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
        raise FileNotFoundError('Russian course library not downloaded yet: sudo kirin-content install ru-course')
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
        raise FileNotFoundError('Dictionaries not downloaded yet: sudo kirin-content install ru-dictionaries')
    return subprocess.call(['flatpak', 'run', 'org.kiwix.desktop', zim])


def plain_ru(text):
    """Compare Russian loosely: no stress marks, ё as е, case-insensitive."""
    return strip_stress(text).replace('ё', 'е').replace('Ё', 'Е').strip().lower()


def load_vocab(path=None):
    path = Path(path or russian_config()['vocab'])
    if not path.is_file():
        raise FileNotFoundError(f'Russian word list not installed at {path}')
    words = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        rank, level, kind, word, english, *note = line.split('\t')
        words.append({'rank': int(rank), 'level': level, 'kind': kind, 'word': word,
                      'english': english, 'note': note[0] if note else '', 'key': f'{word}|{kind}'})
    return words


def load_state():
    try:
        return json.loads(VOCAB_STATE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_state(state):
    VOCAB_STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = VOCAB_STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(tmp, VOCAB_STATE)


def grade(card, knew, today):
    box = min(card.get('box', 0) + 1, len(BOX_DAYS) - 1) if knew else 1
    card.update(box=box, seen=card.get('seen', 0) + 1,
                due=(today + datetime.timedelta(days=BOX_DAYS[box])).isoformat())
    return card


def pick_cards(words, state, level, new, today, max_due=100):
    allowed = VOCAB_LEVELS[:VOCAB_LEVELS.index(level) + 1]
    due = [w for w in words if w['key'] in state and state[w['key']].get('due', '') <= today.isoformat()]
    due.sort(key=lambda w: (state[w['key']]['due'], w['rank']))
    fresh = [w for w in words if w['key'] not in state and w['level'] in allowed][:new]
    return due[:max_due], fresh


def vocab_stats(words, state):
    out = {}
    for lvl in VOCAB_LEVELS:
        mine = [w for w in words if w['level'] == lvl]
        boxes = [state.get(w['key'], {}).get('box', 0) for w in mine]
        out[lvl] = {'total': len(mine), 'started': sum(b > 0 for b in boxes),
                    'learned': sum(b >= 3 for b in boxes), 'mastered': sum(b >= 5 for b in boxes)}
    return out


def vocab(level=None, new=10, reverse=False, speak=False, stats=False, ask=input, today=None):
    """Spaced-repetition word drill (Leitner boxes). Progress lives in VOCAB_STATE."""
    words, state = load_vocab(), load_state()
    today = today or datetime.date.today()
    counts = vocab_stats(words, state)
    if stats:
        for lvl, c in counts.items():
            print(f'{lvl}: {c["mastered"]:5}/{c["total"]} mastered, {c["learned"]} learned, {c["started"]} started')
        return 0
    if level is None:
        level = next((l for l in VOCAB_LEVELS if counts[l]['started'] < counts[l]['total']), 'B2')
    due, fresh = pick_cards(words, state, level, new, today)
    if not due and not fresh:
        print(f'Nothing due today and no new {level} words left. Try a higher --level.')
        return 0
    print(f'Kirin words, level {level}: {len(due)} to review, {len(fresh)} new. '
          + ('Type the Russian.' if reverse else 'Say what it means, then press Enter to check.')
          + ' q quits.\n')
    done = 0
    for w in due + fresh:
        card = dict(state.get(w['key'], {}))
        tag = 'new ' if card.get('seen', 0) == 0 else ''
        note = f'  ({w["note"]})' if w['note'] else ''
        if reverse:
            answer = ask(f'{tag}{w["english"]}{note}\n  ru> ').strip()
            if answer.lower() == 'q':
                break
            knew = plain_ru(answer) == plain_ru(w['word'])
            print(('  yes: ' if knew else '  no: ') + w['word'])
        else:
            if ask(f'{tag}{w["word"]}{note}  ').strip().lower() == 'q':
                break
            print(f'  = {w["english"]}')
            reply = ask('  knew it? [y/n] ').strip().lower()
            if reply == 'q':
                break
            knew = reply.startswith('y')
        if speak:
            try:
                say(w['word'])
            except (FileNotFoundError, RuntimeError, ValueError) as exc:
                print(f'  (no audio: {exc})')
                speak = False
        state[w['key']] = grade(card, knew, today)
        done += 1
    save_state(state)
    print(f'\n{done} cards done. Progress: kirin-learn vocab --stats')
    return 0


def audiobooks():
    catalog = Path(russian_config()['audiobooks']) / 'catalog.json'
    if not catalog.is_file():
        raise FileNotFoundError('Russian audiobooks not downloaded yet: sudo kirin-content install ru-audiobooks')
    return json.loads(catalog.read_text(encoding='utf-8'))


def listen(level=None, play=None):
    books = audiobooks()
    shown = [b for b in books if level is None or b['level'] == level]
    if play is not None:
        if not 1 <= play <= len(shown):
            raise ValueError(f'choose a number from 1 to {len(shown)}')
        folder = Path(russian_config()['audiobooks']) / shown[play - 1]['folder']
        for player in (['vlc', '--playlist-autostart'], ['mpv', '--no-video'], ['xdg-open']):
            if shutil.which(player[0]):
                return subprocess.call(player + [str(folder)])
        raise FileNotFoundError('No audio player found (vlc or mpv)')
    print('Russian audiobooks (LibriVox, public domain; texts are on Wikisource: kirin-learn read wikisource)\n')
    for n, b in enumerate(shown, 1):
        hours = b.get('runtime', '')
        print(f'{n:3}. [{b["level"]}] {b["title"]} - {b["creator"]}  {hours}')
    print('\nPlay one: kirin-learn listen' + (f' --level {level}' if level else '') + ' --play N')
    return 0


def read(what):
    if what == 'mezhdunami':
        index = Path(russian_config()['mezhdunami']) / 'index.html'
        if not index.is_file():
            raise FileNotFoundError('Между нами not downloaded yet: sudo kirin-content install ru-course')
        return subprocess.call(['xdg-open', str(index)])
    zims = russian_config().get('kiwix') or {}
    if what == 'wiktionary' and not zims.get(what):
        zims = {**zims, 'wiktionary': russian_config().get('dictionary')}
    zim = zims.get(what)
    if not zim or not Path(zim).is_file():
        raise FileNotFoundError(f'{KIWIX_NAMES.get(what, what)} not downloaded yet: sudo kirin-content install '
                                + ('ru-reading' if what in ('wikisource', 'wikipedia') else 'ru-dictionaries'))
    return subprocess.call(['flatpak', 'run', 'org.kiwix.desktop', zim])


def study_path():
    try:
        counts = vocab_stats(load_vocab(), load_state())
    except FileNotFoundError:
        counts = {}
    print('Kirin Russian: a route from A1 to B2, using only what is on this machine.')
    print('Roughly 900-1,200 hours of study to B2 for an English speaker: about three years at an hour a day,\n'
          'or 12-18 months at two to three hours a day.\n')
    for level, aim, steps in STUDY_PATH:
        c = counts.get(level)
        progress = f'   words: {c["mastered"]}/{c["total"]} mastered' if c else ''
        print(f'{level}  {aim}{progress}')
        for step in steps:
            print(f'    - {step}')
        print()
    print('Move on when the level\'s words are mostly mastered and the tutor rarely corrects you at that level.')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='Kirin offline learning centre')
    parser.add_argument('--pause', action='store_true', help='wait for Enter before exiting (for menu launchers)')
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
    voc = sub.add_parser('vocab', help='spaced-repetition Russian words, A1-B2')
    voc.add_argument('--level', choices=VOCAB_LEVELS)
    voc.add_argument('--new', type=int, default=10, help='new words this session (default 10)')
    voc.add_argument('--reverse', action='store_true', help='English to Russian: type the word')
    voc.add_argument('--say', action='store_true', help='speak each word')
    voc.add_argument('--stats', action='store_true')
    lis = sub.add_parser('listen', help='Russian audiobooks by level')
    lis.add_argument('--level', choices=VOCAB_LEVELS)
    lis.add_argument('--play', type=int)
    lis.add_argument('--pick', action='store_true', help='ask which one to play')
    rd = sub.add_parser('read', help='open Russian reading material')
    rd.add_argument('what', choices=('mezhdunami', 'wikisource', 'wikipedia', 'wiktionary-ru', 'wiktionary'))
    sub.add_parser('path', help='the study route from A1 to B2')
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
        elif args.action == 'vocab': return vocab(args.level, args.new, args.reverse, args.say, args.stats)
        elif args.action == 'listen':
            if args.pick and args.play is None:
                listen(args.level)
                choice = input('Number to play (Enter to close): ').strip()
                return listen(args.level, int(choice)) if choice.isdigit() else 0
            return listen(args.level, args.play)
        elif args.action == 'read': return read(args.what)
        elif args.action == 'path': return study_path()
    except (ValueError, FileNotFoundError, RuntimeError, json.JSONDecodeError) as exc:
        print(f'kirin-learn: {exc}', file=sys.stderr)
        return 1
    finally:
        if args.pause:
            try:
                input('\nPress Enter to close.')
            except EOFError:
                pass
    return 0

if __name__ == '__main__':
    sys.exit(main())
