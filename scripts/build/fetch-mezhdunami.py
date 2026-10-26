#!/usr/bin/env python3
"""Make an offline copy of the Между нами online Russian textbook (mezhdunami.org).

Между нами (University of Kansas; authors on the site's About the Authors page)
is a free first-year Russian course, CC BY-NC-ND 3.0. This
copies it verbatim for personal, non-commercial offline use:

* every page under the site (pages, images, styles, scripts, PDFs), with links
  rewritten to work from disk (`.shtml` pages are saved as `.html`);
* scripts and styles the pages load from other sites;
* the lesson audio, which the site plays from SoundCloud: downloaded with yt-dlp
  (--ytdlp) and the SoundCloud players replaced with local <audio> players.

Writes --dest/index.html, KIRIN-README.txt and SHA256SUMS. Never fatal for a
single missing file; fails only if the start page cannot be fetched.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
import sys
import time
from urllib import error, parse, request

USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) kirin-build/1 (+https://github.com/factionparadox/Kirin)'
ATTR = re.compile(r'''(\b(?:href|src)\s*=\s*)(["'])(.*?)\2''', re.I | re.S)
CSS_URL = re.compile(r'''url\(\s*(["']?)([^"')]+)\1\s*\)''', re.I)
IFRAME = re.compile(r'''<iframe\b[^>]*\bsrc\s*=\s*(["'])([^"']*soundcloud[^"']*)\1[^>]*>.*?</iframe>''', re.I | re.S)
TRACK = re.compile(r'tracks(?:%2F|/)(\d+)', re.I)
EXTERNAL_ASSET = re.compile(r'<(?:script|link|img)\b[^>]*>', re.I)
MAX_FILES = 5000
README = '''Между нами (Between Us): an offline copy of https://mezhdunami.org

By its authors at the University of Kansas (see About the Authors in the footer).
Licence: Creative Commons BY-NC-ND 3.0
(https://creativecommons.org/licenses/by-nc-nd/3.0/). Copied unchanged for personal,
non-commercial use; the only changes are those needed to read it offline (links point
to these files, and the SoundCloud players are replaced with the same recordings
saved locally). Kirin is not affiliated with the authors. Open index.html to start.
'''


def get(url: str, attempts: int = 3) -> tuple[bytes, str]:
    last = None
    for attempt in range(1, attempts + 1):
        try:
            req = request.Request(url, headers={'User-Agent': USER_AGENT})
            with request.urlopen(req, timeout=60) as response:
                return response.read(), response.headers.get_content_type()
        except error.HTTPError as exc:
            if exc.code in (401, 403, 404, 410):
                raise
            last = exc
        except OSError as exc:
            last = exc
        time.sleep(attempt)
    raise OSError(str(last))


def local_path(url: str, base_host: str) -> str:
    """Where a same-site URL is stored, relative to the copy's root."""
    path = parse.unquote(parse.urlsplit(url).path) or '/'
    if path.endswith('/'):
        path += 'index.html'
    pure = PurePosixPath(path.lstrip('/'))
    if '..' in pure.parts:
        raise ValueError(f'unsafe path {url}')
    name = str(pure)
    if name.endswith('.shtml'):
        name = name[:-6] + '.html'
    elif not PurePosixPath(name).suffix:
        name += '/index.html'
    return name


def external_path(url: str) -> str:
    parts = parse.urlsplit(url)
    path = PurePosixPath(parse.unquote(parts.path).lstrip('/') or 'index')
    if '..' in path.parts:
        raise ValueError(f'unsafe path {url}')
    suffix = hashlib.sha1(parts.query.encode()).hexdigest()[:8] if parts.query else ''
    name = f'{path}-{suffix}{path.suffix}' if suffix else str(path)
    return f'_external/{parts.hostname}/{name}'


def relative(from_file: str, to_file: str) -> str:
    return parse.quote(posixpath.relpath(to_file, posixpath.dirname(from_file) or '.'))


