#!/usr/bin/env bash
# Publish Kirin's openly licensed content to a GitHub release, so it can always be
# downloaded again even if the original sites change (as the DLI course did).
#
# Run on the build machine after a build that fetched the content (--content bundled),
# with the GitHub CLI logged in (gh auth login):
#
#   scripts/publish-content.sh [--work DIR] [--release content-v1] [--repo OWNER/NAME] [--dry-run]
#
# Mirrors: the FSI/DLI/Peace Corps course library (US government works, public domain),
# the LibriVox audiobooks (public domain) and the Piper Russian voices (MIT). It does
# not mirror the Между нами textbook (CC BY-NC-ND: personal copies only), the
# Wikimedia ZIMs (Kiwix keeps them current) or the AI models (Ollama's registry).
#
# Writes packaging/content/mirror.json; commit and push it so Kirin Content and the
# builder use the mirror.
set -Eeuo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd -- "$HERE/.." && pwd)
WORK="$REPO/work" RELEASE=content-v1 GH_REPO=factionparadox/Kirin DRY=0
PART=${KIRIN_MIRROR_PART_SIZE:-1900M}

while [ $# -gt 0 ]; do
  case "$1" in
    --work) WORK=$2; shift 2 ;;
    --release) RELEASE=$2; shift 2 ;;
    --repo) GH_REPO=$2; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

die() { printf 'publish-content: %s\n' "$*" >&2; exit 1; }
R="$WORK/payloads/russian"
OUTDIR="$WORK/mirror/$RELEASE"
declare -A SOURCES=([ru-course]="$R/library" [ru-audiobooks]="$R/audiobooks" [ru-voices]="$R/voices")

if [ "$DRY" -eq 0 ]; then
  command -v gh >/dev/null || die 'the GitHub CLI (gh) is not installed: sudo pacman -S github-cli'
  gh auth status >/dev/null 2>&1 || die 'log in first: gh auth login'
fi
rm -rf "$OUTDIR"; mkdir -p "$OUTDIR"

for pack in ru-course ru-audiobooks ru-voices; do
  src=${SOURCES[$pack]}
  [ -s "$src/SHA256SUMS" ] || die "$pack: $src has no SHA256SUMS; build once with --content bundled first"
  (cd "$src" && sha256sum --quiet -c SHA256SUMS) || die "$pack: files in $src do not match their SHA256SUMS"
  echo "packing $pack from $src"
  # Reproducible tar: sorted names, fixed owner and time; MP3s and PDFs do not compress.
  tar -C "$(dirname "$src")" --sort=name --owner=0 --group=0 --numeric-owner --mtime='2026-01-01 00:00Z' \
      --transform "s,^$(basename "$src"),$pack," -cf "$OUTDIR/$pack.tar" "$(basename "$src")"
  split -b "$PART" -d -a 2 "$OUTDIR/$pack.tar" "$OUTDIR/$pack.tar."
  files=$(grep -c . "$src/SHA256SUMS")
  python3 - "$OUTDIR" "$pack" "$files" <<'PY'
import hashlib, json, sys
from pathlib import Path
out, pack, files = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
def sha(p):
    with p.open('rb') as h: return hashlib.file_digest(h, 'sha256').hexdigest()
whole = out / f'{pack}.tar'
parts = [{'name': p.name, 'size': p.stat().st_size, 'sha256': sha(p)} for p in sorted(out.glob(f'{pack}.tar.[0-9][0-9]'))]
json.dump({'size': whole.stat().st_size, 'sha256': sha(whole), 'files': files, 'parts': parts},
          open(out / f'{pack}.json', 'w'), indent=1)
PY
  rm -f "$OUTDIR/$pack.tar"
done

python3 - "$OUTDIR" "$RELEASE" "$GH_REPO" "${KIRIN_MIRROR_JSON:-$REPO/packaging/content/mirror.json}" <<'PY'
import json, sys
from pathlib import Path
out, release, repo, target = Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4])
packs = {p.stem: json.load(open(p)) for p in sorted(out.glob('*.json'))}
target.parent.mkdir(parents=True, exist_ok=True)
json.dump({'release': release, 'url': f'https://github.com/{repo}/releases/download/{release}/', 'packs': packs},
          open(target, 'w'), indent=1)
total = sum(p['size'] for p in packs.values())
print(f'mirror.json: {len(packs)} packs, {sum(len(p["parts"]) for p in packs.values())} parts, {total / 1e9:.2f} GB')
PY

cat > "$OUTDIR/NOTES.md" <<'EOF'
Openly licensed content for Kirin Linux's Russian course, mirrored so it can always be downloaded again.
Kirin Content and the image builder fetch these parts, verify each one and the whole against
packaging/content/mirror.json, and unpack them. Do not download them by hand unless you want to.

* ru-course: FSI, DLI and Peace Corps Russian course books and audio (US government works, public
  domain), via fsi-language-courses.org and ERIC; Между нами vocabulary lists and workbooks
  (University of Kansas, CC BY-NC-ND 3.0, unchanged).
* ru-audiobooks: LibriVox recordings (public domain), via the Internet Archive.
* ru-voices: Piper Russian voices irina, denis, dmitri and ruslan (rhasspy/piper-voices, MIT).
EOF

if [ "$DRY" -eq 1 ]; then
  echo "dry run: would upload $(ls "$OUTDIR"/*.tar.?? | wc -l) parts to $GH_REPO release $RELEASE"
  exit 0
fi
gh release view "$RELEASE" --repo "$GH_REPO" >/dev/null 2>&1 ||
  gh release create "$RELEASE" --repo "$GH_REPO" --title 'Kirin content mirror' --notes-file "$OUTDIR/NOTES.md"
gh release upload "$RELEASE" --repo "$GH_REPO" --clobber "$OUTDIR"/*.tar.??
echo
echo "Uploaded. Now commit the mirror index so Kirin uses it:"
echo "  git add packaging/content/mirror.json && git commit -m 'Content mirror $RELEASE' && git push"
