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
export MOCK_GRUB="$REPO/tests/fixtures/openkylin-3.0-grub.cfg"
export PATH="$HERE/stubs:$PATH" KIRIN_MIN_FREE_GB=1 MOCK_STATE="$T/state" KIRIN_TEST_WRAP=65536
mkdir -p "$MOCK_STATE"

fail() { echo "MOCK BUILD FAILED: $*" >&2; exit 1; }

# A fake ISO holding a fake root squashfs larger than the (scaled-down) wrap
# size, so extraction cuts it short exactly as openKylin 3.0's 7.5 GB one does.
python3 - "$T/upstream.iso" "$MOCK_STATE/squashfs.full" <<'EOF'
import os, struct, sys
size = 300 * 1024
sq = bytearray(os.urandom(size)); sq[:4] = b'hsqs'; struct.pack_into('<Q', sq, 40, size)
open(sys.argv[2], 'wb').write(sq)
open(sys.argv[1], 'wb').write(os.urandom(40 * 2048) + sq + os.urandom(7000))
EOF
sha=$(sha256sum "$T/upstream.iso" | cut -d' ' -f1)
ZIM=wiktionary_en_all_nopic_2026-09.zim
run() { "$REPO/build/kirin-build.sh" --iso "$T/upstream.iso" --iso-sha256 "$sha" --work "$T/work" --out "$T/out" \
          --kiwix-name "$ZIM" --content bundled "$@"; }

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
printf 'fake libfyaml source' > "$P/libfyaml-0.9.6.tar.gz"

# Russian extras, served from local files instead of the internet.
tag_dir="$P/models/manifests/registry.ollama.ai/library/qwen3"; mkdir -p "$tag_dir"
printf 'tutor weights' > "$T/tw"; tsha=$(sha256sum "$T/tw" | cut -d' ' -f1); mv "$T/tw" "$P/models/blobs/sha256-$tsha"
printf '{"layers":[{"digest":"sha256:%s","size":13}]}' "$tsha" > "$tag_dir/30b-a3b-instruct-2507-q4_K_M"
mkdir -p "$P/piper-2023.11.14-2/root/piper"
printf '#!/bin/sh\n' > "$P/piper-2023.11.14-2/root/piper/piper"; chmod +x "$P/piper-2023.11.14-2/root/piper/piper"
SITE="$T/site"; mkdir -p "$SITE"
: > "$T/voices.tsv"
for v in irina denis dmitri ruslan; do
  for ext in onnx onnx.json; do
    printf 'voice %s %s' "$v" "$ext" > "$SITE/ru_RU-$v-medium.$ext"
    printf 'ru_RU-%s-medium.%s\tfile://%s/ru_RU-%s-medium.%s\n' "$v" "$ext" "$SITE" "$v" "$ext" >> "$T/voices.tsv"
  done
done
printf 'textbook' > "$SITE/book.pdf"
printf 'DLI Russian Basic Course/Mod 01.pdf\tfile://%s/book.pdf\nDLI Russian Basic Course/Gone.pdf\tfile://%s/missing.pdf\n' \
  "$SITE" "$SITE" > "$T/library.tsv"
printf 'dictionary' > "$SITE/$ZIM"; printf '%s  %s\n' "$(sha256sum "$SITE/$ZIM" | cut -d' ' -f1)" "$ZIM" > "$SITE/$ZIM.sha256"
# Extra reading ZIMs: Wikisource is published, the Russian Wiktionary and Wikipedia are not.
WS=wikisource_ru_all_nopic_2019-08.zim; mkdir -p "$SITE/zim/wikisource"
printf 'literature' > "$SITE/zim/wikisource/$WS"
printf '%s  %s\n' "$(sha256sum "$SITE/zim/wikisource/$WS" | cut -d' ' -f1)" "$WS" > "$SITE/zim/wikisource/$WS.sha256"
printf '<a href="%s">%s</a>\n' "$WS" "$WS" > "$SITE/zim/wikisource/index.html"
# Audiobooks: one published item and one that has gone.
mkdir -p "$SITE/archive/metadata" "$SITE/archive/download/testbook"
printf 'track one' > "$SITE/archive/download/testbook/t01_64kb.mp3"
python3 - "$SITE/archive/metadata/testbook" "$SITE/archive/download/testbook/t01_64kb.mp3" <<'PY'
import hashlib, json, sys
data = open(sys.argv[2], 'rb').read()
json.dump({'metadata': {'title': 'Сказки', 'creator': 'Afanasyev', 'language': 'rus', 'runtime': '0:01'},
           'files': [{'name': 't01_64kb.mp3', 'format': '64Kbps MP3', 'md5': hashlib.md5(data).hexdigest(),
                      'sha1': hashlib.sha1(data).hexdigest()}]}, open(sys.argv[1], 'w'))
