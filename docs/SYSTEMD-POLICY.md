# Remove the birthDate user-record field

Kirin inherits the author's requirement in Archon's `docs/SYSTEMD-POLICY.md`: downstream systemd must omit the optional `birthDate` user-record interface. The earlier idea of a generic `apt-mark hold` **does not meet this requirement**.

Upstream systemd describes the optional `birthDate` property in `docs/USER_RECORD.md`; this does not by itself impose age verification. See upstream systemd PR #40954.

Required before release: identify openKylin's actual systemd version and downstream patches, adapt and review Archon's version-sensitive source transformer, remove all field/serialization/CLI/tests/docs references without altering unrelated date parsing, rebuild the **entire matching split-package family**, validate userdb/homed/logind and user-record round-trips, and refuse to publish when upstream source differs from the audited patch expectations.

A downstream rebuild should receive security updates. Holding an old systemd forever is not a replacement for maintenance.

**Status:** upstream systemd first ships `birthDate` in systemd 261 (June 2026). The `systemd` build audit records the image's systemd version and fails if `birthDate` appears in systemd's shared library, `userdbctl`, `homectl`, `systemd-userdbd`, `systemd-homed` or `systemd-logind`. While openKylin ships an older systemd, Kirin meets this requirement with no patching; if an openKylin update brings systemd 261 or later, the audit fails and the downstream rebuild above becomes necessary. No patched systemd is built yet.

Debian 13 ships systemd 257 (before `birthDate`); Debian 14 is expected to ship a release that has it. A future Debian base would need the same rebuild.
