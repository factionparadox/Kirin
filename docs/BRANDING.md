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

Still to do: the live ISO's GRUB menu text and the installer's Chinese strings need the ISO's actual `boot/grub/grub.cfg` and installer files to be inspected first.
