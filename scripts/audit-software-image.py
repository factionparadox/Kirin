#!/usr/bin/env python3
"""Read-only release audit for Kirin's intended APT + Flatpak stack."""
import argparse
from pathlib import Path
import sys

FORBIDDEN = {"kylin-software-center", "ubuntu-kylin-software-center", "openkylin-software-center"}
REQUIRED = {"flatpak", "apt", "dpkg"}
FLATPAKS = ("io.github.flattool.Warehouse", "com.github.tchx84.Flatseal")

def installed_packages(status_text):
    result = set()
    for para in status_text.split("\n\n"):
        fields = {}
        for line in para.splitlines():
            if line and not line[0].isspace() and ": " in line:
                key, value = line.split(": ", 1)
                fields[key] = value
        if fields.get("Status") == "install ok installed" and "Package" in fields:
            result.add(fields["Package"])
    return result

def inspect(root):
    if not root.is_absolute() or not root.is_dir() or root.is_symlink() or root.resolve() == Path("/"):
        raise ValueError("audit requires a separate offline image directory, not /")
    status = root / "var/lib/dpkg/status"
    if not status.is_file():
        raise ValueError("offline image has no dpkg status file")
    installed = installed_packages(status.read_text(encoding="utf-8"))
    errors = [f"blocked software store still installed: {p}" for p in sorted(installed & FORBIDDEN)]
    errors += [f"required base package absent: {p}" for p in sorted(REQUIRED - installed)]
    for appid in FLATPAKS:
        app_dir = root / "var/lib/flatpak/app" / appid
        launcher = root / "var/lib/flatpak/exports/share/applications" / (appid + ".desktop")
        if not app_dir.is_dir() or not any(app_dir.iterdir()):
            errors.append(f"system Flatpak deployment absent: {appid}")
        if not launcher.is_file():
            errors.append(f"system Flatpak desktop export absent: {appid}")
    return errors

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        errors = inspect(args.root)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"AUDIT FAILED: {exc}", file=sys.stderr)
        return 2
    for error in errors:
        print(f"AUDIT FAILED: {error}", file=sys.stderr)
    if errors:
        return 1
    print("Kirin software image inventory passed; runtime integration still requires testing.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
