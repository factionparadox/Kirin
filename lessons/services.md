# systemd services

systemd manages services and startup relationships. A unit file can describe how a service starts and its dependencies.

Read-only inspection:

    systemctl status
    systemctl list-unit-files --type=service
    systemctl --version

Consult `man systemctl` and `man systemd.unit`. Do not enable, stop or change services merely to see what they do.

**Exercise:** Locate a network-related unit and inspect its status. Inspection should not change its state.
