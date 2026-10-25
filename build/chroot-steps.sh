#!/bin/sh
# Runs INSIDE the disposable image chroot, invoked by build/kirin-build.sh.
# Never run this on a real system.
set -eu
[ -f /kirin-build/IN_CHROOT ] || { echo 'chroot-steps.sh: not inside a Kirin build chroot' >&2; exit 2; }
export DEBIAN_FRONTEND=noninteractive LC_ALL=C.UTF-8
apt_opts='-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold'

list() { sed -e 's/#.*//' -e 's/[[:space:]]//g' -e '/^$/d' "$1"; }

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
