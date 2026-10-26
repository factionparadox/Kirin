# Learn Russian with Kirin

Kirin ships a Russian study kit that works offline, with enough material to take you from the alphabet to **B2**, a confident, independent level. Start with the plan:

    kirin-learn path

| Tool | What it is | Open it |
| --- | --- | --- |
| Textbook | *Между нами*, a first-year university course (A1-A2) with its lesson audio, copied for offline use. | `kirin-learn read mezhdunami` |
| Course library | FSI Russian FAST (with tapes) and Active Introduction, Peace Corps Russian courses, DLI Russian Basic Course volumes, and the *Между нами* workbooks. | `kirin-learn library` |
| Words | 10,000 words banded A1-B2, with stress marks, drilled by spaced repetition. | `kirin-learn vocab` |
| Audiobooks | About 30 LibriVox recordings of Russian folk tales and classics, sorted by level. | `kirin-learn listen` |
| Reading | Russian Wikisource (the classics in Russian) and Russian Wikipedia, offline. | `kirin-learn read wikisource` |
| Dictionaries | English Wiktionary (meanings, stress, full tables) and the Russian Wiktionary (definitions in Russian, for B1 and up). | `kirin-learn dictionary`, `kirin-learn read wiktionary-ru` |
| Voices | Piper speech with four Russian voices. | `kirin-learn say 'Привет, как дела?'` |
| AI tutor | Qwen3 30B, a local model that corrects your Russian and explains grammar in English. | `kirin-learn russian` |

The courses and books were written by people who teach Russian for a living. Treat them as the course, and the AI as a practice partner.

## The route to B2

Reaching B2 takes roughly 600-700 hours of study. An hour a day gets you there in about two years; it is the daily habit that matters.

* **A1:** *Между нами* Units 1-5 with the audio, FSI FAST Lessons 1-5, the A1 words (780).
* **A2:** *Между нами* Units 6-9 and its workbooks, the rest of FSI FAST, the Peace Corps course, the A2 words. Start listening to fairy tales (`kirin-learn listen --level A2`).
* **B1:** the DLI volumes and reader, the B1 words, Pushkin, Tolstoy and Chekhov as audiobooks with the text open in Wikisource.
* **B2:** a Russian Wikipedia article a day, look words up in the Russian Wiktionary, novels as audiobooks, the B2 words (7,700), and long conversations and essays with the tutor.

Move on when a level's words are mostly mastered (`kirin-learn vocab --stats`) and the tutor rarely corrects you at that level.

## A daily routine (about an hour)

* 25 min: one lesson from the textbook or course, with its audio. Shadow the speakers: repeat each line straight after them.
* 10 min: words. `kirin-learn vocab --say` reviews what is due and adds ten new words; add `--reverse` to type the Russian yourself.
* 10 min: listening. An audiobook chapter at your level; read the same text on Wikisource first if it is hard.
* 15 min: write or talk. Paste five sentences (or, later, a paragraph) into `kirin-learn russian --level A2` and read the corrections; hear them with `kirin-learn say '…' --voice denis`.

## The AI tutor

    kirin-learn russian                       # interactive lesson; /say, /level B1, /quit
    kirin-learn russian 'How do I say "I would like a coffee"?'
    kirin-learn russian --level A2 'Я хочу пойти в магазин вчера.'

It runs entirely on this computer through Ollama; nothing is sent online. The first answer takes a while as the 19 GB model loads into memory.

**It can be wrong**, most often about stress and rarer endings. When it matters, check the dictionary or the course books. The tutor is told to say when it is unsure.

## Words

    kirin-learn vocab                 # today's reviews plus 10 new words at your level
    kirin-learn vocab --level B1 --new 20 --say
    kirin-learn vocab --reverse       # see the English, type the Russian (stress marks and ё optional)
    kirin-learn vocab --stats

The word levels come from how common each word is, cut at the sizes of the Russian state exam (TORFL) vocabulary lists. They are a good guide, not an official list.

## What is not included

Apps such as Busuu, Duolingo and Babbel are proprietary and cannot be bundled; use them in a web browser if you subscribe. The full DLI Russian Basic Course is no longer published online; Kirin has the volumes that are.

**Exercise:** say `kirin-learn say 'Меня зовут …'` with your name, then ask the tutor to explain why it is *меня* and not *я*.
