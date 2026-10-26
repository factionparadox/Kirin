# OpenZFS, datasets and boot environments

Kirin can install onto **OpenZFS**, a filesystem that checksums every block, compresses data, and takes instant snapshots. Choose **Install Kirin on ZFS** from the live USB (or run `sudo kirin-zfs-install`) instead of the normal installer.

## The layout Kirin creates

| Name | What it is |
| --- | --- |
| `zroot` | the **pool**: the whole ZFS partition, optionally encrypted |
| `zroot/ROOT/kirin` | the **boot environment**: your system, mounted at `/` |
| `zroot/home` | your files, kept separate so rolling the system back never touches them |

**ZFSBootMenu** starts before Kirin. It finds the boot environments in the pool, asks for the passphrase if the pool is encrypted, and boots the default one. Press Escape during its countdown to choose another, or Ctrl+S on an entry to see its snapshots.

## Snapshots

A **snapshot** is a read-only picture of a dataset at one moment. It takes no time and no space at first; it grows only as the live data changes away from it.

* Before every `apt` change, Kirin snapshots the system automatically (`apt-…`), keeping the newest 20.
* The installer leaves one called `installed`.
* Take your own: `sudo kirin-be snapshot before-experiment`.

A snapshot is not a backup: it lives on the same disk. Copy important files elsewhere too.

## Boot environments and going back

    kirin-be list                          # boot environments and snapshots (read-only)
    sudo kirin-be rollback apt-20261101-0930
    sudo kirin-be create test              # a copy of the running system to experiment in
    sudo kirin-be activate kirin           # make kirin the default again
    sudo kirin-be destroy test

`rollback` never overwrites the running system. It **clones** the snapshot into a new boot environment and makes that the default, so the system you are using stays in the boot menu until you destroy it. Every boot environment has `canmount=noauto`: two datasets trying to mount at `/` would stop the computer booting.

## Read-only commands to explore

    zpool status          # pool health, disk errors, scrub results
    zfs list              # datasets, space used, mount points
    zfs list -t snapshot  # snapshots
    zfs get compressratio zroot   # how much compression is saving
    findmnt /             # which dataset is your root

**Exercise:** run `kirin-be list`, then `sudo kirin-be snapshot lesson`, then `kirin-be list` again. Install a small package with `sudo apt install cowsay` and look once more: there is an `apt-…` snapshot from just before it. Remove it with `sudo apt purge cowsay`.

If `findmnt /` does not say `zfs`, Kirin was installed with the normal installer: everything here still works for learning on a spare disk, but not for your root.
