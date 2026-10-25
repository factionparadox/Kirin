# Learn Russian with Kirin

Kirin ships a Russian study kit that works offline:

| Tool | What it is | Open it |
| --- | --- | --- |
| Course library | Public-domain US government courses: FSI Russian (FAST, with audio, and Active Introduction), Peace Corps Russian, and several Defense Language Institute (DLI) Russian Basic Course volumes (lessons, a reader, dialogue guides and a dictionary). | `kirin-learn library` |
| Dictionary | The English Wiktionary, offline in Kiwix: meanings, stress, IPA, full declension and conjugation tables. | `kirin-learn dictionary` |
| Voices | Piper text-to-speech with four Russian voices (Irina, Denis, Dmitri, Ruslan). | `kirin-learn say 'Привет, как дела?'` |
| AI tutor | Qwen3 30B, a local model that corrects your Russian and explains grammar in English. | `kirin-learn russian` |

The books and audio were written by people who teach Russian for a living; DLI trains military linguists with them. Treat them as the course, and the AI as a practice partner.

## Where to start

1. **The alphabet and sounds.** Open `DLI Russian Basic Course/Courses/Phase 1/Mod 01.pdf` with its audio in `Audio/Phase 1/`. Read along, pause, repeat aloud.
2. **One lesson a day.** Work through DLI Phase 1 and 2 in order. Do the matching workbook and taped exercises.
3. **Want a faster survival course first?** `FSI Russian/FAST` is a short course with eight tapes.
4. **Grammar questions:** the DLI *Grammar Reference Book* volumes, or ask the tutor and check its answer there.

## A daily routine (about 45 minutes)

* 20 min: one DLI lesson with its audio. Shadow the speakers: repeat each line straight after them.
* 10 min: look up new words in the dictionary. Note the stress (молоко́) and the case endings.
* 10 min: write five sentences with the new words and paste them into `kirin-learn russian`. Read its corrections.
* 5 min: listen to your corrected sentences with `kirin-learn say '…' --voice denis`.

## The AI tutor

    kirin-learn russian                       # interactive lesson; /say, /level B1, /quit
    kirin-learn russian 'How do I say "I would like a coffee"?'
    kirin-learn russian --level A2 'Я хочу пойти в магазин вчера.'

It runs entirely on this computer through Ollama; nothing is sent online. The first answer takes a while as the 19 GB model loads into memory.

**It can be wrong**, most often about stress and rarer endings. When it matters, check the dictionary or the DLI books. The tutor is told to say when it is unsure.

## What is not included

Apps such as Busuu, Duolingo and Babbel are proprietary and cannot be bundled; use them in a web browser if you subscribe. *Между нами* (mezhdunami.org) is a free online first-year textbook used at several universities, worth opening when you are online.

**Exercise:** say `kirin-learn say 'Меня зовут …'` with your name, then ask the tutor to explain why it is *меня* and not *я*.
