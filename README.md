# Kirin Linux

**A private, educational Linux desktop for the Framework Laptop 13 Pro, with local AI and the UKUI desktop.** Kirin teaches you how your computer works and helps you code and learn Russian from the alphabet to B2. It has no accounts, no cloud services and no telemetry, and its AI runs on the laptop itself.

Kirin starts from openKylin 3.0's packages, which provide the UKUI 4.24 desktop and Linux 7.0, and removes the rest of openKylin. Its vendor accounts, cloud services, software store, AI models, Chinese defaults and branding are gone. Kirin adds its own installer, storage, learning tools, applications and hardware support, and audits the result on every build.

**Status: Kirin Linux 1.0 builds, and every build audit passes.** The ISO is about 12 GB. The AI models and large learning material are downloaded after installing with Kirin Content. The live session runs on real hardware. The graphical installer fixes are new and waiting for their first real install:

* it now installs Kirin's own system;
* no swap or backup partition;
* Kirin branding throughout.

The OpenZFS installer has not been tried on hardware yet. See [What's not done yet](#whats-not-done-yet).

## What Kirin changes

Kirin is a remaster, not a fork: it takes the official openKylin 3.0 ISO apart, changes it and puts it back together, so openKylin's security updates keep arriving. Everything below is done by `build/kirin-build.sh` and checked by an audit that fails the build if it comes undone.

| Area | What Kirin does |
| --- | --- |
| Accounts and cloud | Kylin ID, the token centre, cloud sync and device registration removed; local accounts only ([Accounts](docs/ACCOUNTS.md)) |
| AI | openKylin's AI assistant and every AI model it shipped removed (the build proves none is left); Ollama with models you choose instead |
| Software | openKylin's Software Store replaced by Flatpak with Warehouse and Flatseal; Ubuntu 26.04 and Debian 13 added below openKylin for packages it lacks, never replacing its own ([Software](docs/SOFTWARE.md)) |
| Language | British English by default, Russian supported; Chinese language packs, menu translations and the Chinese boot locale removed ([Languages](docs/LANGUAGES.md)) |
| Branding | Kirin Linux everywhere you look: boot menu and splash, OS name, menus, wallpaper, and inside openKylin's installer (its background, logo, slides and licence) ([Branding](docs/BRANDING.md)) |
| Installer | openKylin's graphical installer installs Kirin: the build commits Kirin into the OSTree repository it deploys from. No swap partition (Kirin swaps to compressed RAM), no 16-100 GB backup partition, English messages. Plus Kirin's own OpenZFS installer |
| systemd | openKylin 3.0's systemd 259 predates the `birthDate` user-record field (added in 261); an audit fails the build if an update ever brings it in ([Systemd policy](docs/SYSTEMD-POLICY.md)) |
| Hardware | Newer Intel microcode, thermald and Wi-Fi regulatory data from Ubuntu 26.04, fingerprint login, firmware updates and Framework tools ([Hardware](docs/HARDWARE.md)) |

## What you get

| | Kirin |
| --- | --- |
| Desktop | UKUI 4.24 on Linux 7.0 (x86-64), Kirin branding, Welcome to Kirin on first login, kitty terminal (translucent, blurred) running fish with Fastfetch |
| Applications | LibreOffice (English and Russian), VLC, mpv, Proton VPN, Pass and Mail (official packages), Discord, Sober, ani-cli |
| Local AI | Ollama with Qwen2.5-Coder 7B (coding) and Qwen3 30B (Russian tutor), chat in Alpaca. Models download once with Kirin Content; after that everything runs offline and nothing leaves the computer. Tuned for a laptop: a model stays loaded between questions and only one is in memory at a time |
| Learning | Kirin Learn: offline Linux lessons, safe command explanations, Vim and Neovim tutors ([Education](docs/EDUCATION.md)) |
| Russian, A1 to B2 | The *Между нами* textbook with audio, FSI, DLI and Peace Corps courses, a 10,000-word spaced-repetition drill, 29 LibriVox audiobooks, Russian Wikisource, Wikipedia and Wiktionary, Piper voices and the AI tutor, with a study plan from the alphabet to B2 ([Russian learning kit](docs/RUSSIAN.md), [learning Russian with Kirin](#learning-russian-with-kirin)) |
| Hardware | Tuned for the Framework Laptop 13 Pro (Intel Core Ultra Series 3): fingerprint login with fprintd, GPU video decoding, power profiles, firmware updates with fwupd, `framework_tool`, zram swap ([Hardware](docs/HARDWARE.md)) |
| OpenZFS root | Optional installer with an OpenZFS root (encryption optional), separate `/home`, ZFSBootMenu, a snapshot before every APT change and `kirin-be` boot environments for rollback ([ZFS](docs/ZFS.md)) |
| Downloads | **Kirin Content** fetches the AI models, course library, dictionaries, reading and audiobooks after installing, checking every file; openly licensed packs also come from Kirin's own GitHub mirror, so they cannot vanish ([Content](docs/CONTENT.md)) |
| Kirin packages | Built from pinned upstream sources; a signed APT repository is ready to publish once it has its key ([Kirin repo](docs/KIRIN-REPO.md)) |

## Building the ISO

You need an x86-64 Linux machine (WSL2 works) with root, internet access, about 70 GB free while building (200 GB with `--content bundled`), and the official `openKylin-Desktop-V3.0-20260918-x86_64.iso`.

~~~sh
sudo build/kirin-build.sh --iso openKylin-Desktop-V3.0-20260918-x86_64.iso
~~~

The output is `out/kirin-YYYYMMDD-amd64.iso` with its `.sha256` and a `.build.json` record. Write it to a USB 3 stick with [Ventoy](https://www.ventoy.net/) or a raw writer.

Useful options:

| Option | What it does |
| --- | --- |
| `--from STAGE` / `--only STAGE` | Redo a stage and what follows, or run one stage (`preflight verify extract inventory payloads customise audit pack`) |
| `--refresh` | After changing only Kirin's own files (branding, defaults, lessons, launchers), re-apply them and repack, without reinstalling packages |
| `--test-build` | Pack even if a policy audit fails (the failures are listed in `.build.json`) |
| `--content on-demand\|bundled` | Big material downloaded after installing (default), or all of it in the ISO for fully offline use (about 40 GB more) |
| `--no-russian` | Leave out the Russian kit |
| `--ru-wikipedia mini\|nopic\|maxi\|none` | How much of Russian Wikipedia to include (default `mini`) |
| `--compression zstd\|gzip\|xz` | Root filesystem compression (default zstd, if the kernel supports it) |
| `--no-extra-repos` | Do not add the Ubuntu and Debian repositories |

Downloads are verified against published checksums where they exist and pinned on first download where they do not. Nothing is fetched twice. Full details: [Building the ISO](docs/BUILDING.md), [Image build checks](docs/IMAGE-BUILD.md).

## Installing

1. Write the ISO to a USB 3 stick with Ventoy and boot it (normal mode, not Ventoy's memdisk mode). The live session runs from the stick, so a fast stick makes it far more pleasant.
2. On a new Framework 13 Pro, set the date and time in the BIOS first: with the factory clock, installers can hang on the boot splash.
3. Choose an installer:
   * **Install Kirin Linux**, the graphical installer, for an ordinary ext4 install. The disk becomes EFI, `/boot`, the system (60% of the disk, up to 100 GB) and your data: no swap partition and no backup partition.
   * **Install Kirin on ZFS** (`sudo kirin-zfs-install`) for an OpenZFS root with snapshots and rollback. It erases the whole disk you choose, and needs **Secure Boot turned off**. Rehearse first with `sudo kirin-zfs-install --dry-run`. See [ZFS](docs/ZFS.md).

## First steps after installing

~~~sh
fwupdmgr refresh && fwupdmgr update     # BIOS, fingerprint reader and other firmware
kirin-fingerprint                       # enrol a finger (or Fingerprint Setup in the menu)
sudo kirin-content                      # download the AI models and Russian material you want
kirin-learn browse                      # Linux lessons
kirin-learn path                        # the Russian study plan, A1 to B2
~~~

## Kirin Learn

~~~sh
kirin-learn browse                       # offline lessons
kirin-learn explain 'apt update'         # what a command does, without running it
kirin-learn tutor vim | neovim           # interactive editor tutors
kirin-learn learn storage                # OpenZFS, snapshots and boot environments
kirin-learn ask-code 'Explain ZFS datasets'
kirin-learn russian                      # AI Russian tutor; /say, /level B1, /quit
kirin-learn vocab --say                  # today's Russian words
kirin-learn listen --level B1            # audiobooks at your level
kirin-learn read wikisource              # Russian literature in Kiwix
~~~

Lessons explain commands without running them, and system inspection is read-only. Everything works offline without an account; only `ask-code` and `russian` use the local AI.

## Learning Russian with Kirin

Start with `kirin-learn path`: it lays out what to study at each level and tracks your word progress. Reaching B2 takes roughly **900-1,200 hours** for an English speaker, which is about **12-18 months at two to three hours a day**, or three years at an hour a day. Watching a favourite series dubbed in Russian becomes possible at A2 with Russian subtitles and comfortable around B2.

Kirin covers the courses, words, listening, reading and practice with an AI. It cannot give you real conversation, and B2 needs plenty of it:

* **A class.** Local adult-education Russian courses add a teacher and speaking practice every week.
* **Language exchange.** Apps such as HelloTalk and Tandem pair you with Russian speakers learning English; start texting at A1 and add weekly calls around A2.
* **Short bursts.** On your phone, a flashcard app or Kirin's audiobooks beat doomscrolling in a queue.

## What's not done yet

| Planned | Notes |
| --- | --- |
| Graphical snapshot and boot-environment manager | `kirin-be` and ZFSBootMenu do it today from the terminal and boot menu |
| Hardware test of the ZFS installer | Rehearse with `sudo kirin-zfs-install --dry-run`; Secure Boot must be off |
| Graphical APT manager (MX Package Installer port) | APT, Warehouse and Flatseal work today |
| Web App Studio | Launchers for web apps with isolated browser profiles |
| Test of the graphical installer fixes | Kirin commit, no swap or backup partition, branding: awaiting the first real install |
| Patched systemd, if openKylin ever moves to 261+ | Not needed with systemd 259; the `systemd` audit says when it is ([Systemd policy](docs/SYSTEMD-POLICY.md)) |
| Debian base | A possible future rebase once Debian 14 ships UKUI 4.20 or newer; almost all of Kirin would carry over |
| Signed Kirin APT repository live | The pipeline exists; it needs its signing key ([Kirin repo](docs/KIRIN-REPO.md)) |
| Full UKUI translation check | Automated audits pass; menus still need a human read-through in English and Russian |

## Development checks

~~~sh
python3 -m unittest discover -s tests -v
bash tests/mock-build/run.sh             # the whole builder, end to end, against stub tools
~~~
