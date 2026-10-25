# Kirin localisation policy

Kirin uses **British English** (en_GB.UTF-8) as the system, installer, desktop and documentation default. **Russian** (ru_RU.UTF-8) is the second supported language and must be selectable during installation and within UKUI. The default keyboard is British (gb); Russian (ru) must be available as an installer/user option.

Chinese language packs, message catalogues, translated menu entries and Chinese-only input-method defaults are excluded from Kirin's distribution image. Preserve Unicode support, fonts, applications, shared libraries and every upstream openKylin AI model: text rendering and model output must still support arbitrary languages.

## Stage the image

Run after installing packages into an OFFLINE unpacked image root, then regenerate locales there using the image's libc locale tooling and test both languages:

    python3 scripts/kirin-localise.py --root /path/to/root --plan
    python3 scripts/kirin-localise.py --root /path/to/root --apply
    python3 scripts/kirin-localise.py --root /path/to/root --audit

The tool rejects the running root (/), cleans known gettext/Qt Chinese catalogue locations and .desktop localisation keys, configures en_GB and ru_RU, and stages dpkg path exclusions for subsequent package installation. It never changes AI model files or fonts. It does not run locale-gen or APT itself. The image builder must ensure generated locales are present, and must audit after any package installation/upgrade: dpkg path exclusions cannot remove keys inside .desktop files.

## Remaining language work

* Inspect actual openKylin package dependencies before removing Chinese-specific input-method or language packages. Never blindly autoremove packages; keep upstream AI applications intact.
* Provide proper English and Russian translations for Chinese-only base menu labels, UKUI settings, installer, updater, Web App Studio, ZFS administrator, first-run UI and help. Never invent translations by renaming unrelated programs.
* Run the image audit after package updates and use maintained package patches if needed to keep .desktop translations from returning.
* Test on an actual installed openKylin 3.0 image: British spelling and formats, Russian menus and input, offline lessons, model operation, normal UTF-8 filenames, and UKUI dialog/screenshots. Static scanning alone cannot prove that all hard-coded Chinese UI strings are removed.

Sources: Debian Locale guidance (https://wiki.debian.org/Locale), dpkg path exclusion documentation (https://manpages.debian.org/unstable/dpkg/dpkg.1.en.html), systemd localectl (https://manpages.debian.org/unstable/systemd/localectl.1.en.html).

**Status:** Source-stage implementation, not a completed translated or boot-tested ISO.
