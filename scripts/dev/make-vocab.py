#!/usr/bin/env python3
"""Build packaging/russian/vocab.tsv: a CEFR-banded Russian word list for kirin-learn vocab.

Sources (both checked out at pinned commits; see packaging/russian/VOCAB-SOURCES.md):
  * OpenRussian dictionary data (CC BY-SA 4.0), github.com/Badestrand/russian-dictionary
    nouns/verbs/adjectives/others.csv: stressed forms, translations, inflections.
  * FrequencyWords ru_full.txt (OpenSubtitles 2018 counts), github.com/hermitdave/FrequencyWords

Each lemma's frequency is the sum of the counts of its own inflected forms, so
"идти" also counts "иду", "шёл"... Words are ranked by that and banded by the
cumulative vocabulary sizes of the Russian state test (TORFL / ТРКИ):
A1 780, A2 1300, B1 2300, B2 10000 words. This is an approximation: frequency in
film subtitles, not an official TORFL lexical minimum.

    python3 scripts/dev/make-vocab.py --openrussian DIR --frequency ru_full.txt --out packaging/russian/vocab.tsv
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import re
import sys

BANDS = (('A1', 780), ('A2', 1300), ('B1', 2300), ('B2', 10000))
STRESS = '́'
FILES = {'nouns.csv': 'noun', 'verbs.csv': 'verb', 'adjectives.csv': 'adj', 'others.csv': 'other'}
SKIP_COLS = {'bare', 'accented', 'translations_en', 'translations_de', 'gender', 'partner', 'animate',
             'indeclinable', 'sg_only', 'pl_only', 'aspect', 'comparative', 'superlative'}


def stressed(text: str) -> str:
    """OpenRussian marks stress with an apostrophe after the vowel: молоко' -> молоко́."""
    return text.replace("'", STRESS)


def plain(text: str) -> str:
    return text.replace("'", '').replace('ё', 'е').lower().strip()


def forms(row: dict) -> set[str]:
    out = {plain(row['bare'])}
    for key, value in row.items():
        if key is None or key in SKIP_COLS or not isinstance(value, str) or not value:
            continue
        for piece in re.split(r'[,;/]', value):
            piece = plain(piece)
            if piece and ' ' not in piece:
                out.add(piece)
    return out


def load_frequency(path: Path) -> dict[str, int]:
    freq = {}
    with path.open(encoding='utf-8') as handle:
        for line in handle:
            word, _, count = line.rstrip('\n').rpartition(' ')
            if word and count.isdigit():
                key = word.replace('ё', 'е').lower()
                freq[key] = freq.get(key, 0) + int(count)
    return freq


def note(kind: str, row: dict) -> str:
    if kind == 'noun':
        g = {'m': 'masc.', 'f': 'fem.', 'n': 'neut.', 'pl': 'pl.'}.get(row.get('gender', ''), '')
        return ' '.join(x for x in (g, 'indecl.' if row.get('indeclinable') == '1' else '') if x)
    if kind == 'verb':
        aspect = {'imperfective': 'impf.', 'perfective': 'pf.', 'both': 'impf./pf.'}.get(row.get('aspect', ''), '')
        partner = plain(row.get('partner', '') or '')
        return f'{aspect} (pair: {partner})' if aspect and partner not in ('', '-') else aspect
    return ''


def build(openrussian: Path, frequency: Path) -> list[list[str]]:
    freq = load_frequency(frequency)
    lemmas, seen = [], set()
    for name, kind in FILES.items():
        with (openrussian / name).open(encoding='utf-8', newline='') as handle:
            for row in csv.DictReader(handle, delimiter='\t'):
                english = (row.get('translations_en') or '').strip()
                bare = (row.get('bare') or '').strip()
                if not english or not bare or ' ' in bare or (bare, kind) in seen:
                    continue
                seen.add((bare, kind))
                lemmas.append((plain(bare), kind, stressed(row.get('accented') or bare), english,
                               note(kind, row), forms(row)))
    # A surface form that is itself a dictionary headword counts only for that headword
    # (so "чек" is not credited to "чека"); other shared forms are split evenly.
    headwords: dict[str, int] = {}
    owners: dict[str, int] = {}
    for bare, *_rest, fs in lemmas:
        headwords[bare] = headwords.get(bare, 0) + 1
        for f in fs:
            owners[f] = owners.get(f, 0) + 1
    entries = []
    for bare, kind, word, english, extra, fs in lemmas:
        score = freq.get(bare, 0) / headwords[bare]
        for f in fs - {bare}:
            if f not in headwords:
                score += freq.get(f, 0) / owners[f]
        if score:
            entries.append((score, kind, word, english, extra))
    entries.sort(key=lambda e: -e[0])
    rows, rank = [], 0
    for score, kind, word, english, extra in entries:
        rank += 1
        level = next((lvl for lvl, limit in BANDS if rank <= limit), None)
        if level is None:
            break
        rows.append([str(rank), level, kind, word, english.replace('\t', ' '), extra])
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--openrussian', type=Path, required=True)
    ap.add_argument('--frequency', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args(argv)
    rows = build(args.openrussian, args.frequency)
    with args.out.open('w', encoding='utf-8', newline='') as out:
        out.write('# Kirin Russian vocabulary, A1-B2 (see scripts/dev/make-vocab.py and VOCAB-SOURCES.md)\n')
        out.write('# rank\tlevel\tkind\tword\tenglish\tnote\n')
        for row in rows:
            out.write('\t'.join(row) + '\n')
    counts = {lvl: sum(1 for r in rows if r[1] == lvl) for lvl, _ in BANDS}
    print(f'{len(rows)} words: ' + ', '.join(f'{k} {v}' for k, v in counts.items()), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
