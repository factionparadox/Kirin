#!/bin/sh
# Stage education files into a packaging root. Never install packages or change a live OS.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
root=${DESTDIR:?Set DESTDIR to a disposable packaging directory}
case "$root" in /*) ;; *) echo 'DESTDIR must be absolute' >&2; exit 2;; esac
[ "$root" != / ] || { echo 'Refusing to install into /' >&2; exit 2; }
install -D -m 0755 "$here/kirin_learn.py" "$root/usr/bin/kirin-learn"
install -D -m 0755 "$here/kirin_welcome.py" "$root/usr/bin/kirin-welcome"
install -D -m 0755 "$here/scripts/kirin-fingerprint" "$root/usr/bin/kirin-fingerprint"
install -D -m 0644 "$here/share/autostart/kirin-welcome.desktop" "$root/etc/xdg/autostart/kirin-welcome.desktop"
for lesson in "$here"/lessons/*.md; do
  install -D -m 0644 "$lesson" "$root/usr/share/kirin/learn/topics/$(basename "$lesson")"
done
install -D -m 0644 "$here/share/nvim/site/tutor/kirin-01-basics.tutor" "$root/usr/share/nvim/site/tutor/kirin-01-basics.tutor"
for launcher in "$here"/share/applications/*.desktop; do
  install -D -m 0644 "$launcher" "$root/usr/share/applications/$(basename "$launcher")"
done
printf 'Staged Kirin Learn into %s\n' "$root"