PY
printf 'testbook\tA2\ngonebook\tB1\n' > "$T/audiobooks.tsv"
export KIRIN_TEST_AUDIOBOOKS_TSV="$T/audiobooks.tsv" KIRIN_TEST_ARCHIVE_BASE="file://$SITE/archive/"
export KIRIN_TEST_KIWIX_ZIM_BASE="file://$SITE/zim" KIRIN_TEST_MEZHDUNAMI_BASE="file://$SITE/no-such-site/" KIRIN_TEST_YTDLP=true
# ZFSBootMenu, served locally with its pinned hashes.
mkdir -p "$SITE/zbm"; printf 'zbm release' > "$SITE/zbm/zbm-release.EFI"; printf 'zbm recovery' > "$SITE/zbm/zbm-recovery.EFI"
KIRIN_TEST_ZBM_FILES="zbm-release.EFI=$(sha256sum "$SITE/zbm/zbm-release.EFI" | cut -d' ' -f1) zbm-recovery.EFI=$(sha256sum "$SITE/zbm/zbm-recovery.EFI" | cut -d' ' -f1)"
export KIRIN_TEST_ZBM_URL="file://$SITE/zbm" KIRIN_TEST_ZBM_FILES
FIX="$REPO/tests/fixtures"
KIRIN_TEST_DEBIAN_KEYS="file://$FIX/test-key-rsa.asc=$(head -1 "$FIX/test-key-fingerprints.txt")"
export KIRIN_TEST_DEBIAN_KEYS
printf '{"vpn": {"url": "file:///nonexistent/vpn.deb", "sha256": "%064d", "package": "x"}, "pass": {"version_json": "file:///nonexistent/p.json"}}' 0 > "$T/proton.json"
export KIRIN_TEST_PROTON_JSON="$T/proton.json"
export KIRIN_TEST_VOICES_TSV="$T/voices.tsv" KIRIN_TEST_LIBRARY_TSV="$T/library.tsv" KIRIN_TEST_KIWIX_INDEX="file://$SITE/"
export KIRIN_TEST_FYAML_SHA256; KIRIN_TEST_FYAML_SHA256=$(sha256sum "$P/libfyaml-0.9.6.tar.gz" | cut -d' ' -f1)

echo '--- 1. wrong checksum is refused'
if "$REPO/build/kirin-build.sh" --iso "$T/upstream.iso" --iso-sha256 "$(printf '0%.0s' {1..64})" \
     --work "$T/work" --out "$T/out" >/dev/null 2>&1; then fail 'bad checksum accepted'; fi

echo '--- 2. first run, without a checksum, recovers the cut-short squashfs; an unrequested removal blocks the purge'
touch "$MOCK_STATE/extra-removal"
set +e; "$REPO/build/kirin-build.sh" --iso "$T/upstream.iso" --work "$T/work" --out "$T/out" --kiwix-name "$ZIM" \
  --content bundled > "$T/log1" 2>&1; rc=$?; set -e
[ "$rc" -ne 0 ] && grep -q 'unrequested removal: openkylin-desktop-meta' "$T/log1" || { cat "$T/log1"; fail 'extra removal not refused'; }
grep -q 'Status: install ok installed' <(grep -A1 'Package: openkylin-token-center' "$T/work/rootfs/var/lib/dpkg/status") ||
  fail 'package purged despite refusal'
grep -q '1 openKylin AI model files' "$T/log1" || { cat "$T/log1"; fail 'models not summarised'; }
grep -q 'came out incomplete' "$T/log1" && grep -q 'recovered 307200 bytes' "$T/log1" || { cat "$T/log1"; fail 'short squashfs not recovered'; }
cmp -s "$T/work/iso/casper/filesystem.squashfs" "$MOCK_STATE/squashfs.full" || fail 'recovered squashfs differs'
grep -q 'opt/kylin-ai/asr.onnx' "$T/work/upstream/upstream-models.json" || fail 'model not inventoried'
grep -q 'kingsoft' "$T/work/upstream/upstream-models.json" && fail 'excluded WPS model was inventoried'
[ ! -e "$T/work/.done-customise" ] || fail 'customise marked done after a refused purge'

