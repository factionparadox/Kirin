#!/bin/sh
# Full text of the installer scripts that size, create, mount and record swap, and the
# strings that say openKylin in its programs. Read-only.
#   sudo sh scripts/dev/probe-installer-swap.sh > /mnt/c/Users/Public/kirin-installer3.txt
R=${1:-$(cd "$(dirname "$0")/../.." && pwd)/work/rootfs}
S="$R/usr/share/kylin-os-installer"
for f in scripts/utils data/systemdatasize.sh scripts/autopart.sh scripts/autopart-efi.sh \
         scripts/prepare/10partition scripts/prepare/10partition-efi scripts/prepare/13mount-target \
         scripts/prepare/18setup-swapfile scripts/in_chroot/27generate-fstab scripts/in_chroot/genfstab \
         scripts/in_chroot/30update-initramfs ky-installer.cfg; do
  echo "=================== $f"; cat "$S/$f" 2>&1
done
echo "=================== openKylin strings in the installer programs"
for f in "$R/usr/bin/kylin-os-installer" "$R"/usr/lib/libK*.so.1.0.0 "$R"/usr/lib/libPlugin*.so.1.0.0; do
  [ "$(basename "$f")" = libKyLicense.so.1.0.0 ] && continue
  (strings -n 3 "$f"; strings -n 3 -el "$f") 2>/dev/null | grep -i openkylin | sort | uniq -c | sed "s#^#$(basename "$f"): #"
done
echo "=================== Qt resources"
for f in "$R/usr/bin/kylin-os-installer" "$R"/usr/lib/libK*.so.1.0.0; do
  (strings -n 4 "$f"; strings -n 4 -el "$f"; strings -n 4 -eb "$f") 2>/dev/null | grep -E '^:/|qrc:|\.(png|svg|jpg|gif|qss)$' | sort -u | head -60 | sed "s#^#$(basename "$f"): #"
done
