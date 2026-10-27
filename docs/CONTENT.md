# Kirin Content: downloads after installing

Kirin's ISO carries the system and its small learning tools. The large, optional material is downloaded afterwards with **Kirin Content** (menu: *Kirin Content*, Welcome to Kirin: *Downloads*, or `sudo kirin-content`).

| Pack | What | Size | From | Checked against |
| --- | --- | --- | --- | --- |
| `ai-coder` | Qwen2.5-Coder 7B: `kirin-learn ask-code`, Alpaca | 4.7 GB | Ollama registry | Ollama's per-blob SHA-256 digests |
| `ai-tutor` | Qwen3 30B: `kirin-learn russian`, Alpaca | 18.6 GB | Ollama registry | Ollama's per-blob SHA-256 digests |
| `ru-course` | FSI, DLI and Peace Corps books and audio; Между нами workbooks | 0.7 GB | Kirin mirror, else the original sites | mirror checksums, else hashes pinned on first download |
| `ru-dictionaries` | English and Russian Wiktionary for Kiwix | ~9 GB | Kiwix | Kiwix's published SHA-256 |
| `ru-reading` | Russian Wikisource (classics) and Wikipedia (introductions) | ~6 GB | Kiwix | Kiwix's published SHA-256 |
| `ru-audiobooks` | 29 LibriVox recordings, A2-B2 | ~5 GB | Kirin mirror, else the Internet Archive | mirror checksums, else the Archive's MD5 and SHA-1 |

    kirin-content                          # pick from a list
    kirin-content list                     # what is installed
    sudo kirin-content install ai-tutor ru-course
    sudo kirin-content install all
    sudo kirin-content remove ru-reading

Interrupted downloads resume: run the same command again. `kirin-learn` tells you which pack to fetch when something is missing.

**Always in the ISO:** Piper and the four Russian voices, the 10,000-word list (`kirin-learn vocab`) and the Между нами textbook with its audio (`kirin-learn read mezhdunami`). Its licence allows a personal copy, not a public mirror, so it is never downloaded later.

**Building a fully offline ISO instead:** `build/kirin-build.sh --content bundled` puts every pack in the image (about 40 GB more).

## Kirin's mirror

Sources disappear: in October 2026 the DLI Russian course was made private overnight. Kirin keeps its own copy of the openly licensed packs as assets of a GitHub release (`content-v1` on factionparadox/Kirin), split into parts under GitHub's 2 GB limit:

| Mirrored | Licence |
| --- | --- |
| `ru-course` (course library) | US government works (public domain); Между нами workbooks CC BY-NC-ND 3.0, unchanged |
| `ru-audiobooks` | Public domain (LibriVox) |
| `ru-voices` (also used by the build) | MIT (Piper voices) |

Not mirrored: the AI models (Ollama's registry is the source), the Wikimedia ZIMs (Kiwix keeps them current) and the Между нами textbook site copy (personal use only).

`packaging/content/mirror.json` lists every part's SHA-256 and the whole archive's. Kirin Content and the builder try the mirror first, verify each part, the joined archive and every file inside it (`SHA256SUMS`), unpack safely, and fall back to the original sources if anything fails.

### Publishing or refreshing the mirror

On the build machine, after a build with `--content bundled` (so the files are in `work/payloads/russian`), with the GitHub CLI logged in once (`gh auth login`):

    scripts/publish-content.sh              # packs, splits, uploads to the content-v1 release
    git add packaging/content/mirror.json && git commit -m 'Content mirror' && git push

`--dry-run` packs and writes `mirror.json` without uploading. A new release name (`--release content-v2`) keeps the old one intact.