echo '--- 4. reviewed allowance lets the build finish'
run --from customise --allow-removal openkylin-desktop-meta > "$T/log3" 2>&1 || { cat "$T/log3"; fail 'build failed'; }
iso=$(ls "$T"/out/kirin-*-amd64.iso)
grep -q 'map .*filesystem.squashfs /casper/filesystem.squashfs' "$iso" || fail 'squashfs not mapped into ISO'
grep -q 'boot_image any replay' "$iso" || fail 'boot records not replayed'
grep -q 'map .*iso-boot/boot/grub/grub.cfg /boot/grub/grub.cfg' "$iso" || fail 'boot menu not mapped'
grep -q 'grub-background.png /boot/grub/kirin-background.png' "$iso" || fail 'GRUB background not mapped'
grep -q 'isolinux-splash.png /isolinux/splash.png' "$iso" || fail 'isolinux splash not mapped'
grep -q 'map .*SHA256SUMS /SHA256SUMS' "$iso" || fail 'SHA256SUMS not mapped'
python3 - "$T/out" "$T/work" <<'PY' || fail 'output checks'
import glob, hashlib, json, sys
out, work = sys.argv[1:]
rec = json.load(open(glob.glob(out + '/*.build.json')[0]))
assert all(v == 'PASS' for v in rec['audits'].values()), rec['audits']
md5 = dict(reversed(l.split('  ', 1)) for l in open(work + '/md5sum.txt').read().splitlines())
assert md5['./casper/filesystem.squashfs'] == hashlib.md5(open(work + '/filesystem.squashfs', 'rb').read()).hexdigest()
new_grub = open(work + '/iso-boot/boot/grub/grub.cfg', 'rb').read()
assert b'locale=en_GB.UTF-8' in new_grub and b'Install Kirin Linux' in new_grub
assert md5['./boot/grub/grub.cfg'] == hashlib.md5(new_grub).hexdigest(), 'grub.cfg md5 not updated'
assert md5['./md5sum.txt'] == 'cccc'
sha = dict(reversed(l.split('  ', 1)) for l in open(work + '/SHA256SUMS').read().splitlines())
assert sha['./boot/grub/grub.cfg'] == hashlib.sha256(new_grub).hexdigest(), 'SHA256SUMS not updated'
PY
R="$T/work/rootfs"
[ ! -e "$R/kirin-build" ] && [ ! -e "$R/usr/sbin/policy-rc.d" ] || fail 'build scaffolding left in image'
[ "$(readlink "$R/etc/resolv.conf")" = ../run/systemd/resolve/stub-resolv.conf ] || fail 'resolv.conf not restored'
[ -x "$R/usr/local/bin/ollama" ] && [ -f "$R/etc/systemd/system/ollama.service" ] && [ -x "$R/usr/bin/kirin-learn" ] ||
  fail 'payloads not installed'
grep -q 'Package: openkylin-token-center' "$R/var/lib/dpkg/status" && fail 'token centre still installed'
grep -q 'Package: kylin-id$' "$R/var/lib/dpkg/status" && fail 'kylin-id (optional purge) still installed'
grep -q 'optional purge: kylin-id' "$T/log3" || fail 'optional purge not attempted'
RU="$R/opt/kirin/russian"
[ -x "$R/opt/kirin/piper/piper" ] && [ "$(ls "$RU"/voices/*.onnx | wc -l)" -eq 4 ] || fail 'Piper or voices missing'
[ -f "$RU/library/DLI Russian Basic Course/Mod 01.pdf" ] && [ ! -e "$RU/library/DLI Russian Basic Course/Gone.pdf" ] ||
  fail 'library not installed (or a missing book was not skipped)'
[ -f "$RU/dictionary/$ZIM" ] || fail 'dictionary not installed'
[ -f "$RU/dictionary/$WS" ] || fail 'Wikisource ZIM not installed'
grep -q '"wikisource": "/opt/kirin/russian/dictionary/'"$WS"'"' "$R/usr/share/kirin/russian.json" || fail 'Wikisource not in russian.json'
grep -q '"wikipedia"' "$R/usr/share/kirin/russian.json" && fail 'unavailable Wikipedia listed in russian.json'
ls "$RU/audiobooks/A2/"*/t01_64kb.mp3 >/dev/null 2>&1 || fail 'audiobook not installed'
grep -q 'not available: gonebook' "$T"/log* || fail 'missing audiobook not reported'
[ -f "$R/usr/share/kirin/russian/vocab.tsv" ] || fail 'Russian word list not installed'
python3 -c 'import json,sys; c=json.load(open(sys.argv[1])); assert c["model"].startswith("qwen3:30b"), c' \
  "$R/usr/share/kirin/russian.json" || fail 'russian.json wrong'
