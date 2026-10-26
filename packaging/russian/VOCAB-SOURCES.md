# Sources for vocab.tsv

`vocab.tsv` (10,000 Russian words banded A1–B2) is derived data, released under
**CC BY-SA 4.0** like its main source. Regenerate with `scripts/dev/make-vocab.py`.

| Source | Version | Licence | Used for |
| --- | --- | --- | --- |
| [OpenRussian dictionary data](https://github.com/Badestrand/russian-dictionary) (openrussian.org, from Wiktionary and its users) | commit `50e210c4803237779cb562bc1abcea529066031c` | CC BY-SA 4.0 | words, stress marks, English meanings, gender, aspect pairs, inflected forms |
| [FrequencyWords](https://github.com/hermitdave/FrequencyWords) `content/2018/ru/ru_full.txt` (OpenSubtitles 2018 word counts) | commit `525f9b560de45753a5ea01069454e72e9aa541c6` | MIT (code), CC BY-SA 4.0 (content) | how common each word is |

Levels: words are ranked by how often they (and their inflected forms) occur in
film and TV subtitles, then cut at the cumulative vocabulary sizes of the Russian
state test (TORFL / ТРКИ): A1 780 words, A2 1,300, B1 2,300, B2 10,000. This is an
approximation of the official lexical minimums, not a copy of them: expect the odd
word in a surprising band.
