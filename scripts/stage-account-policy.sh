#!/bin/sh
# Stage APT account policy in an offline packaging root. Never purge packages.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
root=${DESTDIR:?Set DESTDIR to an offline staging directory}
case "$root" in /*) ;; *) echo 'DESTDIR must be absolute' >&2; exit 2 ;; esac
[ "$root" != / ] || { echo 'Refusing to stage onto /' >&2; exit 2; }
[ -d "$root" ] && [ ! -L "$root" ] || { echo 'DESTDIR must be an existing directory, not a symlink' >&2; exit 2; }
target="$root/etc/apt/preferences.d"
[ ! -L "$root/etc" ] && [ ! -L "$root/etc/apt" ] && [ ! -L "$target" ] || { echo 'Refusing symlinked path' >&2; exit 2; }
install -d -m 0755 "$target"
install -m 0644 "$here/packaging/apt/preferences.d/90kirin-no-token-centre" "$target/90kirin-no-token-centre"
printf 'Staged Kirin APT account-policy pin to %s\n' "$target"
