#!/bin/sh
# ostree-tree.sh ROOT TREE: lay out the system in ROOT as an OSTree commit tree in TREE,
# matching openKylin 3.0's own commit: /etc in /usr/etc; /opt, /mnt, /srv and /tmp as
# symlinks into /var; the kernel and initramfs also in /usr/lib/modules/<version>/;
# an empty machine-id; empty mount points. Files are hard links (TREE must be on
# ROOT's filesystem), so nothing is copied and ROOT is never changed.
set -eu
root=${1:?root} tree=${2:?tree}
root=${root%/}
[ -d "$root/usr" ] && [ -d "$root/etc" ] || { echo "ostree-tree: $root is not a system root" >&2; exit 1; }
rm -rf "$tree"; mkdir -p "$tree"
for d in "$root"/* "$root"/.[!.]*; do
  [ -e "$d" ] || [ -L "$d" ] || continue
  case "${d#"$root"/}" in
    proc|sys|dev|run|tmp|sysroot|kirin-build|lost+found|media|mnt|opt|srv|home|root|ostree) continue ;;
  esac
  cp -al "$d" "$tree/"
done
mv "$tree/etc" "$tree/usr/etc"
rm -f "$tree/usr/etc/machine-id"; : > "$tree/usr/etc/machine-id"; chmod 0444 "$tree/usr/etc/machine-id"
mkdir -p "$tree/var/opt" "$tree/var/mnt" "$tree/var/srv" "$tree/var/tmp"
for d in opt srv mnt; do
  if [ -d "$root/$d" ] && [ ! -L "$root/$d" ]; then cp -al "$root/$d/." "$tree/var/$d/"; fi
done
chmod 1777 "$tree/var/tmp"
for link in opt:var/opt mnt:var/mnt srv:var/srv tmp:var/tmp media:run/media ostree:sysroot/ostree; do
  rm -rf "${tree:?}/${link%%:*}"; ln -s "${link#*:}" "$tree/${link%%:*}"
done
for d in backup data eth dev proc run sys sysroot home; do mkdir -p "$tree/$d"; done
install -d -m 0700 "$tree/root"
if [ -d "$root/root" ]; then cp -al "$root/root/." "$tree/root/"; fi
chmod 0700 "$tree/root"
n=0
for k in "$root"/boot/vmlinuz-*; do
  [ -f "$k" ] || continue
  ver=${k#"$root"/boot/vmlinuz-}
  [ -d "$tree/usr/lib/modules/$ver" ] || continue
  rm -f "$tree/usr/lib/modules/$ver/vmlinuz" "$tree/usr/lib/modules/$ver/initramfs.img"
  ln "$k" "$tree/usr/lib/modules/$ver/vmlinuz"
  if [ -f "$root/boot/initrd.img-$ver" ]; then ln "$root/boot/initrd.img-$ver" "$tree/usr/lib/modules/$ver/initramfs.img"; fi
  n=$((n + 1))
done
[ "$n" -gt 0 ] || { echo 'ostree-tree: no kernel in /boot with matching /usr/lib/modules' >&2; exit 1; }
echo "ostree-tree: $tree ready ($n kernel$( [ "$n" -eq 1 ] || echo s))"
