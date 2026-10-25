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

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd -- "$HERE/.." && pwd)
STAGES=(preflight verify extract inventory payloads customise audit pack)
QWEN_TAG='qwen2.5-coder:7b-instruct'
OLLAMA_VERSION_DEFAULT='v0.40.11'
# Kirin compatibility build of libfyaml0 (see build/chroot-steps.sh compat_libfyaml).
FYAML_VERSION='0.9.6'
FYAML_SHA256=${KIRIN_TEST_FYAML_SHA256:-a59cc3331e2eb903ec36933ad52a45888041cac31e44f553a00511131242c483}
MIN_FREE_GB=${KIRIN_MIN_FREE_GB:-70}

ISO='' ISO_SHA256='' WORK="$PWD/work" OUT="$PWD/out" SQUASHFS_REL=''
MODEL_INVENTORY='' ACCEPT_INVENTORY=0 TEST_BUILD=0 FROM='' ONLY=''
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
  --test-build            Produce an ISO even if policy audits fail; named TEST-UNVERIFIED.
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
  install -m 0644 "$REPO/packaging/base-packages.txt" "$REPO/packaging/flatpak-apps.txt" "$ROOTFS/kirin-build/"
  [ ! -f "$PAYLOADS/libfyaml-$FYAML_VERSION.tar.gz" ] ||
    install -m 0644 "$PAYLOADS/libfyaml-$FYAML_VERSION.tar.gz" "$ROOTFS/kirin-build/"
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
  local free_gb; free_gb=$(df --output=avail -BG "$WORK" | tail -1 | tr -dc 0-9)
  [ "$free_gb" -ge "$MIN_FREE_GB" ] || die "need ${MIN_FREE_GB} GB free under $WORK, have ${free_gb} GB"
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
    python3 "$REPO/scripts/build/inventory-models.py" --root "$ROOTFS" --out "$inv" --owners-out "$owners" || rc=$?
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

pull_qwen() {
  local models="$PAYLOADS/models" index="$PAYLOADS/qwen-blobs.json"
  local bin="$PAYLOADS/ollama-$OLLAMA_VERSION/root/bin/ollama"
  if [ -f "$index" ] && python3 "$REPO/scripts/build/qwen-index.py" --models "$models" --out "$index.check" >/dev/null 2>&1; then
    rm -f "$index.check"; info "$QWEN_TAG already present and verified"; return
  fi
  mkdir -p "$models"
  info "pulling $QWEN_TAG (about 4.7 GB)"
  OLLAMA_MODELS="$models" OLLAMA_HOST=127.0.0.1:11435 "$bin" serve >"$PAYLOADS/ollama-serve.log" 2>&1 &
  OLLAMA_PID=$!
  local i
  for i in $(seq 60); do
    OLLAMA_HOST=127.0.0.1:11435 "$bin" list >/dev/null 2>&1 && break
    kill -0 "$OLLAMA_PID" 2>/dev/null || die "ollama serve exited; see $PAYLOADS/ollama-serve.log"
    sleep 1
  done
  OLLAMA_HOST=127.0.0.1:11435 "$bin" pull "$QWEN_TAG"
  kill "$OLLAMA_PID"; wait "$OLLAMA_PID" 2>/dev/null || true; OLLAMA_PID=''
  python3 "$REPO/scripts/build/qwen-index.py" --models "$models" --tag "$QWEN_TAG" --out "$index"
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

stage_payloads() {
  log 'Fetching payloads: Ollama runtime, Qwen2.5-Coder 7B and compatibility sources'
  fetch_ollama
  pull_qwen
  fetch_libfyaml
}

purge_reviewed() {
  local -a wanted installed
  mapfile -t wanted < <(pkglist "$HERE/remove-packages.txt")
  mapfile -t installed < <(in_chroot installed "${wanted[@]}")
  if [ ${#installed[@]} -eq 0 ]; then
    info 'none of the listed account/store packages are installed'; return
  fi
  info "requested purge: ${installed[*]}"
  in_chroot simulate-purge "${installed[@]}" > "$AUDIT/purge-simulation.txt"
  python3 "$REPO/scripts/build/check-removal.py" --requested "${installed[@]}" \
      --allow "${ALLOW_REMOVAL[@]}" --model-owners "$UPSTREAM/upstream-models-owners.json" \
      < "$AUDIT/purge-simulation.txt" ||
    die "purge refused; inspect $AUDIT/purge-simulation.txt"
  in_chroot purge "${installed[@]}"
}

stage_customise() {
  log 'Customising the image'
  [ -f "$PAYLOADS/qwen-blobs.json" ] || die 'run the payloads stage first'
  # Payloads added after a first run (e.g. the libfyaml source) are fetched here.
  [ -f "$PAYLOADS/libfyaml-$FYAML_VERSION.tar.gz" ] || fetch_libfyaml
  local olroot="$PAYLOADS/ollama-$OLLAMA_VERSION/root"

  # Language policy first, so dpkg path-exclusions apply to packages installed next.
  python3 "$REPO/scripts/kirin-localise.py" --root "$ROOTFS" --apply ||
    info 'language tool reported problems; the audit stage will show them'
  DESTDIR="$ROOTFS" sh "$REPO/scripts/stage-account-policy.sh"

  mount_chroot
  info 'installing base packages'; in_chroot install
  info 'removing Token Centre and Software Store'; purge_reviewed
  info 'installing Warehouse and Flatseal system-wide'; in_chroot flatpak

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

  info 'installing Kirin Learn'
  DESTDIR="$ROOTFS" sh "$REPO/scripts/install-education.sh"

  in_chroot finish
  in_chroot manifest > "$WORK/filesystem.manifest"
  restore_chroot

  # Packages installed above can bring back translated menu keys.
  python3 "$REPO/scripts/kirin-localise.py" --root "$ROOTFS" --apply ||
    info 'language tool reported problems; the audit stage will show them'
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
  if [ -f "$ISOTREE/md5sum.txt" ]; then
    python3 - "$ISOTREE/md5sum.txt" "$WORK/md5sum.txt" "$sq=/$SQUASHFS_REL" \
        "$WORK/filesystem.size=/$stem.size" "$WORK/filesystem.manifest=/$stem.manifest" <<'PY'
import hashlib, sys
from pathlib import Path
src, out, *pairs = sys.argv[1:]
changed = {}
for pair in pairs:
    local, iso = pair.split('=', 1)
    if Path(local).is_file():
        h = hashlib.md5()
        with open(local, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''): h.update(chunk)
        changed['.' + iso] = h.hexdigest()
lines = []
for line in Path(src).read_text().splitlines():
    digest, _, name = line.partition('  ')
    lines.append(f'{changed[name]}  {name}' if name in changed else line)
Path(out).write_text('\n'.join(lines) + '\n')
PY
    maps+=(-map "$WORK/md5sum.txt" /md5sum.txt)
  fi

  local label='' stamp; stamp=$(date -u +%Y%m%d)
  grep -q '^FAIL' "$AUDIT/summary" && label='-TEST-UNVERIFIED'
  local iso_out="$OUT/kirin-$stamp-amd64$label.iso"
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