grep -q 'PASS russian' "$T/work/audit/summary" || fail 'russian audit did not pass'
grep -q 'PASS branding' "$T/work/audit/summary" || fail 'branding audit did not pass'
grep -q 'PASS defaults' "$T/work/audit/summary" || fail 'defaults audit did not pass'
grep -q 'Package: wps-office$' "$R/var/lib/dpkg/status" && fail 'WPS Office still installed'
[ ! -e "$R/var/opt/kingsoft" ] || fail 'WPS leftovers not removed'
[ "$(cat "$R/etc/hostname")" = kirin ] || fail 'hostname not kirin'
grep -q 'Kirin: Fastfetch' "$R/etc/bash.bashrc" || fail 'Fastfetch hook missing'
[ -x "$R/usr/bin/kirin-welcome" ] && [ -f "$R/etc/xdg/autostart/kirin-welcome.desktop" ] || fail 'Welcome app not installed'
[ -f "$R/etc/skel/.config/org.ukui/_ukui-config-global/org.ukui.panel.taskManager.json" ] || fail 'taskbar pins missing'
grep -q '^Name=Kirin Music$' "$R/usr/share/applications/kylin-music.desktop" || fail 'menu name not rebranded'
grep -q 'NAME="Kirin Linux"' "$R/usr/lib/os-release" || fail 'os-release not rebranded'
[ -f "$R/etc/xdg/fastfetch/config.jsonc" ] && [ -f "$R/usr/share/plymouth/themes/kirin/splash.png" ] || fail 'branding files missing'
[ -f "$R/etc/skel/.var/app/com.jeffser.Alpaca/data/alpaca.db" ] || fail 'Alpaca not pre-connected'
grep -q 'ENABLED debian' "$T/work/audit/extra-repos.log" || fail 'extra repos step not run'
grep -q 'installed fastfetch' "$T/work/audit/extra-packages.log" || fail 'extra packages step not run'
grep -q 'UBUNTU alsa-ucm-conf' "$T/work/audit/prefer-ubuntu.log" || fail 'prefer-ubuntu step not run'
grep -q 'from Ubuntu: fprintd' "$T/work/audit/pin-extras.log" || fail 'extras not pinned for updates'
grep -q 'ZFS: OpenZFS 2.4.1 ready' "$T/work/audit/zfs-build.log" || fail 'ZFS step not run'
cmp -s "$SITE/zbm/zbm-release.EFI" "$R/usr/share/kirin/zfsbootmenu/VMLINUZ.EFI" || fail 'ZFSBootMenu not installed'
[ ! -e "$R/opt/kylin-ai/asr.onnx" ] && grep -q 'removing openKylin.s AI models: kylin-ai' "$T/log3" || fail 'openKylin AI model not removed'
grep -q "AI payload audit passed: openKylin's models removed; coding model complete" "$T/work/audit/ai-payload.log" || fail 'ai-payload audit wrong'
[ -x "$R/usr/bin/kirin-content" ] && [ -f "$R/usr/lib/kirin/content/fetch-kiwix.py" ] || fail 'kirin-content not installed'
[ -x "$R/usr/sbin/kirin-zfs-install" ] && [ -x "$R/usr/bin/kirin-be" ] && [ -x "$R/usr/lib/kirin/zfs-apt-snapshot" ] || fail 'ZFS tools not installed'
grep -q 'PASS zfs' "$T/work/audit/summary" || fail 'zfs audit did not pass'
grep -q 'blacklist cros-usbpd-charger' "$R/etc/modprobe.d/kirin-framework.conf" || fail 'Framework module options missing'
grep -q 'ani-cli' "$T/work/audit/kirin-debs.log" || fail 'Kirin packages step not run'
grep -q 'Proton' "$T/work/audit/proton.log" || fail 'Proton step not run'
cat "$T/log1" "$T/log3" | grep -q 'SKIPPED vpn' || fail 'unreachable Proton source not skipped gracefully'
cat "$T/log1" "$T/log3" | grep -q 'Kirin APT repository not set up yet' || fail 'missing Kirin key not reported'
grep -q 'keeping openKylin.s live initrd' "$T/log3" || fail 'live initrd decision not reported'