class Copier:
    def __init__(self, base: str, dest: Path):
        self.base = base if parse.urlsplit(base).path else base + '/'
        self.host = parse.urlsplit(self.base).netloc
        self.dest = dest
        self.saved: dict[str, str] = {}           # url -> local path
        self.failed: list[str] = []
        self.tracks: set[str] = set()
        self.pages: list[str] = []

    def same_site(self, url: str) -> bool:
        return parse.urlsplit(url).netloc == self.host

    def norm(self, url: str, page_url: str) -> str | None:
        url = url.strip()
        if not url or url.startswith(('#', 'mailto:', 'javascript:', 'data:', 'tel:')):
            return None
        absolute = parse.urljoin(page_url, url)
        if not absolute.startswith(('http://', 'https://')):
            return None
        return parse.urldefrag(absolute)[0]

    def fetch(self, url: str, external: bool = False) -> str | None:
        if url in self.saved:
            return self.saved[url]
        if len(self.saved) >= MAX_FILES:
            return None
        try:
            rel = external_path(url) if external else local_path(url, self.host)
            data, kind = get(url)
        except (OSError, ValueError) as exc:
            self.failed.append(f'{url}: {exc}')
            return None
        self.saved[url] = rel
        target = self.dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if kind == 'text/html' and not external:
            self.pages.append(url)
        elif kind == 'text/css' or rel.endswith('.css'):
            self.css(url, rel, data)
        return rel

    def css(self, url: str, rel: str, data: bytes) -> None:
        text = data.decode('utf-8', 'replace')
        external = not self.same_site(url)

        def swap(m):
            target = self.norm(m.group(2), url)
            if not target:
                return m.group(0)
            got = self.fetch(target, external=external or not self.same_site(target))
            return f'url("{relative(rel, got)}")' if got else m.group(0)
        (self.dest / rel).write_text(CSS_URL.sub(swap, text), encoding='utf-8')

    def crawl(self) -> None:
        if not self.fetch(self.base):
            raise OSError(f'could not fetch {self.base}: {self.failed[-1] if self.failed else "unknown"}')
        done = 0
        while done < len(self.pages):
            url = self.pages[done]
            done += 1
            text = (self.dest / self.saved[url]).read_text(encoding='utf-8', errors='replace')
            self.tracks.update(TRACK.findall(' '.join(m.group(2) for m in IFRAME.finditer(text))))
            for tag in EXTERNAL_ASSET.findall(text):
                for m in ATTR.finditer(tag):
                    target = self.norm(m.group(3), url)
                    if target and not self.same_site(target):
                        self.fetch(target, external=True)
            for m in ATTR.finditer(text):
                target = self.norm(m.group(3), url)
                if target and self.same_site(target) and target not in self.saved:
                    self.fetch(target)

    def rewrite(self, audio: dict[str, str]) -> None:
        for url in self.pages:
            rel = self.saved[url]
            path = self.dest / rel
            text = path.read_text(encoding='utf-8', errors='replace')

            def player(m):
                ids = TRACK.findall(m.group(2))
                if ids and ids[0] in audio:
                    return (f'<audio controls preload="none" src="{relative(rel, audio[ids[0]])}">'
                            'Audio</audio>')
                return '<p><em>(This recording is not in the offline copy.)</em></p>'
            text = IFRAME.sub(player, text)

            def link(m):
                target = self.norm(m.group(3), url)
                if target and target in self.saved:
                    frag = parse.urldefrag(parse.urljoin(url, m.group(3)))[1]
                    new = relative(rel, self.saved[target]) + (f'#{frag}' if frag else '')
                    return f'{m.group(1)}{m.group(2)}{new}{m.group(2)}'
                return m.group(0)
            path.write_text(ATTR.sub(link, text), encoding='utf-8')


def fetch_audio(ytdlp: list[str], tracks: set[str], out: Path) -> dict[str, str]:
    out.mkdir(parents=True, exist_ok=True)
    have = {p.stem: p for p in out.iterdir() if p.is_file() and not p.name.endswith(('.part', '.ytdl'))}
    todo = sorted(t for t in tracks if t not in have)
    if todo and ytdlp:
        listing = out / '.tracks.txt'
        listing.write_text(''.join(f'https://api.soundcloud.com/tracks/{t}\n' for t in todo), encoding='utf-8')
        subprocess.run(ytdlp + ['--ignore-errors', '--no-progress', '--quiet', '--no-warnings',
                                '-f', 'bestaudio', '-o', str(out / '%(id)s.%(ext)s'), '-a', str(listing)],
                       check=False)
        listing.unlink(missing_ok=True)
        have = {p.stem: p for p in out.iterdir() if p.is_file() and not p.name.endswith(('.part', '.ytdl'))}
    return {t: f'audio/{have[t].name}' for t in tracks if t in have}


def write_sums(dest: Path) -> int:
    lines = []
    for path in sorted(p for p in dest.rglob('*') if p.is_file() and p.name != 'SHA256SUMS'):
        with path.open('rb') as handle:
            lines.append(f'{hashlib.file_digest(handle, "sha256").hexdigest()}  {path.relative_to(dest).as_posix()}')
    (dest / 'SHA256SUMS').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return len(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--base', default='https://mezhdunami.org/')
    ap.add_argument('--dest', type=Path, required=True)
    ap.add_argument('--ytdlp', help='yt-dlp command, e.g. "python3 /path/yt-dlp" (no audio without it)')
    args = ap.parse_args(argv)
    args.dest.mkdir(parents=True, exist_ok=True)
    copier = Copier(args.base, args.dest)
    try:
        copier.crawl()
    except OSError as exc:
        print(f'MEZHDU NAMI FAILED: {exc}', file=sys.stderr)
        return 1
    ytdlp = args.ytdlp.split() if args.ytdlp else []
    audio = fetch_audio(ytdlp, copier.tracks, args.dest / 'audio')
    copier.rewrite(audio)
    index = local_path(copier.base, copier.host)
    if index != 'index.html':
        (args.dest / 'index.html').write_text(
            f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url={index}">', encoding='utf-8')
    (args.dest / 'KIRIN-README.txt').write_text(README, encoding='utf-8')
    files = write_sums(args.dest)
    print(f'Между нами: {len(copier.pages)} pages, {len(audio)}/{len(copier.tracks)} recordings, '
          f'{files} files, {len(copier.failed)} not available')
    for line in copier.failed[:20]:
        print(f'  not available: {line}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
