#!/bin/sh
# Runs INSIDE the disposable image chroot, invoked by build/kirin-build.sh.
# Never run this on a real system.
set -eu
[ -f /kirin-build/IN_CHROOT ] || { echo 'chroot-steps.sh: not inside a Kirin build chroot' >&2; exit 2; }
export DEBIAN_FRONTEND=noninteractive LC_ALL=C.UTF-8
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
    flatpak install --system -y --noninteractive flathub $(list /kirin-build/flatpak-apps.txt)
    ;;
  finish)
    locale-gen
    update-locale LANG=en_GB.UTF-8 LANGUAGE=en_GB:en
    if ! id ollama >/dev/null 2>&1; then
      useradd -r -s /usr/sbin/nologin -U -m -d /usr/share/ollama ollama
    fi
    for g in render video; do
      if getent group "$g" >/dev/null; then usermod -a -G "$g" ollama; fi
    done
    chown -R ollama:ollama /usr/share/ollama
    systemctl enable ollama.service
    apt-get clean
    rm -rf /var/lib/apt/lists/* /var/cache/apt/*.bin
    ;;
  manifest)
    dpkg-query -W --showformat='${Package}\t${Version}\n'
    ;;
  *)
    echo "unknown step: $step" >&2; exit 2 ;;
esac
