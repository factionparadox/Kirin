# Kirin Linux

**An educational Linux desktop with local AI, built on openKylin 3.0.** Kirin teaches you how your computer works, helps you code and learn Russian without an internet connection or an account, and runs well on the Framework Laptop 13 Pro.

**Status: Kirin Linux 1.0 builds.** `build/kirin-build.sh` turns the official openKylin 3.0 ISO into a bootable Kirin ISO, and every build audit passes. The AI models and big Russian material are now downloaded after installing, which makes the ISO far smaller than the 56 GB it used to be. Testing on real hardware is under way. The OpenZFS root installer is new and not yet tested on hardware; Web App Studio and a graphical APT manager are still plans; see [What's not done yet](#whats-not-done-yet).

## What you get

| | Kirin |
| --- | --- |
| Base | openKylin 3.0 (Huanghe), UKUI 4.24 desktop, Linux 7.0, x86-64 |
| Look and feel | Kirin Linux 1.0 branding: boot splash, boot menu, OS name, icons and menu names ([Branding](docs/BRANDING.md)); Welcome to Kirin on first login; kitty terminal (translucent, blurred) running fish, with Fastfetch |
| Language | British English by default, Russian supported; Chinese language packs and menu translations removed ([Languages](docs/LANGUAGES.md)) |
| Accounts | Local accounts only: no Kylin ID, token centre, cloud sync or device registration ([Accounts](docs/ACCOUNTS.md)) |
| Applications | LibreOffice (English and Russian), VLC, mpv, Proton VPN, Pass and Mail (official packages), Discord, Sober, ani-cli; WPS Office removed |
| Software | APT for the system, with Ubuntu 26.04 and Debian 13 added below openKylin for packages it lacks (never replacing its own); Flatpak with Warehouse and Flatseal instead of openKylin's Software Store ([Software](docs/SOFTWARE.md)) |
| Local AI | Ollama with Qwen2.5-Coder 7B (coding) and Qwen3 30B (Russian tutor), chat in Alpaca; openKylin's own AI models and assistant removed. Models download once with Kirin Content; after that everything runs offline and nothing leaves the computer. Tuned for a laptop: a model stays loaded between questions and only one is in memory at a time |
| Learning | Kirin Learn: offline Linux lessons, safe command explanations, Vim and Neovim tutors ([Education](docs/EDUCATION.md)) |
| Russian, A1 to B2 | The *Между нами* textbook with audio, FSI, DLI and Peace Corps courses, a 10,000-word spaced-repetition drill, 29 LibriVox audiobooks, Russian Wikisource, Wikipedia and Wiktionary, Piper voices and the AI tutor, with a study plan from the alphabet to B2 ([Russian learning kit](docs/RUSSIAN.md), [learning Russian with Kirin](#learning-russian-with-kirin)) |
| Hardware | Tuned for the Framework Laptop 13 Pro (Intel Core Ultra Series 3): fingerprint login with fprintd, GPU video decoding, current Intel microcode and thermald from Ubuntu 26.04, power profiles, firmware updates with fwupd, `framework_tool`, zram swap ([Hardware](docs/HARDWARE.md)) |
| OpenZFS root | Optional installer with an OpenZFS root (encryption optional), separate `/home`, ZFSBootMenu, a snapshot before every APT change and `kirin-be` boot environments for rollback; the normal openKylin installer stays available ([ZFS](docs/ZFS.md)) |
| Downloads | **Kirin Content** fetches the AI models, course library, dictionaries, reading and audiobooks after installing, checking every file; openly licensed packs also come from Kirin's own GitHub mirror, so they cannot vanish ([Content](docs/CONTENT.md)) |
| Kirin packages | Built from pinned upstream sources and published as a signed APT repository ([Kirin repo](docs/KIRIN-REPO.md)) |

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
   * **Install Kirin Linux**, openKylin's graphical installer, for an ordinary install.
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
| Removing systemd's `birthDate` user field | [Systemd policy](docs/SYSTEMD-POLICY.md) |
| Signed Kirin APT repository live | The pipeline exists; it needs its signing key ([Kirin repo](docs/KIRIN-REPO.md)) |
| Full UKUI translation check | Automated audits pass; menus still need a human read-through in English and Russian |

## Development checks

~~~sh
python3 -m unittest discover -s tests -v
bash tests/mock-build/run.sh             # the whole builder, end to end, against stub tools
~~~

## Credits

Kirin is assembled almost entirely from other people's work, and keeps their licences and attribution:

* **System:** [openKylin](https://www.openkylin.top/) and [UKUI](https://www.ukui.org/), [Ubuntu](https://ubuntu.com/) and [Debian](https://www.debian.org/) packages, [Flatpak](https://flatpak.org/), [Warehouse](https://github.com/flattool/warehouse), [Flatseal](https://github.com/tchx84/Flatseal), [kitty](https://sw.kovidgoyal.net/kitty/), [fish](https://fishshell.com/), [Fastfetch](https://github.com/fastfetch-cli/fastfetch), [Neovim](https://neovim.io/)
* **AI:** [Ollama](https://ollama.com/), [Qwen](https://github.com/QwenLM) models, [Alpaca](https://github.com/Jeffser/Alpaca), [Piper](https://github.com/rhasspy/piper) and its voices
* **Russian:** *Между нами* (University of Kansas), FSI, DLI and Peace Corps courses (via [fsi-language-courses.org](https://www.fsi-language-courses.org/) and [ERIC](https://eric.ed.gov/)), [LibriVox](https://librivox.org/) readers and the [Internet Archive](https://archive.org/), [Kiwix](https://kiwix.org/) and the Wikimedia projects, [OpenRussian](https://en.openrussian.org/), [FrequencyWords](https://github.com/hermitdave/FrequencyWords)
* **Hosting:** [GitHub](https://github.com/) releases for Kirin's content mirror
* **Storage:** [OpenZFS](https://openzfs.org/), [ZFSBootMenu](https://zfsbootmenu.org/)
* **Hardware:** [Framework](https://frame.work/) (`framework_tool`, Linux guides), [fprintd/libfprint](https://fprint.freedesktop.org/), [fwupd](https://fwupd.org/), and the [nixos-hardware](https://github.com/NixOS/nixos-hardware) Framework modules
* **Inspiration:** [Archon/Cognoscenti](https://github.com/factionparadox/Archon)
