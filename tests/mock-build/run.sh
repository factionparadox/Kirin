#!/usr/bin/env bash
# End-to-end smoke test of build/kirin-build.sh's orchestration, review gates
# and audits, using stub xorriso/squashfs/chroot/mount tools and a fake image.
# Builds nothing real. Needs root (the builder insists on it) and ~1 GB of
# disk; the 4 GB "model" blob is sparse.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "$0")" && pwd)
REPO=$(cd -- "$HERE/../.." && pwd)
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
export PATH="$HERE/stubs:$PATH" KIRIN_MIN_FREE_GB=1 MOCK_STATE="$T/state"
mkdir -p "$MOCK_STATE"

fail() { echo "MOCK BUILD FAILED: $*" >&2; exit 1; }

head -c 1048576 /dev/urandom > "$T/upstream.iso"
sha=$(sha256sum "$T/upstream.iso" | cut -d' ' -f1)
run() { "$REPO/build/kirin-build.sh" --iso "$T/upstream.iso" --iso-sha256 "$sha" --work "$T/work" --out "$T/out" "$@"; }

# Pre-seed payloads so no network is needed: fake Ollama and a sparse >4 GB model.
P="$T/work/payloads"; ver=v0.40.11
mkdir -p "$P/ollama-$ver/root/bin" "$P/models/blobs" "$P/models/manifests/registry.ollama.ai/library/qwen2.5-coder"
printf '#!/bin/sh\necho fake ollama\n' > "$P/ollama-$ver/root/bin/ollama"; chmod +x "$P/ollama-$ver/root/bin/ollama"
truncate -s 4100000000 "$T/weights"
wsha=$(sha256sum "$T/weights" | cut -d' ' -f1); mv "$T/weights" "$P/models/blobs/sha256-$wsha"
printf '{}' > "$T/cfg"; csha=$(sha256sum "$T/cfg" | cut -d' ' -f1); mv "$T/cfg" "$P/models/blobs/sha256-$csha"
cat > "$P/models/manifests/registry.ollama.ai/library/qwen2.5-coder/7b-instruct" <<EOF
{"config":{"digest":"sha256:$csha","size":2},"layers":[{"digest":"sha256:$wsha","size":4100000000,"mediaType":"application/vnd.ollama.image.model"}]}
EOF
python3 "$REPO/scripts/build/qwen-index.py" --models "$P/models" --out "$P/qwen-blobs.json" >/dev/null

echo '--- 1. wrong checksum is refused'
if "$REPO/build/kirin-build.sh" --iso "$T/upstream.iso" --iso-sha256 "$(printf '0%.0s' {1..64})" \
     --work "$T/work" --out "$T/out" >/dev/null 2>&1; then fail 'bad checksum accepted'; fi

echo '--- 2. first run stops for inventory review'
set +e; run > "$T/log1" 2>&1; rc=$?; set -e
[ "$rc" -eq 10 ] || { cat "$T/log1"; fail "expected review stop (10), got $rc"; }
grep -q 'opt/kylin-ai/asr.onnx' "$T/work/upstream/upstream-models.json" || fail 'model not inventoried'
[ ! -e "$T/work/.done-customise" ] || fail 'image modified before review'

echo '--- 3. unrequested removal blocks the purge'
touch "$MOCK_STATE/extra-removal"
set +e; run --from inventory --accept-inventory > "$T/log2" 2>&1; rc=$?; set -e
[ "$rc" -ne 0 ] && grep -q 'unrequested removal: openkylin-desktop-meta' "$T/log2" || { cat "$T/log2"; fail 'extra removal not refused'; }
grep -q 'Status: install ok installed' <(grep -A1 'Package: openkylin-token-center' "$T/work/rootfs/var/lib/dpkg/status") ||
  fail 'package purged despite refusal'

echo '--- 4. reviewed allowance lets the build finish'
run --from customise --accept-inventory --allow-removal openkylin-desktop-meta > "$T/log3" 2>&1 || { cat "$T/log3"; fail 'build failed'; }
iso=$(ls "$T"/out/kirin-*-amd64.iso)
case "$iso" in *TEST-UNVERIFIED*) fail 'clean build labelled as test' ;; esac
grep -q 'map .*filesystem.squashfs /casper/filesystem.squashfs' "$iso" || fail 'squashfs not mapped into ISO'
grep -q 'boot_image any replay' "$iso" || fail 'boot records not replayed'
python3 - "$T/out" "$T/work" <<'PY' || fail 'output checks'
import glob, hashlib, json, sys
out, work = sys.argv[1:]
rec = json.load(open(glob.glob(out + '/*.build.json')[0]))
assert all(v == 'PASS' for v in rec['audits'].values()), rec['audits']
md5 = dict(reversed(l.split('  ', 1)) for l in open(work + '/md5sum.txt').read().splitlines())
assert md5['./casper/filesystem.squashfs'] == hashlib.md5(open(work + '/filesystem.squashfs', 'rb').read()).hexdigest()
assert md5['./boot/grub/grub.cfg'] == 'aaaa'
PY
R="$T/work/rootfs"
[ ! -e "$R/kirin-build" ] && [ ! -e "$R/usr/sbin/policy-rc.d" ] || fail 'build scaffolding left in image'
[ "$(readlink "$R/etc/resolv.conf")" = ../run/systemd/resolve/stub-resolv.conf ] || fail 'resolv.conf not restored'
[ -x "$R/usr/local/bin/ollama" ] && [ -f "$R/etc/systemd/system/ollama.service" ] && [ -x "$R/usr/bin/kirin-learn" ] ||
  fail 'payloads not installed'
grep -q 'Package: openkylin-token-center' "$R/var/lib/dpkg/status" && fail 'token centre still installed'

echo '--- 5. a policy failure blocks release but allows a labelled test build'
printf 'Name[zh_CN]=Files-zh\n' >> "$R/usr/share/applications/files.desktop"
if run --only audit > "$T/log5" 2>&1; then fail 'language failure not caught'; fi
run --only audit --test-build > "$T/log5" 2>&1 || { cat "$T/log5"; fail 'test build audit refused'; }
run --only pack --test-build > "$T/log5" 2>&1 || { cat "$T/log5"; fail 'test build pack refused'; }
ls "$T"/out/kirin-*-amd64-TEST-UNVERIFIED.iso >/dev/null || fail 'test build not labelled'

echo '--- 6. tampering with an upstream model is never waived'
echo tamper >> "$R/opt/kylin-ai/asr.onnx"
set +e; run --only audit --test-build > "$T/log4" 2>&1; rc=$?; set -e
[ "$rc" -ne 0 ] && grep -q 'never waived' "$T/log4" || { cat "$T/log4"; fail 'model tamper not caught'; }

echo 'MOCK BUILD PASSED'