grep -q 'no kernel config in the image; using xz' "$T/log3" || fail 'compression fallback not reported'
grep -q -- '-comp xz' "$T/work/filesystem.squashfs" || fail 'fallback compression not used'

echo '--- 4b. --refresh re-applies Kirin files and packs with zstd when the kernel supports it'
mkdir -p "$R/boot"; printf 'CONFIG_SQUASHFS=y\nCONFIG_SQUASHFS_ZSTD=y\n' > "$R/boot/config-7.0.0-3-generic"
rm -f "$R/etc/kirin-release" "$R/usr/bin/kirin-learn"
run --refresh > "$T/log4b" 2>&1 || { cat "$T/log4b"; fail 'refresh failed'; }
grep -q 'Refreshing Kirin files' "$T/log4b" && ! grep -q 'installing base packages' "$T/log4b" || fail 'refresh redid customise'
[ -f "$R/etc/kirin-release" ] && [ -x "$R/usr/bin/kirin-learn" ] || fail 'refresh did not re-apply Kirin files'
grep -q -- '-comp zstd -Xcompression-level 12' "$T/work/filesystem.squashfs" || fail 'zstd not used'
printf 'CONFIG_SQUASHFS=y\n# CONFIG_SQUASHFS_ZSTD is not set\n' > "$R/boot/config-7.0.0-3-generic"

echo '--- 5. a policy failure blocks release but allows a test build'
printf 'Name[zh_CN]=Files-zh\n' >> "$R/usr/share/applications/files.desktop"
if run --only audit > "$T/log5" 2>&1; then fail 'language failure not caught'; fi
run --only audit --test-build > "$T/log5" 2>&1 || { cat "$T/log5"; fail 'test build audit refused'; }
run --only pack --test-build > "$T/log5" 2>&1 || { cat "$T/log5"; fail 'test build pack refused'; }
ls "$T"/out/kirin-*-amd64.iso >/dev/null || fail 'test build ISO missing'
grep -q 'audits that did not pass: language' "$T/log5" || fail 'failed audit not reported'
python3 -c "import glob, json, sys; r = json.load(open(glob.glob(sys.argv[1] + '/*.build.json')[0])); assert r['test_build'] and r['audits']['language'] == 'FAIL', r" "$T/out" || fail 'test build not recorded'

echo '--- 6. an openKylin AI model left in the image is never waived'
mkdir -p "$R/opt/kylin-ai"; echo leftover > "$R/opt/kylin-ai/asr.onnx"
set +e; run --only audit --test-build > "$T/log4" 2>&1; rc=$?; set -e
[ "$rc" -ne 0 ] && grep -q 'never waived' "$T/log4" || { cat "$T/log4"; fail 'leftover model not caught'; }
rm -f "$R/opt/kylin-ai/asr.onnx"

echo '--- 7. on-demand content: no AI models or big Russian material in the image'
run --from customise --content on-demand --allow-removal openkylin-desktop-meta --test-build > "$T/log7" 2>&1 || { cat "$T/log7"; fail 'on-demand build failed'; }
[ -z "$(ls -A "$R/usr/share/ollama/.ollama/models" 2>/dev/null)" ] || fail 'models bundled in on-demand build'
for d in library dictionary audiobooks; do [ ! -e "$R/opt/kirin/russian/$d" ] || fail "$d bundled in on-demand build"; done
[ "$(ls "$R"/opt/kirin/russian/voices/*.onnx | wc -l)" -eq 4 ] || fail 'voices missing in on-demand build'
grep -q 'AI models are downloaded after install' "$T/work/audit/ai-payload.log" || fail 'on-demand ai-payload audit wrong'
grep -q 'PASS russian' "$T/work/audit/summary" || { cat "$T/work/audit/russian.log"; fail 'on-demand russian audit failed'; }
python3 -c "import glob, json, sys; r = json.load(open(sorted(glob.glob(sys.argv[1] + '/*.build.json'))[-1])); assert r['content'] == 'on-demand', r" "$T/out" || fail 'content mode not recorded'

echo 'MOCK BUILD PASSED'
