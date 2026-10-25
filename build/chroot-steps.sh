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
    for p in $(list /kirin-build/extra-packages.txt); do
      # shellcheck disable=SC2086
      if apt-get install -y -q --no-install-recommends $apt_opts "$p" >/dev/null 2>&1; then
        echo "installed $p from $(apt-cache policy "$p" | awk '/\*\*\*/{getline; print $2" "$3; exit}')"
      else
        echo "NOT AVAILABLE: $p"
      fi
    done
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
