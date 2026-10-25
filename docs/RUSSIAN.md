# Russian learning kit

Kirin's second supported language is also a subject it teaches. Everything below is bundled into the image and works offline. Leave it out with `build/kirin-build.sh --no-russian`.

| Component | Source | Licence / status | Size (approx.) | Installed at |
| --- | --- | --- | --- | --- |
| AI tutor: `qwen3:30b-a3b-instruct-2507-q4_K_M` | Ollama library | Apache 2.0 | 19 GB | Ollama models |
| Speech: Piper 2023.11.14-2 | [rhasspy/piper](https://github.com/rhasspy/piper) release, SHA-256 pinned in the builder | MIT | 26 MB | `/opt/kirin/piper` |
| Voices: Irina, Denis, Dmitri, Ruslan (medium) | [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) | MIT | ~250 MB | `/opt/kirin/russian/voices` |
| Course library: FSI Russian FAST (book and 9 tapes) and Active Introduction, Peace Corps Russian, and the DLI Russian Basic Course volumes ERIC still publishes | [fsi-language-courses.org](https://www.fsi-language-courses.org/russian/) and [ERIC](https://eric.ed.gov) copies | US government works, public domain | ~0.5 GB | `/opt/kirin/russian/library` |
| Dictionary: English Wiktionary, no pictures | [Kiwix](https://download.kiwix.org/zim/wiktionary/), newest `wiktionary_en_all_nopic_*.zim` | CC BY-SA | several GB | `/opt/kirin/russian/dictionary` |
| Dictionary reader: Kiwix | Flathub `org.kiwix.desktop` | GPL-3.0 | runtime | system Flatpak |

## Integrity

* Piper is pinned by SHA-256 in `build/kirin-build.sh`; the ZIM is checked against the `.sha256` Kiwix publishes; Ollama verifies model blobs by digest and the builder re-hashes them.
* The voices and course files have no published checksums. `scripts/build/fetch-files.py` records each file's SHA-256 on first download (`work/payloads/russian/*.lock.json`) and refuses any later download that differs. Keep those lock files to make rebuilds reproducible.
* Voices are required. Course files are optional: a file whose source has moved is reported and skipped, never replaced by something else.
* The `russian` audit checks the tutor model's blobs, Piper, all four voices, every library file against its pinned hash, and the dictionary.

## Kirin Learn commands

    kirin-learn russian [TEXT] [--level A1..C2]   # AI tutor; no TEXT starts an interactive lesson
    kirin-learn say TEXT [--voice irina|denis|dmitri|ruslan] [--output file.wav]
    kirin-learn library [--open]
    kirin-learn dictionary

The study guide is the `russian` lesson: `kirin-learn learn russian`.

## Not included

Proprietary courses and apps (Busuu, Duolingo, Babbel, commercial textbooks) cannot be bundled. *Между нами* (mezhdunami.org) is a free online textbook under a non-derivative licence and is linked from the lesson rather than mirrored.


The full DLI Russian Basic Course (85 books and tapes) is no longer downloadable: fsi-language-courses.org made its copies private in October 2026. Kirin includes the DLI volumes that ERIC still publishes in full.
