# OpenZFS root

Kirin can install onto an OpenZFS root with ZFSBootMenu, automatic snapshots and boot environments. The normal openKylin installer stays available for an ordinary install.

## In the image (build)

| Part | Source | Checked by |
| --- | --- | --- |
| OpenZFS 2.4.1 (`zfs-dkms`, `zfsutils-linux`, `zfs-initramfs`, `zfs-zed`) | Ubuntu 26.04, whose 2.4.1 is patched for Linux 7.0. Only packages built from the `zfs-linux` source may come from Ubuntu; they are pinned there (`/etc/apt/preferences.d/83kirin-zfs`) to keep receiving its updates | APT signatures |
| ZFS kernel module | Compiled by DKMS during the build for every kernel in the image (openKylin 3.0: 7.0.0-3-generic) | `zfs` audit: a module for every kernel |
| ZFSBootMenu 3.1.0 (bundles OpenZFS 2.4.0, Linux 6.18), release and recovery EFI | [zbm-dev/zfsbootmenu](https://github.com/zbm-dev/zfsbootmenu) release | SHA-256 pinned in `build/kirin-build.sh`, taken from the release's `sha256.txt`, whose signify signature was verified against `releng/keys/zfsbootmenu.pub` |
| `kirin-zfs-install`, `kirin-be`, APT snapshot hook | this repository | unit tests (`tests/test_zfs.py`), `zfs` audit |

If the module does not build, the ZFS packages are removed again, the build carries on and the `zfs` audit fails, so the problem is visible. Upstream OpenZFS 2.4.2 and later also support Linux 7.0, if Ubuntu's package ever stops building.

**Secure Boot must be off.** Neither the DKMS-built module nor ZFSBootMenu is signed with keys the firmware trusts.

## Installing

From the live USB: **Install Kirin on ZFS** in the menu, or `sudo kirin-zfs-install`. It asks for the disk (never offering the USB stick it booted from), your user name and password, and whether to encrypt, then asks you to type the disk's name to confirm.

It follows [ZFSBootMenu's Ubuntu UEFI guide](https://docs.zfsbootmenu.org/en/latest/guides/ubuntu/uefi.html):

1. GPT: a 1 GB EFI system partition and the rest for ZFS.
2. Pool `zroot`: `ashift=12`, `autotrim=on`, zstd compression, POSIX ACLs, `compatibility=openzfs-2.3-linux` (so ZFSBootMenu's own OpenZFS can always read it). Optional native encryption, `aes-256-gcm`, passphrase typed at start-up.
3. Datasets: `zroot/ROOT/kirin` (`/`, `canmount=noauto`, the boot environment) and `zroot/home`.
4. Unpacks the live image onto them, creates your account (administrator), removes live-session-only packages, rebuilds the initramfs with ZFS.
5. Copies ZFSBootMenu to `EFI/ZBM` (plus a backup and the recovery build, and `EFI/BOOT/BOOTX64.EFI` for firmware that forgets boot entries), and adds UEFI boot entries.
6. Takes a snapshot called `installed`.

Rehearse it without touching a disk: `sudo kirin-zfs-install --dry-run --disk /dev/nvme0n1` prints every command.

## Snapshots and boot environments

* `/etc/apt/apt.conf.d/80kirin-zfs-snapshot` runs `/usr/lib/kirin/zfs-apt-snapshot` before every dpkg run: one `apt-YYYYMMDD-HHMMSS` snapshot per APT run, newest 20 kept. It does nothing on other filesystems and never blocks APT.
* `kirin-be list | snapshot | create | activate | rollback | destroy` manages them. Rollback never overwrites the running system: it clones the snapshot into a new boot environment and makes that the default.
* ZFSBootMenu can boot any boot environment or snapshot from its menu.

See the storage lesson: `kirin-learn learn storage`.

## Not yet

* A graphical snapshot and boot-environment manager.
* Installing alongside another operating system (the installer uses the whole disk).
