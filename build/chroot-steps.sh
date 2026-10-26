#!/bin/sh
# Runs INSIDE the disposable image chroot, invoked by build/kirin-build.sh.
# Never run this on a real system.
set -eu
[ -f /kirin-build/IN_CHROOT ] || { echo 'chroot-steps.sh: not inside a Kirin build chroot' >&2; exit 2; }
export DEBIAN_FRONTEND=noninteractive LC_ALL=C.UTF-8
# The host's PATH is inherited through sudo and chroot; on Arch it has no sbin
# directories, so dpkg cannot find ldconfig or start-stop-daemon. Use openKylin's.
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
apt_opts='-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold'
MULTIARCH=x86_64-linux-gnu
FYAML_VERSION=0.9.6
FYAML_MIN=0.9

list() { sed -e 's/#.*//' -e 's/[[:space:]]//g' -e '/^$/d' "$1"; }
installed_set() { dpkg-query -W -f='${db:Status-Abbrev} ${Package}\n' | awk '$1 == "ii" {print $2}' | sort; }
soname() { readelf -d "$1" | sed -n 's/.*(SONAME).*\[\(.*\)\]/\1/p'; }

# openKylin 3.0's flatpak needs libappstream5, which needs libfyaml0 >= 0.9,
# but no openKylin repository ships libfyaml0 (Debian only has 0.8). Build a
# Kirin compatibility package from the checksummed upstream release, and only
# install it if its SONAME is exactly what libappstream5 links against.
compat_libfyaml() {
  cand=$(apt-cache policy libfyaml0 2>/dev/null | awk '/Candidate:/ {print $2}')
  if [ -n "$cand" ] && [ "$cand" != '(none)' ] && dpkg --compare-versions "$cand" ge "$FYAML_MIN"; then
    return 0
  fi
  echo "libfyaml0 >= $FYAML_MIN is not in the openKylin repositories (candidate: ${cand:-none}); building Kirin compatibility package"
  work=/kirin-build/libfyaml
  rm -rf "$work"; mkdir -p "$work/stage" "$work/pkg/DEBIAN" "$work/appstream"

  installed_set > "$work/before"
  # shellcheck disable=SC2086
  apt-get install -y --no-install-recommends $apt_opts gcc make m4 libc6-dev binutils pkg-config
  installed_set > "$work/after"
  comm -13 "$work/before" "$work/after" > "$work/tools"

  tar -xzf "/kirin-build/libfyaml-$FYAML_VERSION.tar.gz" -C "$work"
  (
    cd "$work/libfyaml-$FYAML_VERSION"
    ./configure --prefix=/usr --libdir="/usr/lib/$MULTIARCH" --disable-static \
      --disable-network --with-libclang=no --enable-portable-target > "$work/configure.log" 2>&1 ||
      { tail -40 "$work/configure.log" >&2; exit 1; }
    make -j"$(nproc)" > "$work/make.log" 2>&1 || { tail -40 "$work/make.log" >&2; exit 1; }
    make install DESTDIR="$work/stage" > "$work/install.log" 2>&1 || { tail -40 "$work/install.log" >&2; exit 1; }
  )

  lib=$(find "$work/stage/usr/lib/$MULTIARCH" -maxdepth 1 -type f -name 'libfyaml.so.*' | head -1)
  [ -n "$lib" ] || { echo 'libfyaml build produced no shared library' >&2; exit 1; }
  built=$(soname "$lib")

  (cd "$work/appstream" && apt-get download libappstream5 >/dev/null)
  dpkg-deb -x "$work"/appstream/libappstream5_*.deb "$work/appstream/root"
  needed=$(find "$work/appstream/root" -name 'libappstream.so.*' -type f -exec readelf -d {} \; |
           sed -n 's/.*(NEEDED).*\[\(libfyaml[^]]*\)\]/\1/p' | sort -u)
  if [ -z "$needed" ] || [ "$needed" != "$built" ]; then
    echo "REFUSED: libappstream5 needs '${needed:-nothing}' but the build produced '$built'" >&2
    exit 1
  fi
  echo "built $built, matching libappstream5"

  mkdir -p "$work/pkg/usr/lib/$MULTIARCH" "$work/pkg/usr/share/doc/libfyaml0"
  cp -a "$work/stage/usr/lib/$MULTIARCH"/libfyaml.so.* "$work/pkg/usr/lib/$MULTIARCH/"
  cp "$work/libfyaml-$FYAML_VERSION/LICENSE" "$work/pkg/usr/share/doc/libfyaml0/copyright"
  cat > "$work/pkg/DEBIAN/control" <<EOF
Package: libfyaml0
Source: libfyaml
Version: $FYAML_VERSION-0kirin1
Architecture: amd64
Multi-Arch: same
Section: libs
Priority: optional
Depends: libc6
Maintainer: Kirin Linux build <kirin-build@localhost>
Homepage: https://github.com/pantoniou/libfyaml
Description: fully featured YAML 1.2 parser library (Kirin compatibility build)
 Built by the Kirin image builder from the upstream $FYAML_VERSION release because
 openKylin 3.0's repositories lack libfyaml0 >= $FYAML_MIN, which libappstream5
 (and so flatpak) requires.
EOF
  dpkg-deb --root-owner-group --build "$work/pkg" "$work/libfyaml0.deb" >/dev/null
  dpkg -i "$work/libfyaml0.deb"
  ldconfig

  # Remove exactly the build tools this step installed, and nothing else.
  if [ -s "$work/tools" ]; then
    # shellcheck disable=SC2046
    apt-get -s purge $(cat "$work/tools") | awk '/^(Remv|Purg) / {print $2}' | sed 's/:.*//' | sort > "$work/removing"
    unexpected=$(comm -23 "$work/removing" "$work/tools")
    if [ -n "$unexpected" ]; then
      echo "Keeping build tools: removing them would also remove: $unexpected" >&2
    else
      # shellcheck disable=SC2046,SC2086
      apt-get purge -y $apt_opts $(cat "$work/tools")
    fi
  fi
  rm -rf "$work"
}

