# Kirin branding

Applied to the image by `scripts/kirin-rebrand.py` and checked by the `branding` audit. Artwork lives in `packaging/branding/`.

| What | How |
| --- | --- |
| Boot splash | Plymouth theme `kirin` (`packaging/branding/plymouth/`): the Kirin Linux logo on a dark background, with password-prompt and message support. Selected inside the image, then every initramfs is rebuilt. If the rebuilt initramfs matches the ISO's kernel and still contains casper's live-boot scripts, it also replaces the ISO's `casper/initrd`, so the live session shows it too; otherwise the live session keeps openKylin's splash and the build says so. |
| Menu names | In `.desktop` display keys (Name, GenericName, Comment, Keywords and their translations) "openKylin" and "Kylin" become "Kirin". Exec, Icon and other keys are untouched, so the programs still run. |
| OS name | `NAME`/`PRETTY_NAME` in os-release and `DISTRIB_DESCRIPTION` in lsb-release read "Kirin Linux (openKylin 3.0 base)". `ID`, `VERSION_ID` and the codename stay openKylin's, because openKylin's updater and packages identify the system by them. |
| Boot menu (installed system) | `GRUB_DISTRIBUTOR="Kirin Linux"` via `/etc/default/grub.d/90-kirin.cfg`. |
| Fastfetch | System config `/etc/xdg/fastfetch/config.jsonc` with the Kirin ASCII logo and colours 24 25 31 32 39 117, and an OS line naming Kirin. |
| Icon | `kirin` in the hicolor theme (16–512 px) and `/usr/share/pixmaps/kirin.png`. |

| ISO boot menus | `scripts/build/iso-boot-config.py` rewrites the ISO's `boot/grub/grub.cfg` and `isolinux/*.cfg`: openKylin 3.0 boots every entry with `locale=zh_CN`, which made the live session and installer Chinese; it becomes `locale=en_GB.UTF-8` with a British keyboard. "Install openKylin" becomes "Install Kirin Linux". GRUB gets a Kirin background; isolinux's `splash.png` and `back.jpg` are replaced. `md5sum.txt` and `SHA256SUMS` are updated so the installer's media check passes. |
| Odd names | `packaging/branding/desktop-names.json` gives proper English and Russian names to launchers that don't rebrand cleanly (the OS installer, package installer, boot repair, AI assistant "Xiao K", manual and upstream community link). |
| Fastfetch package | openKylin 3.0 does not ship Fastfetch; it is installed from `packaging/extra-packages.txt` after the pinned Ubuntu/Debian repositories are added. |

openKylin's AI assistant supports custom "private" models through Settings → AI, but stores them through its own runtime, so Kirin documents the one-time setup (`kirin-learn learn ai`) rather than writing undocumented config. Alpaca is pre-connected.

## Desktop defaults

Applied by `scripts/kirin-polish.py` and checked by the `defaults` audit.

| What | How |
| --- | --- |
| Version | Kirin Linux 1.0: in os-release `PRETTY_NAME`, lsb-release, Fastfetch and `/etc/kirin-release`. |
| Hostname | `kirin`; the live session's user and host are `kirin` too (`/etc/casper.conf`, with `FLAVOUR` set so casper honours them). |
| Welcome to Kirin | `kirin-welcome` (GTK 3), started once at first login by `/etc/xdg/autostart/kirin-welcome.desktop`, and in the menu. Links Kirin Learn, the Russian tutor, courses and dictionary, Alpaca, Warehouse, LibreOffice and Settings; English or Russian by session language. |
| Taskbar | New users get Files, Terminal, Alpaca, LibreOffice, VLC, Kirin Learn and Settings pinned (UKUI `org.ukui.panel.taskManager` `quickLaunchers` in `/etc/skel`); apps that are not installed are skipped. |
| Default apps | `ukui-mimeapps.list` and `mimeapps.list`: WPS Office's Writer/Spreadsheet/Presentation/PDF handlers become LibreOffice's (PDF: the first installed viewer), and openKylin's music and video players become VLC. Only mappings whose target is installed change. |
| WPS Office | Removed (optional reviewed purge) with its add-on models in `/var/opt/kingsoft`, which `build/model-exclusions.txt` leaves out of the protected inventory. |
| Fastfetch | Runs when an interactive terminal opens (`/etc/bash.bashrc`). Turn off in Welcome to Kirin, or `touch ~/.config/kirin/no-fastfetch`. |
