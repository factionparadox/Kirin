#!/usr/bin/env python3
"""Offline Kirin image localisation; never runs on the live root."""
import argparse
import json
import re
import sys
from pathlib import Path

ZH = re.compile(r"^zh(?:$|[_-](?:CN|TW|HK|SG|Hans|Hant)$)", re.I)
ZH_NAME = re.compile(r"(?:^|[_.-])zh(?:[_-](?:CN|TW|HK|SG|Hans|Hant))?(?=[_.-]|$)", re.I)
ZH_KEY = re.compile(r"^\s*[A-Za-z][A-Za-z0-9-]*\[zh(?:[_-][A-Za-z0-9@-]+)?\]\s*=", re.I)
CJK = re.compile("[\u3400-\u9fff]")
LOCALE_DIRS = ("usr/share/locale", "usr/share/locale-langpack", "usr/share/man", "usr/share/help")
CATALOG_DIRS = ("usr/share/qt5/translations", "usr/share/qt6/translations",
                "usr/share/ukui/translations", "usr/share/kylin/translations")
DESKTOP_DIRS = ("usr/share/applications", "usr/share/desktop-directories",
                "usr/share/xsessions", "etc/xdg/autostart")
POLICY = {
    "etc/locale.gen": "en_GB.UTF-8 UTF-8\nru_RU.UTF-8 UTF-8\n",
    "etc/default/locale": "LANG=en_GB.UTF-8\nLANGUAGE=en_GB:en\n",
    "etc/locale.conf": "LANG=en_GB.UTF-8\n",
    "etc/default/keyboard": 'XKBMODEL="pc105"\nXKBLAYOUT="gb"\nXKBVARIANT=""\nXKBOPTIONS=""\nBACKSPACE="guess"\n',
    "etc/dpkg/dpkg.cfg.d/90kirin-languages": (
        "# Suppress Chinese-language catalogues on future package installs.\n"
        + "".join(f"path-exclude=/usr/share/{p}/zh*/*\n" for p in ("locale", "locale-langpack", "man", "help"))
        + "".join(f"path-exclude=/{p}/*_zh*.qm\n" for p in CATALOG_DIRS)
    ),
    "usr/share/kirin/locale-policy.json": json.dumps({
        "default": "en_GB.UTF-8", "available": ["en_GB.UTF-8", "ru_RU.UTF-8"],
        "keyboards": ["gb", "ru"], "preserve_upstream_ai": True
    }, indent=2) + "\n",
}

def root_check(root):
    if not root.is_absolute() or not root.is_dir() or root.is_symlink() or root.resolve() == Path("/"):
        raise ValueError("requires an existing nonsymlink offline image root other than /")
    return root

def inside(root, rel, final_link_ok=False):
    """Path of rel under root, refusing symlinked components (optionally not the last)."""
    path = root
    parts = Path(rel).parts
    for i, part in enumerate(parts):
        path = path / part
        if path.is_symlink() and not (final_link_ok and i == len(parts) - 1):
            raise ValueError(f"symlink in image path: {path}")
    return path

def discover(root):
    # Symlinks are only ever removed as links, never followed: a zh_CN link to
    # another locale (e.g. zh_CN -> zh_Hans, or a hostile one to ru_RU) loses the
    # link while its target is judged on its own name.
    files, dirs, menus, untranslated, links = [], [], [], [], []
    for rel in LOCALE_DIRS:
        folder = inside(root, rel)
        if folder.is_dir():
            for child in folder.iterdir():
                if ZH.match(child.name):
                    if child.is_symlink():
                        links.append(child)
                    elif child.is_dir():
                        for p in child.rglob("*"):   # rglob does not descend into linked directories
                            if p.is_symlink(): links.append(p)
                            elif p.is_file(): files.append(p)
                        dirs.append(child)
    for rel in CATALOG_DIRS:
        folder = inside(root, rel)
        if folder.is_dir():
            for p in folder.rglob("*"):
                if ZH_NAME.search(p.stem) and p.suffix.lower() in (".qm", ".mo", ".ts", ".po", ".json"):
                    if p.is_symlink(): links.append(p)
                    elif p.is_file(): files.append(p)
    for rel in DESKTOP_DIRS:
        folder = inside(root, rel)
        if folder.is_dir():
            for p in folder.rglob("*.desktop"):
                if p.is_symlink(): continue   # never rewrite through a link; targets in these folders are scanned directly
                raw = p.read_text(encoding="utf-8")
                kept = [x for x in raw.splitlines(keepends=True) if not ZH_KEY.match(x)]
                new = "".join(kept)
                if new != raw: menus.append((p, new))
                for line in kept:
                    if line.startswith(("Name=", "GenericName=", "Comment=")) and CJK.search(line):
                        untranslated.append(f"{p.relative_to(root)}: untranslated default: {line.strip()}")
    return sorted(set(files)), dirs, menus, untranslated, sorted(set(links))

def run(root, mode):
    files, dirs, menus, untranslated, links = discover(root)
    if mode == "plan":
        for p in links: print("REMOVE LINK:", p.relative_to(root))
        for p in files: print("REMOVE:", p.relative_to(root))
        for p, _ in menus: print("CLEAN MENU:", p.relative_to(root))
        for rel in POLICY: print("WRITE:", rel)
    elif mode == "apply":
        for p in links: p.unlink()      # removes the link itself only
        for p in files: p.unlink()
        for d in dirs:
            for sub in sorted((p for p in d.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
                if not any(sub.iterdir()): sub.rmdir()
            if not any(d.iterdir()): d.rmdir()
        for p, content in menus: p.write_text(content, encoding="utf-8")
        for rel, value in POLICY.items():
            path = inside(root, rel, final_link_ok=True)
            # e.g. openKylin's etc/default/locale is a link to locale.conf: replace the
            # link with Kirin's own file rather than writing through it.
            if path.is_symlink(): path.unlink()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding="utf-8")
    elif mode == "audit":
        problems = [f"Chinese translation: {p.relative_to(root)}" for p in files]
        problems += [f"Chinese translation link: {p.relative_to(root)}" for p in links]
        problems += [f"Chinese desktop translation: {p.relative_to(root)}" for p, _ in menus]
        for rel, content in POLICY.items():
            path = inside(root, rel, final_link_ok=True)
            if path.is_symlink() or not path.is_file() or path.read_text(encoding="utf-8") != content:
                problems.append(f"locale policy missing/modified: {rel}")
        for item in problems: print("FAIL:", item)
        if problems: return 1
    for item in untranslated: print("NEEDS TRANSLATION:", item)
    if untranslated: return 1
    print("Kirin language policy check complete (runtime UKUI translation QA still required)")
    return 0

def main(argv=None):
    parser = argparse.ArgumentParser(description="Stage English UK / Russian into Kirin offline image")
    parser.add_argument("--root", required=True, type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ("plan", "apply", "audit"):
        modes.add_argument("--" + mode, action="store_true")
    args = parser.parse_args(argv)
    try:
        root = root_check(args.root)
        mode = next(x for x in ("plan", "apply", "audit") if getattr(args, x))
        return run(root, mode)
    except (OSError, ValueError, UnicodeError) as e:
        print("REFUSED:", e, file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
