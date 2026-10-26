#!/usr/bin/env bash
# Kirin ISO builder: remasters the official openKylin 3.0 x86-64 ISO.
#
# Run as root on an x86-64 Linux build host with internet access and ~70 GB
# free. Everything happens under --work; nothing on the host is modified
# except temporary bind mounts into the work directory.
#
#   sudo build/kirin-build.sh --iso openKylin-Desktop-V3.0-20260918-x86_64.iso
#
# See docs/BUILDING.md for stages, review gates and what the output is (and is not).
set -Eeuo pipefail
# Show helper output as it happens, even through pipes (Python buffers it otherwise).
export PYTHONUNBUFFERED=1

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd -- "$HERE/.." && pwd)
STAGES=(preflight verify extract inventory payloads customise audit pack)
QWEN_TAG='qwen2.5-coder:7b-instruct'
# Russian learning (docs/RUSSIAN.md). A mixture-of-experts model: 30B parameters,
# about 3B active per token, so it answers quickly on a CPU with 32 GB of RAM.
TUTOR_TAG='qwen3:30b-a3b-instruct-2507-q4_K_M'
PIPER_VERSION='2023.11.14-2'
PIPER_SHA256=${KIRIN_TEST_PIPER_SHA256:-a50cb45f355b7af1f6d758c1b360717877ba0a398cc8cbe6d2a7a3a26e225992}
KIWIX_INDEX=${KIRIN_TEST_KIWIX_INDEX:-https://download.kiwix.org/zim/wiktionary/}
KIWIX_PREFIX='wiktionary_en_all_nopic_'
RUSSIAN_DIR=/opt/kirin/russian
PROTON_JSON=${KIRIN_TEST_PROTON_JSON:-$REPO/packaging/proton.json}
KIRIN_REPO_URL='https://factionparadox.github.io/Kirin/apt'
# Debian 13 archive and security signing keys (https://ftp-master.debian.org/keys.html).
DEBIAN_KEYS=${KIRIN_TEST_DEBIAN_KEYS:-"https://ftp-master.debian.org/keys/archive-key-13.asc=04B54C3CDCA79751B16BC6B5225629DF75B188BD https://ftp-master.debian.org/keys/archive-key-13-security.asc=5E04A1E3223A19A20706E20F9904613D4CCE68C6"}
VOICES_TSV=${KIRIN_TEST_VOICES_TSV:-$REPO/packaging/russian/voices.tsv}
LIBRARY_TSV=${KIRIN_TEST_LIBRARY_TSV:-$REPO/packaging/russian/library.tsv}
AUDIOBOOKS_TSV=${KIRIN_TEST_AUDIOBOOKS_TSV:-$REPO/packaging/russian/audiobooks.tsv}
ARCHIVE_BASE=${KIRIN_TEST_ARCHIVE_BASE:-https://archive.org/}
MEZHDUNAMI_BASE=${KIRIN_TEST_MEZHDUNAMI_BASE:-https://mezhdunami.org/}
YTDLP_URL='https://github.com/yt-dlp/yt-dlp/releases/latest/download'
# More Kiwix ZIMs for reading at B1-B2: key|directory|prefix (the Wikipedia variant is set by --ru-wikipedia).
KIWIX_ZIM_BASE=${KIRIN_TEST_KIWIX_ZIM_BASE:-https://download.kiwix.org/zim}
OLLAMA_VERSION_DEFAULT='v0.40.11'
# Kirin compatibility build of libfyaml0 (see build/chroot-steps.sh compat_libfyaml).
FYAML_VERSION='0.9.6'
FYAML_SHA256=${KIRIN_TEST_FYAML_SHA256:-a59cc3331e2eb903ec36933ad52a45888041cac31e44f553a00511131242c483}
MIN_FREE_GB=${KIRIN_MIN_FREE_GB:-70}

ISO='' ISO_SHA256='' WORK="$PWD/work" OUT="$PWD/out" SQUASHFS_REL=''
MODEL_INVENTORY='' ACCEPT_INVENTORY=0 TEST_BUILD=0 FROM='' ONLY='' NO_RUSSIAN=0 KIWIX_NAME='' NO_EXTRA_REPOS=0
RU_WIKIPEDIA=mini
OLLAMA_VERSION=$OLLAMA_VERSION_DEFAULT
ALLOW_REMOVAL=()

usage() {
  cat <<EOF
Usage: sudo $0 --iso FILE [options]

Required:
  --iso FILE              Official openKylin 3.0 x86-64 ISO, downloaded by you

Optional check:
  --iso-sha256 HEX        Refuse the ISO unless its SHA-256 matches HEX

Review gates:
  --accept-inventory      Continue past the AI-model inventory after you have reviewed it
  --model-inventory FILE  Use your own reviewed {path: sha256} inventory instead of the scan
  --allow-removal PKG     Permit APT to also remove PKG during purges (repeatable, after review)

Options:
  --work DIR              Work directory (default: ./work)
  --out DIR               Output directory (default: ./out)
  --squashfs PATH         Root filesystem squashfs inside the ISO, if detection is ambiguous
  --ollama-version TAG    Ollama release tag (default: $OLLAMA_VERSION_DEFAULT)
  --no-russian            Leave out the Russian tutor model, voices, course library and dictionary
  --no-extra-repos        Do not add the pinned Ubuntu 26.04 and Debian 13 repositories
  --kiwix-name FILE       Pin the Wiktionary ZIM (e.g. ${KIWIX_PREFIX}2026-09.zim) instead of the newest
  --ru-wikipedia KIND     Russian Wikipedia ZIM: mini (default: every article's introduction, a few GB),
                          nopic (full articles, ~10 GB), maxi (with pictures, ~30 GB) or none
  --test-build            Produce an ISO even if policy audits fail (they are listed in its .build.json).
                          The AI-model contract is never relaxed.
  --from STAGE            Re-run from STAGE onwards
  --only STAGE            Run just STAGE
Stages: ${STAGES[*]}
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --iso) ISO=$2; shift 2 ;;
    --iso-sha256) ISO_SHA256=${2,,}; shift 2 ;;
    --work) WORK=$2; shift 2 ;;
    --out) OUT=$2; shift 2 ;;
    --squashfs) SQUASHFS_REL=${2#/}; shift 2 ;;
    --model-inventory) MODEL_INVENTORY=$2; shift 2 ;;
    --accept-inventory) ACCEPT_INVENTORY=1; shift ;;
    --allow-removal) ALLOW_REMOVAL+=("$2"); shift 2 ;;
    --ollama-version) OLLAMA_VERSION=$2; shift 2 ;;
    --test-build) TEST_BUILD=1; shift ;;
    --no-russian) NO_RUSSIAN=1; shift ;;
    --no-extra-repos) NO_EXTRA_REPOS=1; shift ;;
    --kiwix-name) KIWIX_NAME=$2; shift 2 ;;
    --ru-wikipedia)
      case "$2" in nopic|maxi|mini|none) RU_WIKIPEDIA=$2 ;; *) echo '--ru-wikipedia takes nopic, maxi, mini or none' >&2; exit 2 ;; esac
      shift 2 ;;
    --from) FROM=$2; shift 2 ;;
    --only) ONLY=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

log()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing host tool: $1 ($2)"; }

