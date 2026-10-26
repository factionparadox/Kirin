# Russian learning kit

Kirin's second supported language is also a subject it teaches, with enough material on the machine to go from the alphabet to B2. Everything below is bundled into the image and works offline. Leave it all out with `build/kirin-build.sh --no-russian`.

| Component | Source | Licence / status | Size (approx.) | Installed at |
| --- | --- | --- | --- | --- |
| AI tutor: `qwen3:30b-a3b-instruct-2507-q4_K_M` | Ollama library | Apache 2.0 | 19 GB | Ollama models |
| Speech: Piper 2023.11.14-2 | [rhasspy/piper](https://github.com/rhasspy/piper) release, SHA-256 pinned in the builder | MIT | 26 MB | `/opt/kirin/piper` |
| Voices: Irina, Denis, Dmitri, Ruslan (medium) | [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) | MIT | ~250 MB | `/opt/kirin/russian/voices` |
| Textbook: *Между нами* (A1-A2), every page, PDF and lesson recording | [mezhdunami.org](https://mezhdunami.org) (University of Kansas), copied by `fetch-mezhdunami.py`; audio from the course's SoundCloud via [yt-dlp](https://github.com/yt-dlp/yt-dlp) (release checked against its SHA2-256SUMS) | CC BY-NC-ND 3.0: copied unchanged for personal, non-commercial use; only links and players are adapted to work offline | ~0.5 GB | `/opt/kirin/russian/mezhdunami` |
| Course library: FSI Russian FAST (books and 9 tapes) and Active Introduction; Peace Corps Russian (general course, competencies workbook, Kyrgyzstan and Turkmenistan lessons); DLI Russian Basic Course volumes; *Между нами* vocabulary lists and workbooks | [fsi-language-courses.org](https://www.fsi-language-courses.org/russian/), [ERIC](https://eric.ed.gov), mezhdunami.org | US government works (public domain); *Между нами* CC BY-NC-ND 3.0 | ~0.6 GB | `/opt/kirin/russian/library` |
| Words: 10,000 words banded A1-B2 (`packaging/russian/vocab.tsv`) | Derived from [OpenRussian](https://github.com/Badestrand/russian-dictionary) and [FrequencyWords](https://github.com/hermitdave/FrequencyWords); see `packaging/russian/VOCAB-SOURCES.md` | CC BY-SA 4.0 | 0.7 MB | `/usr/share/kirin/russian` |
| Audiobooks: 29 LibriVox recordings, A2-B2 (`packaging/russian/audiobooks.tsv`) | [LibriVox](https://librivox.org) via the Internet Archive, 64 kbit/s MP3 | Public domain | ~5 GB | `/opt/kirin/russian/audiobooks` |
| English Wiktionary, no pictures | [Kiwix](https://download.kiwix.org/zim/wiktionary/), newest `wiktionary_en_all_nopic_*.zim` | CC BY-SA | several GB | `/opt/kirin/russian/dictionary` |
| Russian Wiktionary, no pictures | Kiwix, newest `wiktionary_ru_all_nopic_*.zim` | CC BY-SA | ~1-2 GB | same |
| Russian Wikisource (literature), no pictures | Kiwix, newest `wikisource_ru_all_nopic_*.zim` | Public domain texts / CC BY-SA | ~2.3 GB | same |
| Russian Wikipedia | Kiwix, newest `wikipedia_ru_all_mini_*.zim` (every article's introduction); `--ru-wikipedia nopic` for full articles (~10 GB), `maxi` with pictures (~30 GB) or `none` | CC BY-SA | a few GB | same |
| ZIM reader: Kiwix | Flathub `org.kiwix.desktop` | GPL-3.0 | runtime | system Flatpak |

With everything at the defaults, the Russian kit adds about 35-40 GB to the image, so the ISO should still fit a 64 GB USB stick; the builder prints the final size and warns if it will not. Full Russian Wikipedia (`--ru-wikipedia nopic`) adds about 7 GB more and may not fit.

## Integrity

* Piper is pinned by SHA-256 in `build/kirin-build.sh`; every ZIM is checked against the `.sha256` Kiwix publishes; Ollama verifies model blobs by digest and the builder re-hashes them.
* Audiobooks are checked against the MD5 and SHA-1 the Internet Archive publishes for each file, and must be recordings in Russian.
* The voices and course files have no published checksums. `scripts/build/fetch-files.py` records each file's SHA-256 on first download (`work/payloads/russian/*.lock.json`) and refuses any later download that differs. Keep those lock files to make rebuilds reproducible.
* Voices are required. Everything else is optional: a source that has moved is reported and skipped, never replaced by something else.
* The `russian` audit checks the tutor model's blobs, Piper, all four voices, every library file, audiobook and textbook file against the hashes recorded at download, and the dictionaries.

## Kirin Learn commands

    kirin-learn path                                  # the route from A1 to B2, with your word progress
    kirin-learn russian [TEXT] [--level A1..C2]       # AI tutor; no TEXT starts an interactive lesson
    kirin-learn vocab [--level A1..B2] [--new N] [--reverse] [--say] [--stats]
    kirin-learn listen [--level A2|B1|B2] [--play N | --pick]
    kirin-learn read mezhdunami|wikisource|wikipedia|wiktionary-ru|wiktionary
    kirin-learn say TEXT [--voice irina|denis|dmitri|ruslan] [--output file.wav]
    kirin-learn library [--open]
    kirin-learn dictionary

Word progress is kept per user in `~/.local/share/kirin-learn/vocab.json`. The menu has launchers for each of these (Russian Words, Russian Audiobooks, Russian Study Path, *Между нами*, Wikisource, Wikipedia). The study guide is the `russian` lesson: `kirin-learn learn russian`.

## Not included

Proprietary courses and apps (Busuu, Duolingo, Babbel, commercial textbooks) cannot be bundled.

The full DLI Russian Basic Course (85 books and tapes) is no longer downloadable: fsi-language-courses.org made its copies private in October 2026. Kirin includes the DLI volumes that ERIC still publishes in full.