step=${1:?step}
shift
case "$step" in
  installed)
    # Print which of the given packages are installed.
    for p in "$@"; do
      if dpkg-query -W -f='${db:Status-Abbrev}' "$p" 2>/dev/null | grep -q '^ii'; then echo "$p"; fi
    done
    ;;
  install)
    apt-get update
    compat_libfyaml
    # shellcheck disable=SC2046,SC2086
    apt-get install -y --no-install-recommends $apt_opts $(list /kirin-build/base-packages.txt) locales
    ;;
  install-extras)
    # Packages openKylin may lack; each comes from openKylin if it has it, otherwise
    # from the pinned Ubuntu/Debian repositories. A missing one is reported, not fatal.
    apt-get update -q >/dev/null 2>&1 || true
    [ -f /kirin-build/before-extras ] || installed_set > /kirin-build/before-extras
    # "a|b" means: the first of these that installs (for packages that conflict).
    for choice in $(list /kirin-build/extra-packages.txt); do
      done_one=''
      for p in $(printf '%s\n' "$choice" | tr '|' ' '); do
        # shellcheck disable=SC2086
        if apt-get install -y -q --no-install-recommends $apt_opts "$p" >/dev/null 2>&1; then
          echo "installed $p from $(apt-cache policy "$p" | awk '/\*\*\*/{getline; print $2" "$3; exit}')"
          done_one=1; break
        fi
      done
      [ -n "$done_one" ] || echo "NOT AVAILABLE: $choice"
    done
    ;;
  zfs)
    # OpenZFS from Ubuntu 26.04: its 2.4.1 is patched for Linux 7.0, the kernel openKylin
    # 3.0 ships. DKMS compiles the module for every kernel in the image that has headers.
    pin=/etc/apt/preferences.d/83kirin-zfs
    if [ ! -f /etc/apt/sources.list.d/kirin-ubuntu.sources ]; then echo 'ZFS: SKIPPED (Ubuntu repository not enabled)'; exit 0; fi
    for suite in resolute resolute-updates resolute-security; do
      printf 'Package: src:zfs-linux\nPin: release o=Ubuntu,n=%s\nPin-Priority: 990\n\n' "$suite"
    done > "$pin"
    want='zfs-dkms zfsutils-linux zfs-initramfs zfs-zed'
    # Only packages built from the zfs-linux source may come from Ubuntu.
    bad=''
    for entry in $(apt-get -s -q install --no-install-recommends $want 2>/dev/null |
                   sed -n 's/^Inst \([^ ]*\) .*(\([^ ]*\) Ubuntu[: ].*/\1=\2/p'); do
      src=$(apt-cache show "$entry" 2>/dev/null | awk '/^Source:/ {print $2; exit}')
      [ "${src:-${entry%%=*}}" = zfs-linux ] || bad="$bad ${entry%%=*}"
    done
    if [ -n "$bad" ]; then
      rm -f "$pin"; echo "ZFS: SKIPPED (would also take$bad from Ubuntu)"; exit 0
    fi
    # shellcheck disable=SC2086
    if ! apt-get install -y -q --no-install-recommends $apt_opts $want gdisk dosfstools efibootmgr squashfs-tools >/dev/null; then
      apt-get purge -y -q $want >/dev/null 2>&1 || true
      rm -f "$pin"; echo 'ZFS: FAILED (packages did not install)'; exit 0
    fi
    zver=$(dpkg-query -W -f='${Version}' zfs-dkms | sed 's/^[0-9]*://; s/-[^-]*$//')
    ok=1 built=0
    for kdir in /lib/modules/*; do
      [ -d "$kdir" ] || continue
      k=$(basename "$kdir")
      [ -e "$kdir/build" ] || { echo "ZFS: no headers for $k, skipped"; continue; }
      dkms install "zfs/$zver" -k "$k" >/dev/null 2>&1 || true
      if find "$kdir" -name 'zfs.ko*' | grep -q .; then echo "ZFS_MODULE $k"; built=$((built + 1)); else echo "ZFS: module did not build for $k"; ok=0; fi
    done
    if [ "$ok" -eq 0 ] || [ "$built" -eq 0 ]; then
      apt-get purge -y -q $want >/dev/null 2>&1 || true
      rm -f "$pin"; echo 'ZFS: FAILED (module build; see /var/lib/dkms/zfs)'; exit 0
    fi
    systemctl enable zfs.target zfs-import-cache.service zfs-mount.service zfs-import.target zfs-zed.service >/dev/null 2>&1 || true
    echo "ZFS: OpenZFS $zver ready ($(zfs version 2>/dev/null | head -1))"
    ;;
  pin-extras)
    # Packages that came from Ubuntu or Debian (Kirin's extras and their dependencies)
    # are pinned to their source so they keep getting its updates (see 80kirin-extra-repos).
    pins=/etc/apt/preferences.d/82kirin-from-extras
    rm -f "$pins"
    [ -f /kirin-build/before-extras ] || { echo 'nothing recorded'; exit 0; }
    n=0
    for p in $(installed_set | comm -13 /kirin-build/before-extras -); do
      origin=$(apt-cache policy "$p" 2>/dev/null | awk '
        /^ +\*\*\* / {mine=1; next}
        /^ +[^ ]+ [0-9-]+$/ && !/http|status/ {mine=0}
        mine && /archive\.ubuntu\.com|security\.ubuntu\.com/ {print "Ubuntu"; exit}
        mine && /deb\.debian\.org|security\.debian\.org/ {print "Debian"; exit}')
      [ -n "$origin" ] || continue
      printf 'Package: %s\nPin: release o=%s\nPin-Priority: 500\n\n' "$p" "$origin" >> "$pins"
      echo "from $origin: $p"; n=$((n + 1))
    done
    echo "$n packages from the extra repositories pinned for updates"
    ;;
  prefer-ubuntu)
    # Hardware data packages where Ubuntu 26.04 (which Framework supports) may be newer
    # than openKylin: take Ubuntu's only when its upstream version is newer, nothing
    # else would change origin, and then keep following Ubuntu's updates for it.
    # Upstream part of a version: drop the Debian revision, or a native package's distro suffix.
    upstream() { printf '%s\n' "$1" | sed -e 's/-[^-]*$//' -e 's/\(ubuntu\|ok\|build\|deb\)[0-9].*$//' -e 's/[+~.]$//'; }
    pins=/etc/apt/preferences.d/81kirin-prefer-ubuntu
    if [ ! -f /etc/apt/sources.list.d/kirin-ubuntu.sources ]; then
      echo 'SKIPPED: Ubuntu repository not enabled'; exit 0
    fi
    rm -f "$pins"
    for p in $(list /kirin-build/prefer-ubuntu.txt); do
      ok=$(apt-cache madison "$p" 2>/dev/null | awk -F'|' '$3 !~ /archive\.ubuntu|security\.ubuntu|debian\.org/ {gsub(/ /,"",$2); print $2; exit}')
      ub=$(apt-cache madison "$p" 2>/dev/null | awk -F'|' '$3 ~ /archive\.ubuntu|security\.ubuntu/ {gsub(/ /,"",$2); print $2; exit}')
      have=$(dpkg-query -W -f='${Version}' "$p" 2>/dev/null || true)
      if [ -z "$ub" ]; then echo "KEPT $p ${have:-$ok}: not in Ubuntu"; continue; fi
      base=${have:-$ok}
      if [ -n "$base" ] && ! dpkg --compare-versions "$(upstream "$ub")" gt "$(upstream "$base")"; then
        echo "KEPT $p $base (Ubuntu has $ub, not newer)"; continue
      fi
      # Only this package may come from Ubuntu or Debian.
      if apt-get -s -q install --no-install-recommends "$p=$ub" 2>/dev/null |
         grep -E '^Inst ' | grep -v "^Inst $p " | grep -qE '\((\S+ )?(Debian|Ubuntu)[: ]'; then
        echo "KEPT $p ${base:-none}: Ubuntu's $ub would pull other packages from Ubuntu"; continue
      fi
      # shellcheck disable=SC2086
      if apt-get install -y -q --no-install-recommends $apt_opts "$p=$ub" >/dev/null 2>&1; then
        for suite in resolute resolute-updates resolute-security; do
          printf 'Package: %s\nPin: release o=Ubuntu,n=%s\nPin-Priority: 510\n\n' "$p" "$suite" >> "$pins"
        done
        echo "UBUNTU $p $ub (openKylin had ${base:-none})"
      else
        echo "KEPT $p ${base:-none}: Ubuntu's $ub did not install"
      fi
    done
    ;;
  kirin-debs)
    # Kirin's own packages, built from pinned upstream sources (packaging/debs).
    rm -rf /kirin-build/debs-out
    if python3 /kirin-build/build-debs.py --specs /kirin-build/debs --out /kirin-build/debs-out; then
      # shellcheck disable=SC2086
      apt-get install -y -q --no-install-recommends $apt_opts /kirin-build/debs-out/*.deb >/dev/null &&
        echo "installed: $(cd /kirin-build/debs-out && ls -- *.deb | tr '\n' ' ')" ||
        echo 'NOT INSTALLED: Kirin packages (dependencies unavailable)'
    else
      echo 'NOT BUILT: Kirin packages (see messages above)'
    fi
    # Kirin's signed APT repository, once its key exists (docs/KIRIN-REPO.md).
    if [ -f /kirin-build/kirin-repo/kirin-archive-keyring.gpg ]; then
      install -d -m 0755 /etc/apt/keyrings
      install -m 0644 /kirin-build/kirin-repo/kirin-archive-keyring.gpg /etc/apt/keyrings/kirin-archive.gpg
      printf 'Types: deb\nURIs: %s\nSuites: stable\nComponents: main\nSigned-By: /etc/apt/keyrings/kirin-archive.gpg\n' \
        "$(cat /kirin-build/kirin-repo/url)" > /etc/apt/sources.list.d/kirin.sources
      echo 'ENABLED Kirin APT repository'
    fi
    ;;
  proton)
    # Proton's official packages (verified on the host by scripts/build/fetch-proton.py).
    d=/kirin-build/proton
    if [ -f "$d/protonvpn-release.deb" ]; then
      # shellcheck disable=SC2086
      if dpkg -i "$d/protonvpn-release.deb" >/dev/null && apt-get update -q >/dev/null 2>&1 &&
         apt-get install -y -q $apt_opts "$(cat "$d/protonvpn-package")" >/dev/null; then
        echo 'installed Proton VPN (updates from repo.protonvpn.com)'
      else
        echo 'NOT INSTALLED: Proton VPN'
      fi
    fi
    for app in pass mail; do
      [ -f "$d/proton$app.deb" ] || { echo "NOT AVAILABLE: Proton $app"; continue; }
      # shellcheck disable=SC2086
      if apt-get install -y -q $apt_opts "$d/proton$app.deb" >/dev/null; then echo "installed Proton $app"
      else echo "NOT INSTALLED: Proton $app"; fi
    done
    ;;
  cleanup-removed)
    # Files a removed package left behind outside dpkg's knowledge (WPS unpacks add-ons
    # into /var/opt/kingsoft). Removed only when the package is gone and dpkg owns nothing there.
    if ! dpkg-query -W -f='${db:Status-Abbrev}' wps-office 2>/dev/null | grep -q '^ii'; then
      for d in /var/opt/kingsoft /opt/kingsoft; do
        if [ -d "$d" ] && ! dpkg -S "$d" >/dev/null 2>&1; then rm -rf "$d"; echo "removed leftover $d"; fi
      done
    fi
    ;;
  simulate-purge)
    apt-get -s purge "$@"
    ;;
  purge)
    # shellcheck disable=SC2086
    apt-get purge -y $apt_opts "$@"
    ;;
  flatpak)
    flatpak remote-add --system --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    # shellcheck disable=SC2046
    # --reinstall keeps this idempotent and re-runs Flatpak's export triggers.
    flatpak install --system -y --noninteractive --reinstall flathub $(list /kirin-build/flatpak-apps.txt)
    # Let Kiwix read the bundled dictionary ($1 = Russian material directory).
    if [ -n "${1:-}" ] && list /kirin-build/flatpak-apps.txt | grep -qx org.kiwix.desktop; then
      flatpak override --system --filesystem="$1:ro" org.kiwix.desktop
    fi
    ;;
  extra-repos)
    # Pinned Debian 13 / Ubuntu 26.04 repositories. Each is kept only if APT can
    # verify it, and both are removed if they would replace any openKylin package.
    d=/kirin-build/extra-repos
    install -d -m 0755 /etc/apt/keyrings
    install -m 0644 "$d/80kirin-extra-repos" /etc/apt/preferences.d/80kirin-extra-repos
    have_list() { ls /var/lib/apt/lists/*"$1"*InRelease >/dev/null 2>&1; }
    drop() { rm -f "/etc/apt/sources.list.d/kirin-$1.sources" "/etc/apt/keyrings/kirin-$1.gpg"; echo "DROPPED $1: $2"; }
    if [ -f "$d/kirin-debian.gpg" ]; then
      install -m 0644 "$d/kirin-debian.gpg" /etc/apt/keyrings/kirin-debian.gpg
      install -m 0644 "$d/kirin-debian.sources" /etc/apt/sources.list.d/kirin-debian.sources
      apt-get update -q >/dev/null 2>&1 || true
      have_list 'deb.debian.org_debian_dists_trixie_' || drop debian 'APT could not verify the Debian repository'
    else
      echo 'DROPPED debian: no verified Debian keys'
    fi
    # Ubuntu's keyring comes from a repository APT already trusts (openKylin's or Debian's).
    rm -rf "$d/ubuntu-keyring"; mkdir -p "$d/ubuntu-keyring"
    if (cd "$d/ubuntu-keyring" && apt-get download -q ubuntu-keyring >/dev/null 2>&1) &&
       dpkg-deb -x "$d"/ubuntu-keyring/ubuntu-keyring_*.deb "$d/ubuntu-keyring/root" &&
       [ -f "$d/ubuntu-keyring/root/usr/share/keyrings/ubuntu-archive-keyring.gpg" ]; then
      install -m 0644 "$d/ubuntu-keyring/root/usr/share/keyrings/ubuntu-archive-keyring.gpg" /etc/apt/keyrings/kirin-ubuntu.gpg
      install -m 0644 "$d/kirin-ubuntu.sources" /etc/apt/sources.list.d/kirin-ubuntu.sources
      apt-get update -q >/dev/null 2>&1 || true
      have_list 'archive.ubuntu.com_ubuntu_dists_resolute_' ||
        drop ubuntu "APT could not verify Ubuntu 26.04 with the keyring from $(apt-cache policy ubuntu-keyring | awk '/\*\*\*/{getline; print $2; exit}')"
    else
      echo 'DROPPED ubuntu: no trusted ubuntu-keyring package available'
    fi
    # Safety: the extras must never upgrade or replace an openKylin package.
    if apt-get -s -q dist-upgrade 2>/dev/null | grep -E '^Inst .*\((\S+ )?(Debian|Ubuntu)[: ]'; then
      drop debian 'it would replace openKylin packages'; drop ubuntu 'it would replace openKylin packages'
      apt-get update -q >/dev/null 2>&1 || true
    fi
    for r in debian ubuntu; do
      [ -f "/etc/apt/sources.list.d/kirin-$r.sources" ] && echo "ENABLED $r (pinned below openKylin)"
    done
    [ -n "$(ls /etc/apt/sources.list.d/kirin-*.sources 2>/dev/null)" ] || rm -f /etc/apt/preferences.d/80kirin-extra-repos
    ;;
  finish)
    # openKylin's locales package is Ubuntu-style: locale-gen reads
    # /var/lib/locales/supported.d, not /etc/locale.gen. Generate only en_GB and ru_RU.
    if [ -d /var/lib/locales/supported.d ]; then
      for f in /var/lib/locales/supported.d/*; do
        if [ -f "$f" ] && [ ! -L "$f" ]; then sed -i '/^zh_/d' "$f"; fi
      done
      printf 'en_GB.UTF-8 UTF-8\nru_RU.UTF-8 UTF-8\n' > /var/lib/locales/supported.d/kirin
      locale-gen --purge en_GB.UTF-8 ru_RU.UTF-8
    else
      locale-gen
    fi
    update-locale LANG=en_GB.UTF-8 LANGUAGE=en_GB:en
    if ! id ollama >/dev/null 2>&1; then
      useradd -r -s /usr/sbin/nologin -U -m -d /usr/share/ollama ollama
    fi
    for g in render video; do
      if getent group "$g" >/dev/null; then usermod -a -G "$g" ollama; fi
    done
    chown -R ollama:ollama /usr/share/ollama
    systemctl enable ollama.service
    # Fingerprints: fprintd replaces openKylin's biometric service (which never drove the
    # Framework's Goodix reader). Only switched over if libpam-fprintd actually installed.
    if dpkg-query -W -f='${db:Status-Abbrev}' libpam-fprintd 2>/dev/null | grep -q '^ii'; then
      for prof in /usr/share/pam-configs/*; do
        if [ -f "$prof" ] && grep -qi 'biometric' "$prof"; then pam-auth-update --package --remove "$(basename "$prof")"; fi
      done
      # openKylin's common-auth counts as locally edited, so plain --package leaves it alone;
      # --force regenerates it from the profiles (with the biometric one removed above).
      pam-auth-update --package --force --enable fprintd || true
      for unit in $(systemctl list-unit-files --no-legend 'biometric*' 2>/dev/null | awk '{print $1}'); do
        systemctl mask "$unit" >/dev/null 2>&1 && echo "masked $unit"
      done
      if grep -q 'pam_biometric' /etc/pam.d/common-auth; then
        sed -i '/pam_biometric\.so/d' /etc/pam.d/common-auth
        echo 'FINGERPRINT: removed a leftover pam_biometric line from common-auth'
      fi
      if ! grep -q 'pam_fprintd' /etc/pam.d/common-auth; then
        # Last resort: put fprintd in front of the password check, skipping it and pam_deny on success.
        sed -i '0,/^auth\s.*pam_unix\.so/s//auth\t[success=2 default=ignore]\tpam_fprintd.so max-tries=1 timeout=10\n&/' /etc/pam.d/common-auth
        echo 'FINGERPRINT: added pam_fprintd to common-auth by hand'
      fi
      grep -q 'pam_fprintd' /etc/pam.d/common-auth || echo 'FINGERPRINT WARNING: pam_fprintd is not in common-auth'
      echo 'FINGERPRINT: fprintd enabled for login, lock screen and sudo'
    else
      echo 'FINGERPRINT: libpam-fprintd not installed; leaving openKylin biometrics as they are'
    fi
    # Kirin defaults written by scripts/kirin-polish.py: schema overrides and the default terminal.
    if command -v glib-compile-schemas >/dev/null; then glib-compile-schemas /usr/share/glib-2.0/schemas || true; fi
    if [ -x /usr/bin/kitty ] && update-alternatives --list x-terminal-emulator 2>/dev/null | grep -qx /usr/bin/kitty; then
      update-alternatives --set x-terminal-emulator /usr/bin/kitty
    fi
    # Kirin boot splash: select the theme, then rebuild every initramfs.
    if [ -f /usr/share/plymouth/themes/kirin/kirin.plymouth ]; then
      if command -v update-alternatives >/dev/null; then
        update-alternatives --install /usr/share/plymouth/themes/default.plymouth default.plymouth \
          /usr/share/plymouth/themes/kirin/kirin.plymouth 300 >/dev/null 2>&1 || true
        update-alternatives --set default.plymouth /usr/share/plymouth/themes/kirin/kirin.plymouth >/dev/null 2>&1 || true
      fi
      if command -v plymouth-set-default-theme >/dev/null; then plymouth-set-default-theme kirin || true; fi
    fi
    if command -v update-initramfs >/dev/null; then
      update-initramfs -u -k all
      for k in /boot/vmlinuz-*; do
        [ -e "$k" ] || continue
        v=${k#/boot/vmlinuz-}
        if [ -f "/boot/initrd.img-$v" ] && lsinitramfs "/boot/initrd.img-$v" 2>/dev/null | grep -q 'scripts/casper$'; then
          echo "CASPER_INITRD $v"
        fi
      done
    fi
    apt-get clean
    rm -rf /var/lib/apt/lists/* /var/cache/apt/*.bin
    ;;
  manifest)
    dpkg-query -W --showformat='${Package}\t${Version}\n'
    ;;
  *)
    echo "unknown step: $step" >&2; exit 2 ;;
esac
