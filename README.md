# Kirin Linux

**An educational, mutable Linux desktop with local AI, recoverable system management and practical software tools.**

**Status: source-stage project.** Kirin is not yet a bootable or verified installation image. The features below are release goals unless explicitly marked as existing source code.

## Why Kirin exists

Kirin is based on **openKylin 3.0 (Huanghe)** and **UKUI 4.24**. It retains an approachable desktop and openKylin's existing offline AI capabilities, while adding Linux education, a dedicated coding model, OpenZFS-based system recovery, and straightforward software administration.

Inspired by [Archon/Cognoscenti](https://github.com/factionparadox/Archon), Kirin aims to **teach the user how the operating system works**. Lessons, command explanations, manual pages and read-only system inspection must work offline and without an account or AI. Users retain the ability to modify the system; snapshots and boot environments are intended to help recover from mistakes.

## Distribution specification

| Component | Kirin design |
| --- | --- |
| Foundation | openKylin 3.0 Huanghe, initially x86-64 |
| Desktop | UKUI 4.24 |
| Filesystem | OpenZFS root, independent persistent user datasets |
| Boot and recovery | ZFSBootMenu, snapshots, cloned boot environments, graphical ZFS administration |
| Native software | APT/dpkg, planned MX Package Installer port and Synaptic |
| Flatpak software | Flatpak and Flathub, **Warehouse** and **Flatseal** preinstalled |
| Replaced | openKylin Software Store (not the OS updater or APT/dpkg) |
| AI | Preserve every existing upstream model; add offline Ollama + Qwen2.5-Coder 7B Instruct |
| Web apps | Planned Web App Studio for ChatGPT, Claude and arbitrary websites |
| Learning | Kirin Learn, offline lessons, Vim, Neovim and native tutors |
| Russian study | Local AI tutor (Qwen3 30B), Piper Russian voices, public-domain DLI/FSI/Peace Corps courses, offline Wiktionary ([Russian learning kit](docs/RUSSIAN.md)) |
| Language | British English (en_GB.UTF-8) default; Russian (ru_RU.UTF-8) supported |
| Accounts | Local Linux accounts only; no mandatory Kylin ID, token centre, cloud sync or device registration |
| Init and security | systemd retained, with downstream birthDate field removal required; no SELinux requirement |

## Software without an app store

Kirin will **remove openKylin's Software Store** from its target image. It will be replaced with a dedicated Flatpak administration stack:

- **[Warehouse](https://github.com/flattool/warehouse)** — Flatpak ID io.github.flattool.Warehouse. Install and remove applications, manage remotes, inspect packages, clean application data and switch to available previous versions.
- **[Flatseal](https://github.com/tchx84/Flatseal)** — Flatpak ID com.github.tchx84.Flatseal. Inspect and manage Flatpak sandbox permissions.

The Flatpak runtime, both applications, their required runtimes and desktop launchers must be **included in the installation image**. Kirin must not require a first-boot download merely to open its Flatpak manager. Flathub is the intended default remote; users may add or remove others.

**APT remains first-class** for the OS, developer tools and native applications. Kirin's planned MX Package Installer port provides graphical APT management, with Synaptic for advanced package tasks. openKylin's repositories remain authoritative. Additional Debian, Ubuntu and MX sources are opt-in, authenticated and package-specific: broad cross-distribution upgrades must not replace the base's libraries unchecked.

We will **keep operating-system update capability** when removing the Software Store. The installed binary package names and dependencies must be verified against the actual 3.0 ISO before any purge. See [Software management and replacement plan](docs/SOFTWARE.md).

## Local AI and Web App Studio

**Do not remove or replace openKylin's existing AI models.** Preserve their offline functions and payloads. Kirin adds **Ollama with Qwen2.5-Coder 7B Instruct** as an additional, dedicated coding assistant. Its complete model files must already be on the ISO, usable without a first-boot download. See [offline model validation](docs/IMAGE-BUILD.md).

Web App Studio is planned to create UKUI launchers for ChatGPT, Claude and other user-chosen services, with isolated browser profiles. Website logins are entirely separate from Kirin's local operating-system accounts.

## Kirin Learn

The repository currently has an offline lesson library, a Python teaching CLI, desktop launchers and a Neovim tutor. Vim and Neovim are mandatory base-image packages. Learning is possible without AI, a subscription or internet access.

~~~sh
kirin-learn browse
kirin-learn learn packages
kirin-learn explain 'apt update'
kirin-learn doctor
kirin-learn tutor vim
kirin-learn tutor neovim
kirin-learn ask-code 'Explain ZFS datasets'
~~~

Lessons explain commands without executing them; system inspection is read-only. A graphical UKUI help centre is planned. See [education goals](docs/EDUCATION.md).

## Recovery and storage

Kirin is intended to install onto OpenZFS, boot using ZFSBootMenu and make root boot environments, snapshots and dataset administration accessible from UKUI. Package updates should be able to create recovery environments before system changes. Personal files should be stored separately from the switchable root environments.

The required ZFS kernel and userspace integration, root installer, boot-environment activation and rollback, upgrade transaction safety and hardware testing **remain outstanding**.

## Localisation, accounts and systemd

Kirin targets **British English** as its default and **Russian** as its second supported language. Chinese language packs, menu translations and regional defaults are to be excluded from the image, while preserving Unicode rendering, libraries, fonts and every upstream AI model. UKUI translation completeness needs actual image-level verification. [Languages](docs/LANGUAGES.md).

No openKylin ID, Token Centre, required vendor login, cloud settings sync or device-binding. Keep local user accounts, PAM, polkit and normal UKUI settings. [Accounts](docs/ACCOUNTS.md).

Systemd stays, but Kirin's downstream build must remove the optional birthDate user-record feature rather than merely freezing an arbitrary systemd version. [Systemd policy](docs/SYSTEMD-POLICY.md).

## Implementation status

| Present in this source repository | Still to build and test |
| --- | --- |
| Offline lessons, Kirin Learn CLI, editor tutoring and launchers | Installed and tested UKUI educational desktop |
| Offline AI-file integrity checking | Real model payloads embedded and functioning |
| Language policy and vendor-account audits | Translated, account-free openKylin image |
| Store-removal and Flatpak integration specification; image-inventory audit | Actual store removal, Warehouse/Flatseal offline integration and runtime tests |
| ISO remaster pipeline (`build/kirin-build.sh`), tested against a mock image | A real build from the openKylin 3.0 ISO and VM boot testing |
| Design and package manifests | OpenZFS-root ISO, boot environments, ZFS GUI, Web App Studio and MX GUI APT port |

**No finished ISO, verified graphical package manager, or ZFS-root boot is claimed.** A release requires a genuine openKylin build root, offline installation testing and checks on disposable drives or virtual machines.

## Building the ISO

`build/kirin-build.sh` remasters the official openKylin 3.0 ISO into a Kirin image. It needs an x86-64 Linux host (WSL2 works) with root, internet access and about 70 GB free, and it stops for a human review of the upstream AI model inventory before changing anything. See [Building the ISO](docs/BUILDING.md).

~~~sh
sudo build/kirin-build.sh --iso openKylin-Desktop-V3.0-20260918-x86_64.iso
~~~

## Source-stage checks

~~~sh
python3 -m unittest discover -s tests -v
sudo bash tests/mock-build/run.sh   # builder end-to-end against stub tools
DESTDIR="$(mktemp -d)" sh scripts/install-education.sh
# Once a candidate image has been unpacked into an OFFLINE staging root:
python3 scripts/audit-software-image.py --root /path/to/staged-root
python3 scripts/kirin-localise.py --root /path/to/staged-root --audit
python3 scripts/audit-online-accounts.py --root /path/to/staged-root
~~~

These checks inspect selected image contracts; they do not build or boot an ISO.

## Upstream credit

Kirin builds on [openKylin](https://www.openkylin.top/), [UKUI](https://www.ukui.org/), [OpenZFS](https://openzfs.github.io/openzfs-docs/), [ZFSBootMenu](https://docs.zfsbootmenu.org/), [Flatpak](https://docs.flatpak.org/), [Warehouse](https://github.com/flattool/warehouse), [Flatseal](https://github.com/tchx84/Flatseal), [Neovim](https://neovim.io/) and [Ollama](https://ollama.com/). Preserve applicable upstream licences and attribution.
