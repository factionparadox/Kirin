#!/bin/sh
# Dump what Kirin needs to know about openKylin's graphical installer, from a built
# image root (default ~builder/kirin/work/rootfs). Read-only.
#   sudo scripts/dev/probe-installer.sh > /mnt/c/Users/Public/kirin-installer2.txt
R=${1:-$(cd "$(dirname "$0")/../.." && pwd)/work/rootfs}
[ -d "$R/usr/share/kylin-os-installer" ] || { echo "no installer in $R" >&2; exit 1; }
L=$(ls "$R"/var/lib/dpkg/info/*os-installer*.list 2>/dev/null)
echo "== packages"; ls "$R"/var/lib/dpkg/info/ | grep -i installer | grep '\.list$'
echo "== files (no translations, icons)"; cat $L | grep -v -e '\.mo$' -e '\.qm$' -e '\.ts$' -e '/icons/' -e '/doc/' | sort
echo "== config files"
for f in $(cat $L) $(find "$R/etc" -iname '*installer*' 2>/dev/null | sed "s#^$R##"); do
  case "$f" in *.ini|*.cfg|*.conf|*.json|*.yaml|*.yml|*setting*) [ -f "$R$f" ] && { echo "--- $f"; head -c 4000 "$R$f"; echo; } ;; esac
done
echo "== swap outside translations"
grep -rIn -i swap $(cat $L | grep -v -e '\.ts$' -e '\.qm$' | sed "s#^#$R#" | while read f; do [ -f "$f" ] && echo "$f"; done) 2>/dev/null | grep -v '^Binary' | head -80
echo "== swap in binaries"
for f in $(cat $L | grep -e /bin/ -e /lib/ -e /sbin/ | sed "s#^#$R#"); do
  [ -f "$f" ] && strings "$f" 2>/dev/null | grep -i -e swap -e systemsetting -e '\.ini' | sed "s#^#$(basename "$f"): #" | head -40
done
echo "== CJK msg/echo lines in scripts"
grep -rIn -P 'msg .*[\x{4e00}-\x{9fff}]' "$R/usr/share/kylin-os-installer/scripts" 2>/dev/null | sed "s#$R##" | head -120
echo "== LANGUAGES case defaults"; grep -rIl 'case ${LANGUAGES}' "$R/usr/share/kylin-os-installer/scripts" | sed "s#$R##"
echo "== openKylin in installer text files"
grep -rIl -i openkylin $(cat $L | sed "s#^#$R#" | while read f; do [ -f "$f" ] && echo "$f"; done) 2>/dev/null | sed "s#$R##" | head -40
echo "== openKylin in binaries and .qm"
for f in $(cat $L | grep -e /bin/ -e /lib/ -e '\.qm$' | sed "s#^#$R#"); do
  [ -f "$f" ] || continue
  n=$( (strings "$f"; strings -el "$f"; strings -eb "$f") 2>/dev/null | grep -ci openkylin)
  [ "$n" -eq 0 ] || echo "$n $(echo "$f" | sed "s#$R##")"
done
echo "== images"
cat $L | grep -i -e '\.png$' -e '\.jpg$' -e '\.svg$' -e '\.gif$' | grep -v /icons/ | while read f; do
  [ -f "$R$f" ] && echo "$(stat -c %s "$R$f") $f"; done | head -80
echo "== kernel command line options"; grep -rn -i -e kyswapfile -e 'automatic' "$R/cdrom" "$R"/boot/grub/grub.cfg 2>/dev/null | head
echo "== live boot menu"; grep -n -i -e swap -e linux "$(dirname "$R")"/iso/boot/grub/grub.cfg 2>/dev/null | head -20
