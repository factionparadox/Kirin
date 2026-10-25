# OpenZFS, datasets and boot environments

OpenZFS has checksums, snapshots and datasets. A snapshot captures a point-in-time state. A boot environment is a bootable system root; a snapshot is not automatically a boot environment or an off-device backup.

If OpenZFS is installed, try these read-only commands:

    zpool status
    zfs list
    zfs list -t snapshot

**Exercise:** Use `findmnt /` to identify your actual root filesystem. If it is not ZFS, there is no reason to change the disk just to complete the exercise.

Native ZFS-root and rollback are Kirin development goals, not functionality verified in this source stage.