if [ -z "$ISO" ]; then usage >&2; exit 2; fi
if [ -n "$ISO_SHA256" ] && ! [[ $ISO_SHA256 =~ ^[0-9a-f]{64}$ ]]; then die '--iso-sha256 must be 64 hex digits'; fi
ISO=$(realpath -e -- "$ISO") || die "ISO not found"
mkdir -p "$WORK" "$OUT"
WORK=$(realpath -- "$WORK") OUT=$(realpath -- "$OUT")
case "$WORK" in /|/home|/root|/usr|/var|/tmp) die "refusing work directory $WORK" ;; esac
[ -z "$MODEL_INVENTORY" ] || MODEL_INVENTORY=$(realpath -e -- "$MODEL_INVENTORY")

ROOTFS="$WORK/rootfs" ISOTREE="$WORK/iso" UPSTREAM="$WORK/upstream" PAYLOADS="$WORK/payloads" AUDIT="$WORK/audit"
mkdir -p "$UPSTREAM" "$PAYLOADS" "$AUDIT"

# ---------------------------------------------------------------- chroot helpers
MOUNTS=()
mount_chroot() {
  [ ${#MOUNTS[@]} -eq 0 ] || return 0
  local m
  for m in dev dev/pts proc sys run; do mkdir -p "$ROOTFS/$m"; done
  # Make the image root a mount point of its own: Flatpak's bwrap (used for its
  # install triggers) fails with "Failed to make / slave" in a plain chroot.
  mount --bind "$ROOTFS" "$ROOTFS";            MOUNTS+=("$ROOTFS")
  mount --make-private "$ROOTFS"
  mount --bind /dev "$ROOTFS/dev";             MOUNTS+=("$ROOTFS/dev")
  mount -t devpts devpts "$ROOTFS/dev/pts";    MOUNTS+=("$ROOTFS/dev/pts")
  mount -t proc proc "$ROOTFS/proc";           MOUNTS+=("$ROOTFS/proc")
  mount -t sysfs sysfs "$ROOTFS/sys";          MOUNTS+=("$ROOTFS/sys")
  mount -t tmpfs tmpfs "$ROOTFS/run";          MOUNTS+=("$ROOTFS/run")

  # DNS for apt/flatpak inside the chroot; original resolv.conf is restored later.
  if [ -e "$ROOTFS/etc/resolv.conf" ] || [ -L "$ROOTFS/etc/resolv.conf" ]; then
    [ -e "$ROOTFS/etc/resolv.conf.kirin-orig" ] || [ -L "$ROOTFS/etc/resolv.conf.kirin-orig" ] ||
      mv "$ROOTFS/etc/resolv.conf" "$ROOTFS/etc/resolv.conf.kirin-orig"
  fi
  local src=/etc/resolv.conf
  grep -q '^nameserver 127\.0\.0\.53' /etc/resolv.conf 2>/dev/null &&
    [ -f /run/systemd/resolve/resolv.conf ] && src=/run/systemd/resolve/resolv.conf
  rm -f "$ROOTFS/etc/resolv.conf"; cp -L "$src" "$ROOTFS/etc/resolv.conf"

  # Stop maintainer scripts from starting services in the chroot.
  if [ ! -e "$ROOTFS/usr/sbin/policy-rc.d.kirin" ]; then
    printf '#!/bin/sh\nexit 101\n' > "$ROOTFS/usr/sbin/policy-rc.d"
    chmod 0755 "$ROOTFS/usr/sbin/policy-rc.d"; touch "$ROOTFS/usr/sbin/policy-rc.d.kirin"
  fi

  mkdir -p "$ROOTFS/kirin-build"
  install -m 0755 "$HERE/chroot-steps.sh" "$ROOTFS/kirin-build/chroot-steps.sh"
  install -m 0644 "$REPO/packaging/base-packages.txt" "$REPO/packaging/flatpak-apps.txt" \
    "$REPO/packaging/extra-packages.txt" "$REPO/packaging/prefer-ubuntu.txt" "$ROOTFS/kirin-build/"
  [ ! -f "$PAYLOADS/libfyaml-$FYAML_VERSION.tar.gz" ] ||
    install -m 0644 "$PAYLOADS/libfyaml-$FYAML_VERSION.tar.gz" "$ROOTFS/kirin-build/"
  install -m 0755 "$REPO/scripts/build/build-debs.py" "$ROOTFS/kirin-build/build-debs.py"
  rm -rf "$ROOTFS/kirin-build/debs"; cp -r "$REPO/packaging/debs" "$ROOTFS/kirin-build/debs"
  rm -rf "$ROOTFS/kirin-build/proton"
  [ ! -d "$PAYLOADS/proton" ] || cp -r "$PAYLOADS/proton" "$ROOTFS/kirin-build/proton"
  if [ -f "$PAYLOADS/kirin-archive-keyring.gpg" ]; then
    mkdir -p "$ROOTFS/kirin-build/kirin-repo"
    cp "$PAYLOADS/kirin-archive-keyring.gpg" "$ROOTFS/kirin-build/kirin-repo/"
    printf '%s\n' "$KIRIN_REPO_URL" > "$ROOTFS/kirin-build/kirin-repo/url"
  fi
  mkdir -p "$ROOTFS/kirin-build/extra-repos"
  cp "$REPO"/packaging/apt/extra-repos/* "$ROOTFS/kirin-build/extra-repos/"
  [ ! -f "$PAYLOADS/kirin-debian.gpg" ] || cp "$PAYLOADS/kirin-debian.gpg" "$ROOTFS/kirin-build/extra-repos/"
  touch "$ROOTFS/kirin-build/IN_CHROOT"
}

umount_chroot() {
  local i
  for ((i=${#MOUNTS[@]}-1; i>=0; i--)); do
    umount "${MOUNTS[i]}" 2>/dev/null || umount -l "${MOUNTS[i]}" 2>/dev/null || true
  done
  MOUNTS=()
}

restore_chroot() {
  umount_chroot
  rm -rf "$ROOTFS/kirin-build"
  if [ -e "$ROOTFS/usr/sbin/policy-rc.d.kirin" ]; then
    rm -f "$ROOTFS/usr/sbin/policy-rc.d" "$ROOTFS/usr/sbin/policy-rc.d.kirin"
  fi
  if [ -e "$ROOTFS/etc/resolv.conf.kirin-orig" ] || [ -L "$ROOTFS/etc/resolv.conf.kirin-orig" ]; then
    rm -f "$ROOTFS/etc/resolv.conf"; mv "$ROOTFS/etc/resolv.conf.kirin-orig" "$ROOTFS/etc/resolv.conf"
  fi
}

OLLAMA_PID=''
cleanup() {
  [ -z "$OLLAMA_PID" ] || kill "$OLLAMA_PID" 2>/dev/null || true
  [ ${#MOUNTS[@]} -eq 0 ] || umount_chroot
}
trap cleanup EXIT
trap 'die "stage failed at line $LINENO: $BASH_COMMAND"' ERR

# Inside the image, use openKylin's PATH: the host's (e.g. Arch's, via sudo) may
# lack the sbin directories dpkg needs. The host chroot binary is found first.
in_chroot() {
  local chroot_bin; chroot_bin=$(command -v chroot)
  PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "$chroot_bin" "$ROOTFS" /kirin-build/chroot-steps.sh "$@"
}
pkglist() { sed -e 's/#.*//' -e 's/[[:space:]]//g' -e '/^$/d' "$1"; }

# ---------------------------------------------------------------- stages
stage_preflight() {
  log 'Preflight'
  [ "$(uname -s)" = Linux ] || die 'build host must be Linux (WSL2 works if it has ~70 GB free)'
  [ "$(uname -m)" = x86_64 ] || die 'build host must be x86-64 to chroot into the amd64 image'
  [ "$EUID" -eq 0 ] || die 'run as root (unsquash ownership, chroot and mounts need it)'
  need xorriso 'apt install xorriso'
  need mksquashfs 'apt install squashfs-tools'
  need unsquashfs 'apt install squashfs-tools'
  need curl 'apt install curl'
  need zstd 'apt install zstd'
  need python3 'apt install python3'
  need sha256sum coreutils; need chroot coreutils; need realpath coreutils
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || die 'python3 3.11 or newer is required'
  local free_gb need=$MIN_FREE_GB; free_gb=$(df --output=avail -BG "$WORK" | tail -1 | tr -dc 0-9)
  # The Russian kit adds a 19 GB model and a multi-GB dictionary, held in payloads, rootfs and squashfs.
  [ "$NO_RUSSIAN" -eq 1 ] || [ -n "${KIRIN_MIN_FREE_GB:-}" ] || need=150
  [ "$free_gb" -ge "$need" ] || die "need ${need} GB free under $WORK, have ${free_gb} GB"
  info "host ok; ${free_gb} GB free in $WORK"
}

stage_verify() {
  log 'Verifying the upstream ISO'
  local actual; actual=$(sha256sum -- "$ISO" | cut -d' ' -f1)
  if [ -n "$ISO_SHA256" ]; then
    [ "$actual" = "$ISO_SHA256" ] || die "ISO checksum mismatch: got $actual"
    info 'sha256 matches'
  else
    info "sha256 $actual (not checked; recorded in the build record)"
  fi
  local volid; volid=$(xorriso -indev "$ISO" -pvd_info 2>/dev/null | sed -n 's/^Volume Id *: *//p' | head -1)
  python3 - "$UPSTREAM/iso.json" "$(basename -- "$ISO")" "$actual" "$(stat -c %s -- "$ISO")" "$volid" <<'PY'
import json, sys
out, name, sha, size, volid = sys.argv[1:]
json.dump({'file': name, 'sha256': sha, 'size': int(size), 'volume_id': volid}, open(out, 'w'), indent=2)
PY
  info "volume id: ${volid:-unknown}"
}

stage_extract() {
  log 'Extracting the ISO and its root filesystem'
  rm -rf "$ISOTREE" "$ROOTFS"
  xorriso -osirrox on -indev "$ISO" -extract / "$ISOTREE" > "$UPSTREAM/extract.log" 2>&1 ||
    die "ISO extraction failed; see $UPSTREAM/extract.log"
  chmod -R u+w "$ISOTREE"

  # Files over 4 GiB can come out of the ISO cut short (their recorded size wraps
  # at 2^32). Check every squashfs and re-read any short one from the ISO.
  local sq
  while IFS= read -r -d '' sq; do
    unsquashfs -s "$ISOTREE/$sq" > /dev/null 2>&1 && continue
    info "$sq came out incomplete ($(stat -c %s "$ISOTREE/$sq") bytes); re-reading it from the ISO"
    python3 "$REPO/scripts/build/recover-squashfs.py" --iso "$ISO" --file "$ISOTREE/$sq" \
        ${KIRIN_TEST_WRAP:+--wrap "$KIRIN_TEST_WRAP"} | sed 's/^/    /' ||
      die "could not recover $sq from the ISO; the download may be damaged, so re-download it"
    unsquashfs -s "$ISOTREE/$sq" > /dev/null 2>&1 || die "$sq is still unreadable after recovery"
  done < <(find "$ISOTREE" -type f -name '*.squashfs' -printf '%P\0')

  if [ -z "$SQUASHFS_REL" ]; then
    mapfile -t found < <(find "$ISOTREE" -type f -name '*.squashfs' -printf '%s %P\n' | sort -rn)
    [ ${#found[@]} -gt 0 ] || die 'no *.squashfs found in the ISO; pass --squashfs'
    info 'squashfs images in the ISO:'; printf '      %s\n' "${found[@]}"
    if [ ${#found[@]} -gt 1 ]; then
      local big=${found[0]%% *} next=${found[1]%% *}
      [ "$big" -ge $((next * 2)) ] || die 'several similarly sized squashfs images; choose one with --squashfs'
    fi
    SQUASHFS_REL=${found[0]#* }
  fi
  [ -f "$ISOTREE/$SQUASHFS_REL" ] || die "no such squashfs in ISO: $SQUASHFS_REL"
  printf '%s\n' "$SQUASHFS_REL" > "$UPSTREAM/squashfs.path"
  unsquashfs -s "$ISOTREE/$SQUASHFS_REL" > "$UPSTREAM/squashfs.info"
  info "root filesystem: $SQUASHFS_REL ($(sed -n 's/^Compression //p' "$UPSTREAM/squashfs.info"))"

  unsquashfs -d "$ROOTFS" "$ISOTREE/$SQUASHFS_REL" >/dev/null
  [ -f "$ROOTFS/var/lib/dpkg/status" ] || die 'unpacked root has no dpkg database; wrong squashfs?'
  cp "$ROOTFS/var/lib/dpkg/status" "$UPSTREAM/dpkg-status.orig"
  info "unpacked to $ROOTFS"
}

stage_inventory() {
  log 'Inventorying upstream AI model files'
  local inv="$UPSTREAM/upstream-models.json" owners="$UPSTREAM/upstream-models-owners.json" rc=0
  if [ -n "$MODEL_INVENTORY" ]; then
    [ "$MODEL_INVENTORY" -ef "$inv" ] || cp "$MODEL_INVENTORY" "$inv"
    python3 "$REPO/scripts/build/inventory-models.py" --root "$ROOTFS" --inventory "$inv" --owners-out "$owners" || rc=$?
  else
    python3 "$REPO/scripts/build/inventory-models.py" --root "$ROOTFS" --out "$inv" --owners-out "$owners" \
        --exclude-file "$HERE/model-exclusions.txt" || rc=$?
  fi
  [ "$rc" -eq 0 ] || die 'model inventory failed or found nothing; see above'
  # Prove the inventory matches the untouched upstream root before anything changes.
  python3 - "$inv" "$ROOTFS" <<'PY'
import hashlib, json, sys
from pathlib import Path
inv, root = json.load(open(sys.argv[1])), Path(sys.argv[2])
bad = [p for p, h in inv.items() if hashlib.file_digest((root / p).open('rb'), 'sha256').hexdigest() != h]
if bad: sys.exit('inventory does not match upstream files: ' + ', '.join(bad))
PY
  if [ "$ACCEPT_INVENTORY" -ne 1 ]; then
    cat <<EOF

REVIEW REQUIRED before the image is modified.
  The list above is saved in: $inv
Check that every upstream AI model is listed and nothing unrelated is.
If the list is right, continue with this one command:

  sudo $0 --iso '$ISO' --from inventory --accept-inventory

If you edited $(basename "$inv") by hand, add: --model-inventory '$inv.reviewed'
(save your edited copy under that name first; a re-run rescans the original).
EOF
    exit 10
  fi
  info 'inventory accepted'
}

fetch_ollama() {
  local dir="$PAYLOADS/ollama-$OLLAMA_VERSION" base="https://github.com/ollama/ollama/releases/download/$OLLAMA_VERSION"
  if [ -x "$dir/root/bin/ollama" ]; then info "Ollama $OLLAMA_VERSION already unpacked"; return; fi
  mkdir -p "$dir"
  curl -fsSL "$base/sha256sum.txt" -o "$dir/sha256sum.txt"
  local name
  for name in ollama-linux-amd64.tar.zst ollama-linux-amd64.tgz; do
    grep -qE "[[:space:]](\./)?$name\$" "$dir/sha256sum.txt" && break
    name=''
  done
  [ -n "$name" ] || die "no linux-amd64 archive listed in $OLLAMA_VERSION sha256sum.txt"
  info "downloading $name"
  curl -fL --progress-bar "$base/$name" -o "$dir/$name"
  local want; want=$(grep -E "[[:space:]](\./)?$name\$" "$dir/sha256sum.txt" | cut -d' ' -f1)
  [ "$(sha256sum "$dir/$name" | cut -d' ' -f1)" = "$want" ] || die "$name checksum mismatch"
  rm -rf "$dir/root"; mkdir -p "$dir/root"
  case "$name" in
    *.tar.zst) zstd -dc "$dir/$name" | tar -xf - -C "$dir/root" ;;
    *.tgz) tar -xzf "$dir/$name" -C "$dir/root" ;;
  esac
  [ -x "$dir/root/bin/ollama" ] || die 'Ollama archive did not contain bin/ollama'
  info "Ollama $OLLAMA_VERSION verified"
}

# pull_model TAG INDEX-FILE DESCRIPTION
pull_model() {
  local tag=$1 index=$2 about=$3 models="$PAYLOADS/models"
  local bin="$PAYLOADS/ollama-$OLLAMA_VERSION/root/bin/ollama"
  # Already downloaded? Re-verify every blob and (re)write the index from what is there.
  if python3 "$REPO/scripts/build/qwen-index.py" --models "$models" --tag "$tag" --out "$index.check" >/dev/null 2>&1; then
    mv -f "$index.check" "$index"; info "$tag already present and verified"; return
  fi
  rm -f "$index.check"
  mkdir -p "$models"
  info "pulling $tag ($about)"
  OLLAMA_MODELS="$models" OLLAMA_HOST=127.0.0.1:11435 "$bin" serve >"$PAYLOADS/ollama-serve.log" 2>&1 &
  OLLAMA_PID=$!
  local i
  for i in $(seq 60); do
    OLLAMA_HOST=127.0.0.1:11435 "$bin" list >/dev/null 2>&1 && break
    kill -0 "$OLLAMA_PID" 2>/dev/null || die "ollama serve exited; see $PAYLOADS/ollama-serve.log"
    sleep 1
  done
  OLLAMA_HOST=127.0.0.1:11435 "$bin" pull "$tag"
  kill "$OLLAMA_PID"; wait "$OLLAMA_PID" 2>/dev/null || true; OLLAMA_PID=''
  python3 "$REPO/scripts/build/qwen-index.py" --models "$models" --tag "$tag" --out "$index"
}

pull_qwen() { pull_model "$QWEN_TAG" "$PAYLOADS/qwen-blobs.json" 'about 4.7 GB'; }

fetch_piper() {
  local dir="$PAYLOADS/piper-$PIPER_VERSION" tarball
  tarball="$dir/piper_linux_x86_64.tar.gz"
  if [ -x "$dir/root/piper/piper" ]; then info "Piper $PIPER_VERSION already unpacked"; return; fi
  mkdir -p "$dir"
  if [ ! -f "$tarball" ] || [ "$(sha256sum "$tarball" | cut -d' ' -f1)" != "$PIPER_SHA256" ]; then
    curl -fsSL "https://github.com/rhasspy/piper/releases/download/$PIPER_VERSION/piper_linux_x86_64.tar.gz" -o "$tarball"
  fi
  [ "$(sha256sum "$tarball" | cut -d' ' -f1)" = "$PIPER_SHA256" ] || die "Piper $PIPER_VERSION checksum mismatch"
  rm -rf "$dir/root"; mkdir -p "$dir/root"
  tar -xzf "$tarball" -C "$dir/root"
  [ -x "$dir/root/piper/piper" ] || die 'Piper archive did not contain piper/piper'
  info "Piper $PIPER_VERSION verified"
}

fetch_russian() {
  [ "$NO_RUSSIAN" -eq 0 ] || { info 'Russian extras skipped (--no-russian)'; return; }
  local r="$PAYLOADS/russian"
  mkdir -p "$r"
  pull_model "$TUTOR_TAG" "$PAYLOADS/tutor-blobs.json" 'about 19 GB'
  fetch_piper
  info 'fetching Piper Russian voices'
  python3 "$REPO/scripts/build/fetch-files.py" --manifest "$VOICES_TSV" \
      --dest "$r/voices" --lock "$r/voices.lock.json" --required |& sed 's/^/    /' ||
    die 'could not fetch the Piper Russian voices'
  info 'fetching the Russian course library (DLI, FSI, Peace Corps)'
  python3 "$REPO/scripts/build/fetch-files.py" --manifest "$LIBRARY_TSV" \
      --dest "$r/library" --lock "$r/library.lock.json" |& sed 's/^/    /' ||
    die 'the course library manifest could not be processed'
  info 'fetching the English Wiktionary for Kiwix (several GB)'
  local zim
  zim=$(python3 "$REPO/scripts/build/fetch-kiwix.py" --index "$KIWIX_INDEX" --prefix "$KIWIX_PREFIX" \
        --dest "$r/dictionary" ${KIWIX_NAME:+--name "$KIWIX_NAME"}) || die 'could not fetch the Wiktionary ZIM'
  printf '%s\n' "$zim" > "$r/dictionary.name"
  info "dictionary: $zim (checksum verified)"
  fetch_reading_zims
  info 'fetching Russian audiobooks (LibriVox, via the Internet Archive; several GB)'
  python3 "$REPO/scripts/build/fetch-archive.py" --manifest "$AUDIOBOOKS_TSV" --dest "$r/audiobooks" \
      --base "$ARCHIVE_BASE" |& sed 's/^/    /' || die 'the audiobook manifest could not be processed'
  fetch_mezhdunami
}

# Russian Wiktionary, Wikisource and Wikipedia. Each is optional: a missing one is reported.
fetch_reading_zims() {
  local r="$PAYLOADS/russian" entry key dir prefix zim
  local -a zims=("wiktionary-ru|wiktionary|wiktionary_ru_all_nopic_" "wikisource|wikisource|wikisource_ru_all_nopic_")
  [ "$RU_WIKIPEDIA" = none ] || zims+=("wikipedia|wikipedia|wikipedia_ru_all_${RU_WIKIPEDIA}_")
  : > "$r/kiwix.list.new"
  for entry in "${zims[@]}"; do
    IFS='|' read -r key dir prefix <<< "$entry"
    info "fetching $prefix* (Kiwix)"
    if zim=$(python3 "$REPO/scripts/build/fetch-kiwix.py" --index "$KIWIX_ZIM_BASE/$dir/" --prefix "$prefix" --dest "$r/dictionary"); then
      printf '%s\t%s\n' "$key" "$zim" >> "$r/kiwix.list.new"
      info "$key: $zim (checksum verified)"
    else
      info "not available: $prefix (left out)"
    fi
  done
  # ZIMs no longer wanted (for example after --ru-wikipedia none) are removed.
  local f
  for f in "$r"/dictionary/*.zim; do
    [ -e "$f" ] || continue
    case "$(basename "$f")" in "$(cat "$r/dictionary.name")") continue ;; esac
    cut -f2 "$r/kiwix.list.new" | grep -qxF "$(basename "$f")" || { rm -f "$f"; info "removed $(basename "$f")"; }
  done
  mv -f "$r/kiwix.list.new" "$r/kiwix.list"
}

# yt-dlp (for the textbook's SoundCloud audio), checked against its release's SHA2-256SUMS.
fetch_ytdlp() {
  local dir="$PAYLOADS/yt-dlp" want
  mkdir -p "$dir"
  curl -fsSL "$YTDLP_URL/SHA2-256SUMS" -o "$dir/SHA2-256SUMS" || return 1
  want=$(awk '$2 == "yt-dlp" {print $1}' "$dir/SHA2-256SUMS")
  [ -n "$want" ] || return 1
  if [ ! -f "$dir/yt-dlp" ] || [ "$(sha256sum "$dir/yt-dlp" | cut -d' ' -f1)" != "$want" ]; then
    curl -fsSL "$YTDLP_URL/yt-dlp" -o "$dir/yt-dlp" || return 1
  fi
  [ "$(sha256sum "$dir/yt-dlp" | cut -d' ' -f1)" = "$want" ] || return 1
  echo "python3 $dir/yt-dlp"
}

fetch_mezhdunami() {
  local r="$PAYLOADS/russian" ytdlp=${KIRIN_TEST_YTDLP:-}
  info 'copying the Между нами textbook and its audio for offline use'
  if [ -z "$ytdlp" ]; then
    ytdlp=$(fetch_ytdlp) || { ytdlp=''; info 'yt-dlp unavailable: the textbook is copied without its audio'; }
  fi
  python3 "$REPO/scripts/build/fetch-mezhdunami.py" --base "$MEZHDUNAMI_BASE" --dest "$r/mezhdunami" \
      ${ytdlp:+--ytdlp "$ytdlp"} |& sed 's/^/    /' || info 'Между нами not available (left out)'
}


fetch_libfyaml() {
  local tarball="$PAYLOADS/libfyaml-$FYAML_VERSION.tar.gz"
  if [ ! -f "$tarball" ] || [ "$(sha256sum "$tarball" | cut -d' ' -f1)" != "$FYAML_SHA256" ]; then
    curl -fsSL "https://github.com/pantoniou/libfyaml/releases/download/v$FYAML_VERSION/libfyaml-$FYAML_VERSION.tar.gz" \
      -o "$tarball"
  fi
  [ "$(sha256sum "$tarball" | cut -d' ' -f1)" = "$FYAML_SHA256" ] || die "libfyaml $FYAML_VERSION source checksum mismatch"
  info "libfyaml $FYAML_VERSION source verified"
}

fetch_debian_keys() {
  [ "$NO_EXTRA_REPOS" -eq 0 ] || return 0
  local out="$PAYLOADS/kirin-debian.gpg" tmp="$PAYLOADS/debian-keys" pair url fpr n=0
  rm -rf "$tmp"; mkdir -p "$tmp"
  for pair in $DEBIAN_KEYS; do
    url=${pair%=*} fpr=${pair##*=} n=$((n + 1))
    curl -fsSL "$url" -o "$tmp/$n.asc" || die "could not download Debian key $url"
    python3 "$REPO/scripts/build/pgp-fingerprint.py" "$tmp/$n.asc" --expect "$fpr" --binary-out "$tmp/$n.gpg" |
      sed 's/^/    /' || die "Debian key $url does not have the pinned fingerprint $fpr"
  done
  cat "$tmp"/*.gpg > "$out"
  rm -rf "$tmp"
  info 'Debian 13 signing keys verified against pinned fingerprints'
}

fetch_proton() {
  info "fetching Proton's official VPN, Pass and Mail packages"
  python3 "$REPO/scripts/build/fetch-proton.py" --config "$PROTON_JSON" --dest "$PAYLOADS/proton" | sed 's/^/    /'
}

# The Kirin APT repository is added once its public key is committed (docs/KIRIN-REPO.md).
fetch_kirin_key() {
  local key="$REPO/packaging/apt/kirin-archive-keyring.asc" fpr="$REPO/packaging/apt/kirin-archive-keyring.fingerprint"
  rm -f "$PAYLOADS/kirin-archive-keyring.gpg"
  if [ ! -f "$key" ] || [ ! -f "$fpr" ]; then
    info 'Kirin APT repository not set up yet (no public key committed); Kirin packages come with the ISO only'
    return 0
  fi
  python3 "$REPO/scripts/build/pgp-fingerprint.py" "$key" --expect "$(tr -d ' \n' < "$fpr")" \
      --binary-out "$PAYLOADS/kirin-archive-keyring.gpg" | sed 's/^/    /' ||
    die 'packaging/apt/kirin-archive-keyring.asc does not match its committed fingerprint'
}

stage_payloads() {
  log 'Fetching payloads: Ollama, the AI models, Russian learning material and compatibility sources'
  fetch_ollama
  pull_qwen
  fetch_libfyaml
  fetch_debian_keys
  fetch_proton
  fetch_kirin_key
  fetch_russian
}

install_russian() {
  [ "$NO_RUSSIAN" -eq 0 ] || return 0
  local r="$PAYLOADS/russian" dest="$ROOTFS$RUSSIAN_DIR"
  info 'installing Russian learning material'
  rm -rf "$dest" "$ROOTFS/opt/kirin/piper"
  mkdir -p "$dest" "$ROOTFS/opt/kirin"
  cp -a "$PAYLOADS/piper-$PIPER_VERSION/root/piper" "$ROOTFS/opt/kirin/piper"
  local part
  # Hard links save space, but fail while the image is bind-mounted for the chroot;
  # then make a full copy (never into a half-made directory, which would nest it).
  for part in voices library dictionary audiobooks mezhdunami; do
    [ -d "$r/$part" ] || continue
    rm -rf "$dest/$part"
    cp -al "$r/$part" "$dest/$part" 2>/dev/null || { rm -rf "$dest/$part"; cp -a "$r/$part" "$dest/$part"; }
  done
  find "$dest" -name '*.part' -delete
  install -m 0644 "$PAYLOADS/tutor-blobs.json" "$ROOTFS/usr/share/kirin/tutor-blobs.json"
  [ -f "$r/kiwix.list" ] || : > "$r/kiwix.list"
  python3 - "$ROOTFS/usr/share/kirin/russian.json" "$TUTOR_TAG" "$RUSSIAN_DIR" "$(cat "$r/dictionary.name")" "$r/kiwix.list" <<'PY'
import json, sys
out, model, root, zim, listing = sys.argv[1:]
kiwix = {'wiktionary': f'{root}/dictionary/{zim}'}
for line in open(listing, encoding='utf-8'):
    if '\t' in line:
        key, name = line.rstrip('\n').split('\t', 1)
        kiwix[key] = f'{root}/dictionary/{name}'
json.dump({'model': model, 'root': root, 'piper': '/opt/kirin/piper/piper',
           'voices': root + '/voices', 'library': root + '/library',
           'dictionary': f'{root}/dictionary/{zim}', 'kiwix': kiwix,
           'audiobooks': root + '/audiobooks', 'mezhdunami': root + '/mezhdunami',
           'vocab': '/usr/share/kirin/russian/vocab.tsv'}, open(out, 'w'), indent=2)
PY
}

audit_russian() {
  if [ "$NO_RUSSIAN" -eq 1 ]; then echo 'skipped (--no-russian)'; return 0; fi
  local dest="$ROOTFS$RUSSIAN_DIR" ok=0
  python3 "$REPO/scripts/build/qwen-index.py" --models "$ROOTFS/usr/share/ollama/.ollama/models" \
      --tag "$TUTOR_TAG" --out "$WORK/tutor-blobs.check" || ok=1
  [ -x "$ROOTFS/opt/kirin/piper/piper" ] || { echo 'Piper missing'; ok=1; }
  (cd "$dest/voices" && sha256sum --quiet -c SHA256SUMS) || ok=1
  [ "$(grep -cs '\.onnx$' "$dest/voices/SHA256SUMS")" = 4 ] || { echo 'expected four Russian voices'; ok=1; }
  # The course library is optional (its sources may move); verify whatever was fetched.
  if [ -s "$dest/library/SHA256SUMS" ]; then (cd "$dest/library" && sha256sum --quiet -c SHA256SUMS) || ok=1; fi
  echo "library: $(cat "$dest/library/SHA256SUMS" 2>/dev/null | wc -l) files"
  ls "$dest/dictionary/"*.zim >/dev/null 2>&1 || { echo 'Wiktionary ZIM missing'; ok=1; }
  echo "reading: $(cut -f1 "$PAYLOADS/russian/kiwix.list" 2>/dev/null | tr '\n' ' ')"
  # Audiobooks and the Между нами copy are optional; whatever is there must be intact.
  local part
  for part in audiobooks mezhdunami; do
    if [ -s "$dest/$part/SHA256SUMS" ]; then
      (cd "$dest/$part" && sha256sum --quiet -c SHA256SUMS) || ok=1
      echo "$part: $(wc -l < "$dest/$part/SHA256SUMS") files"
    else
      echo "$part: not included"
    fi
  done
  [ -f "$ROOTFS/usr/share/kirin/russian/vocab.tsv" ] || { echo 'Russian word list missing'; ok=1; }
  [ -f "$ROOTFS/usr/share/kirin/russian.json" ] || { echo 'russian.json missing'; ok=1; }
  return "$ok"
}

# simulate_and_purge NAME PKG...: purge PKGs only if the simulated transaction passes review.
simulate_and_purge() {
  local name=$1; shift
  in_chroot simulate-purge "$@" > "$AUDIT/purge-$name.txt"
  python3 "$REPO/scripts/build/check-removal.py" --requested "$@" \
      --allow "${ALLOW_REMOVAL[@]}" --model-owners "$UPSTREAM/upstream-models-owners.json" \
      < "$AUDIT/purge-$name.txt" || return 1
  in_chroot purge "$@"
}

purge_reviewed() {
  local -a wanted required optional installed
  mapfile -t wanted < <(pkglist "$HERE/remove-packages.txt")
  local p
  for p in "${wanted[@]}"; do
    case "$p" in *\?) optional+=("${p%\?}") ;; *) required+=("$p") ;; esac
  done
  mapfile -t installed < <(in_chroot installed "${required[@]}")
  if [ ${#installed[@]} -gt 0 ]; then
    info "requested purge: ${installed[*]}"
    simulate_and_purge required "${installed[@]}" || die "purge refused; inspect $AUDIT/purge-required.txt"
  else
    info 'none of the listed account/store packages are installed'
  fi
  for p in "${optional[@]}"; do
    [ -n "$(in_chroot installed "$p")" ] || continue
    info "optional purge: $p"
    simulate_and_purge "$p" "$p" ||
      info "KEPT $p: removing it would take other packages with it; see $AUDIT/purge-$p.txt"
  done
}

stage_customise() {
  log 'Customising the image'
  [ -f "$PAYLOADS/qwen-blobs.json" ] || die 'run the payloads stage first'
  # Payloads added after a first run (e.g. the libfyaml source) are fetched here.
  [ -f "$PAYLOADS/libfyaml-$FYAML_VERSION.tar.gz" ] || fetch_libfyaml
  [ "$NO_RUSSIAN" -eq 1 ] || [ -f "$PAYLOADS/russian/dictionary.name" ] || fetch_russian
  [ "$NO_EXTRA_REPOS" -eq 1 ] || [ -f "$PAYLOADS/kirin-debian.gpg" ] || fetch_debian_keys
  [ -d "$PAYLOADS/proton" ] || fetch_proton
  fetch_kirin_key
  local olroot="$PAYLOADS/ollama-$OLLAMA_VERSION/root"

  # Language policy first, so dpkg path-exclusions apply to packages installed next.
  python3 "$REPO/scripts/kirin-localise.py" --root "$ROOTFS" --apply ||
    info 'language tool reported problems; the audit stage will show them'
  DESTDIR="$ROOTFS" sh "$REPO/scripts/stage-account-policy.sh"

  mount_chroot
  info 'installing base packages'; in_chroot install
  info 'removing Token Centre, Software Store, Kylin ID, WPS Office and the openKylin AI assistant app'; purge_reviewed
  in_chroot cleanup-removed | sed 's/^/    /'
  if [ "$NO_EXTRA_REPOS" -eq 0 ]; then
    info 'adding pinned Ubuntu 26.04 and Debian 13 repositories'
    in_chroot extra-repos | tee "$AUDIT/extra-repos.log" | sed 's/^/    /'
  fi
  info 'installing extra packages (LibreOffice, VLC, Fastfetch and others)'
  in_chroot install-extras | tee "$AUDIT/extra-packages.log" | sed 's/^/    /'
  if [ "$NO_EXTRA_REPOS" -eq 0 ]; then
    info 'taking newer hardware data (audio profiles, microcode) from Ubuntu 26.04 where it is newer'
    in_chroot prefer-ubuntu | tee "$AUDIT/prefer-ubuntu.log" | sed 's/^/    /'
  fi
  info "building and installing Kirin's own packages (ani-cli)"
  in_chroot kirin-debs | tee "$AUDIT/kirin-debs.log" | sed 's/^/    /'
  info 'installing Proton VPN, Pass and Mail (official packages)'
  in_chroot proton | tee "$AUDIT/proton.log" | sed 's/^/    /'
  if [ "$NO_EXTRA_REPOS" -eq 0 ]; then
    in_chroot pin-extras > "$AUDIT/pin-extras.log"; info "$(tail -1 "$AUDIT/pin-extras.log")"
  fi
  info 'installing Flatpak apps system-wide (Warehouse, Flatseal, Kiwix, Alpaca, Discord, Sober)'
  in_chroot flatpak "$RUSSIAN_DIR"
  local chat_model=$QWEN_TAG
  [ "$NO_RUSSIAN" -eq 1 ] || chat_model=$TUTOR_TAG
  python3 "$REPO/scripts/build/seed-alpaca.py" --root "$ROOTFS" --model "$chat_model" | sed 's/^/    /'

  info 'installing Ollama and the coding model'
  install -d -m 0755 "$ROOTFS/usr/local/bin" "$ROOTFS/usr/local/lib"
  install -m 0755 "$olroot/bin/ollama" "$ROOTFS/usr/local/bin/ollama"
  rm -rf "$ROOTFS/usr/local/lib/ollama"
  [ ! -d "$olroot/lib/ollama" ] || cp -a "$olroot/lib/ollama" "$ROOTFS/usr/local/lib/ollama"
  install -D -m 0644 "$REPO/packaging/systemd/ollama.service" "$ROOTFS/etc/systemd/system/ollama.service"
  local dest="$ROOTFS/usr/share/ollama/.ollama/models"
  rm -rf "$dest"; mkdir -p "$dest"
  cp -al "$PAYLOADS/models/." "$dest/" 2>/dev/null || cp -a "$PAYLOADS/models/." "$dest/"
  install -D -m 0644 "$PAYLOADS/qwen-blobs.json" "$ROOTFS/usr/share/kirin/qwen-blobs.json"
  install -D -m 0644 "$UPSTREAM/upstream-models.json" "$ROOTFS/usr/share/kirin/upstream-models.json"

  install_russian

  info 'installing Kirin Learn'
  DESTDIR="$ROOTFS" sh "$REPO/scripts/install-education.sh"

  info 'applying Kirin branding'
  python3 "$REPO/scripts/kirin-rebrand.py" --root "$ROOTFS" --apply | sed 's/^/    /'
  info 'applying Kirin defaults (version, hostname, default apps, taskbar, Fastfetch)'
  python3 "$REPO/scripts/kirin-polish.py" --root "$ROOTFS" --apply | tee "$AUDIT/defaults.log" | sed 's/^/    /'

  in_chroot finish | tee "$AUDIT/finish.log"
  in_chroot manifest > "$WORK/filesystem.manifest"
  restore_chroot

  # Packages installed above can bring back translated menu keys and Kylin names.
  python3 "$REPO/scripts/kirin-localise.py" --root "$ROOTFS" --apply ||
    info 'language tool reported problems; the audit stage will show them'
  python3 "$REPO/scripts/kirin-rebrand.py" --root "$ROOTFS" --apply >/dev/null
  prepare_live_initrd
  info 'customisation complete'
}

stage_audit() {
  log 'Auditing the staged image'
  [ ! -e "$ROOTFS/kirin-build" ] || die 'build chroot files still present; re-run customise'
  local summary="$AUDIT/summary" failed=0 name
  : > "$summary"
  run_audit() {
    name=$1; shift
    if "$@" > "$AUDIT/$name.log" 2>&1; then
      echo "PASS $name" >> "$summary"; info "PASS  $name"
    else
      echo "FAIL $name" >> "$summary"; info "FAIL  $name (see $AUDIT/$name.log)"; failed=1
    fi
  }
  run_audit ai-payload python3 "$REPO/scripts/check-image-contract.py" \
      --upstream-inventory "$UPSTREAM/upstream-models.json" --candidate-root "$ROOTFS" \
      --qwen-index "$PAYLOADS/qwen-blobs.json" --qwen-blobs "$ROOTFS/usr/share/ollama/.ollama/models/blobs"
  run_audit software python3 "$REPO/scripts/audit-software-image.py" --root "$ROOTFS"
  run_audit language python3 "$REPO/scripts/kirin-localise.py" --root "$ROOTFS" --audit
  run_audit accounts python3 "$REPO/scripts/audit-online-accounts.py" --root "$ROOTFS"
  run_audit russian audit_russian
  run_audit branding python3 "$REPO/scripts/kirin-rebrand.py" --root "$ROOTFS" --audit
  run_audit defaults python3 "$REPO/scripts/kirin-polish.py" --root "$ROOTFS" --audit
  grep -q '^FAIL ai-payload' "$summary" && die 'AI payload contract failed; this is never waived'
  if [ "$failed" -eq 1 ] && [ "$TEST_BUILD" -ne 1 ]; then
    die 'policy audits failed; fix them, or pass --test-build for an unverified test image'
  fi
  return 0
}

stage_pack() {
  log 'Packing the root filesystem and ISO'
  [ -s "$AUDIT/summary" ] || die 'run the audit stage first'
  if grep -q '^FAIL' "$AUDIT/summary" && [ "$TEST_BUILD" -ne 1 ]; then die 'audits failed; refusing to pack'; fi
  SQUASHFS_REL=$(cat "$UPSTREAM/squashfs.path")
  local comp bs
  comp=$(sed -n 's/^Compression //p' "$UPSTREAM/squashfs.info")
  bs=$(sed -n 's/^Block size //p' "$UPSTREAM/squashfs.info")
  local sq="$WORK/filesystem.squashfs"
  rm -f "$sq"
  mksquashfs "$ROOTFS" "$sq" -noappend -comp "${comp:-xz}" ${bs:+-b "$bs"} -wildcards \
    -e 'proc/*' 'sys/*' 'dev/*' 'run/*' 'tmp/*'

  local -a maps=(-map "$sq" "/$SQUASHFS_REL")
  local stem="${SQUASHFS_REL%.squashfs}"
  if [ -f "$ISOTREE/$stem.size" ]; then
    du -sx --block-size=1 "$ROOTFS" | cut -f1 > "$WORK/filesystem.size"
    maps+=(-map "$WORK/filesystem.size" "/$stem.size")
  fi
  if [ -f "$ISOTREE/$stem.manifest" ]; then
    maps+=(-map "$WORK/filesystem.manifest" "/$stem.manifest")
  fi
  local -a md5pairs=("$sq=/$SQUASHFS_REL" "$WORK/filesystem.size=/$stem.size" "$WORK/filesystem.manifest=/$stem.manifest")
  if [ -f "$WORK/live-initrd" ] && [ -s "$WORK/live-initrd.path" ]; then
    local initrd_rel; initrd_rel=$(cat "$WORK/live-initrd.path")
    maps+=(-map "$WORK/live-initrd" "/$initrd_rel")
    md5pairs+=("$WORK/live-initrd=/$initrd_rel")
    info "live session gets the Kirin boot splash ($initrd_rel)"
  fi
  # Kirin boot menus: British English locale, Kirin names and artwork (scripts/build/iso-boot-config.py).
  local boot="$WORK/iso-boot" rel
  python3 "$REPO/scripts/build/iso-boot-config.py" --iso-tree "$ISOTREE" --out "$boot" \
      --grub-background /boot/grub/kirin-background.png > "$WORK/iso-boot.list"
  while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    maps+=(-map "$boot/$rel" "/$rel"); md5pairs+=("$boot/$rel=/$rel")
    info "boot menu updated: $rel"
  done < "$WORK/iso-boot.list"
  maps+=(-map "$REPO/packaging/branding/grub-background.png" /boot/grub/kirin-background.png)
  local art
  for art in isolinux/splash.png:isolinux-splash.png isolinux/back.jpg:isolinux-back.jpg; do
    if [ -f "$ISOTREE/${art%%:*}" ]; then
      maps+=(-map "$REPO/packaging/branding/${art##*:}" "/${art%%:*}")
      md5pairs+=("$REPO/packaging/branding/${art##*:}=/${art%%:*}")
    fi
  done
  local sums
  for sums in md5sum.txt SHA256SUMS; do
    [ -f "$ISOTREE/$sums" ] || continue
    python3 - "$ISOTREE/$sums" "$WORK/$sums" "${md5pairs[@]}" <<'PY'
import hashlib, re, sys
from pathlib import Path
src, out, *pairs = sys.argv[1:]
algo = 'sha256' if 'SHA256' in Path(src).name.upper() else 'md5'
digests = {}
for pair in pairs:
    local, iso = pair.split('=', 1)
    if Path(local).is_file():
        h = hashlib.new(algo)
        with open(local, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''): h.update(chunk)
        digests[iso.lstrip('/')] = h.hexdigest()
lines = []
for line in Path(src).read_text(errors='replace').splitlines():
    m = re.match(r'^([0-9a-fA-F]+)( [ *])(.*)$', line)
    key = m.group(3).removeprefix('./').lstrip('/') if m else None
    lines.append(f'{digests[key]}{m.group(2)}{m.group(3)}' if m and key in digests else line)
Path(out).write_text('\n'.join(lines) + '\n')
PY
    maps+=(-map "$WORK/$sums" "/$sums")
  done

  # Name and date only; failed audits are recorded in the .build.json and printed below.
  local stamp; stamp=$(date -u +%Y%m%d)
  local iso_out="$OUT/kirin-$stamp-amd64.iso"
  rm -f "$iso_out"
  xorriso -indev "$ISO" -outdev "$iso_out" -boot_image any replay \
    -compliance iso_9660_level=3 "${maps[@]}" -end
  (cd "$OUT" && sha256sum "$(basename "$iso_out")" > "$(basename "$iso_out").sha256")

  python3 - "$OUT/$(basename "$iso_out" .iso).build.json" "$UPSTREAM/iso.json" "$AUDIT/summary" \
      "$iso_out" "$OLLAMA_VERSION" "$TEST_BUILD" <<'PY'
import hashlib, json, sys
out, upstream, summary, iso, ollama, test = sys.argv[1:]
record = {
    'upstream_iso': json.load(open(upstream)),
    'output': iso.rsplit('/', 1)[-1],
    'sha256': open(iso + '.sha256').read().split()[0],
    'ollama': ollama, 'coding_model': 'qwen2.5-coder:7b-instruct',
    'audits': dict(reversed(l.split()) for l in open(summary) if l.strip()),
    'test_build': test == '1',
    'not_yet_implemented': ['OpenZFS root and ZFSBootMenu', 'systemd birthDate removal',
                            'MX Package Installer port', 'Web App Studio', 'Kirin branding'],
}
json.dump(record, open(out, 'w'), indent=2)
PY
  log "Built $iso_out"
  info "$(cut -d' ' -f1 "$iso_out.sha256")"
  if grep -q '^FAIL' "$AUDIT/summary"; then
    info "audits that did not pass: $(awk '$1 == "FAIL" {print $2}' "$AUDIT/summary" | tr '\n' ' ')(see $AUDIT)"
  fi
  local bytes; bytes=$(stat -c %s "$iso_out")
  info "size: $((bytes / 1000000000)) GB ($bytes bytes)"
  # A "64 GB" USB stick holds about 61.5 GB, less Ventoy's own partition.
  if [ "$bytes" -gt 61000000000 ]; then
    info 'WARNING: this ISO will not fit a 64 GB USB stick. Rebuild the Russian extras smaller, for example:'
    info "  sudo $0 --iso '$ISO' --from payloads --accept-inventory --ru-wikipedia none"
  fi
}

# The live session boots from the ISO's own initrd, not the image's. If the
# rebuilt initramfs (with the Kirin splash) is for the same kernel the ISO
# boots and contains casper's live-boot scripts, use it for the ISO too.
prepare_live_initrd() {
  rm -f "$WORK/live-initrd" "$WORK/live-initrd.path"
  local -a ok vmlinuz initrds
  mapfile -t ok < <(sed -n 's/^CASPER_INITRD //p' "$AUDIT/finish.log")
  mapfile -t vmlinuz < <(find "$ISOTREE/casper" -maxdepth 1 -type f -name 'vmlinuz*' 2>/dev/null)
  mapfile -t initrds < <(find "$ISOTREE/casper" -maxdepth 1 -type f -name 'initrd*' 2>/dev/null)
  if [ ${#vmlinuz[@]} -ne 1 ] || [ ${#initrds[@]} -ne 1 ]; then
    info "keeping openKylin's live initrd: expected one casper/vmlinuz and one casper/initrd"; return 0
  fi
  local v
  for v in "${ok[@]}"; do
    if cmp -s "${vmlinuz[0]}" "$ROOTFS/boot/vmlinuz-$v"; then
      cp "$ROOTFS/boot/initrd.img-$v" "$WORK/live-initrd"
      printf '%s\n' "${initrds[0]#"$ISOTREE"/}" > "$WORK/live-initrd.path"
      info "rebuilt live initrd for kernel $v"
      return 0
    fi
  done
  info "keeping openKylin's live initrd: no rebuilt live-capable initramfs matches the ISO kernel"
}

# ---------------------------------------------------------------- driver
valid_stage() { local s; for s in "${STAGES[@]}"; do [ "$s" = "$1" ] && return 0; done; return 1; }
[ -z "$FROM" ] || valid_stage "$FROM" || die "unknown stage: $FROM"
[ -z "$ONLY" ] || valid_stage "$ONLY" || die "unknown stage: $ONLY"

if [ -n "$FROM" ]; then
  # Redoing a stage invalidates it and everything after it.
  drop=0; for s in "${STAGES[@]}"; do [ "$s" = "$FROM" ] && drop=1; [ "$drop" -eq 1 ] && rm -f "$WORK/.done-$s"; done
fi

for s in "${STAGES[@]}"; do
  if [ -n "$ONLY" ] && [ "$s" != "$ONLY" ] && [ "$s" != preflight ]; then continue; fi
  if [ -z "$ONLY" ] && [ "$s" != preflight ] && [ -f "$WORK/.done-$s" ]; then
    info "skipping $s (done; use --from $s to redo)"; continue
  fi
  "stage_$s"
  touch "$WORK/.done-$s"
  if [ -n "$ONLY" ] && [ "$s" = "$ONLY" ]; then
    after=0; for t in "${STAGES[@]}"; do [ "$after" -eq 1 ] && rm -f "$WORK/.done-$t"; [ "$t" = "$s" ] && after=1; done
  fi
done
