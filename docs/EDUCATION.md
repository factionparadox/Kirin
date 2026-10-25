# Kirin's educational purpose

Kirin incorporates the design of the author's Archon/Cognoscenti Linux learning centre: offline lessons, read-only component inspection, explanations that never execute entered commands, and links to installed upstream manuals. It is adapted to **APT, UKUI, OpenZFS and systemd**.

The learner should understand what components do and how to inspect their actual system, not have to trust a chatbot. Educational features must work without Ollama, a GPU, an account or internet connectivity. Local Qwen is a supplementary coding tutor.

| Topic | Exercise |
|---|---|
| Terminal | Use `pwd`, `ls -la`, `man` |
| Editors | Learn Vim and Neovim, edit a disposable file, save/undo |
| APT | Inspect package origins and repository priorities |
| Services | Inspect systemd units without enabling them |
| ZFS | Distinguish snapshots, datasets, boot environments and backups |
| AI | Verify model output against manuals and offline references |

Kirin provides `vimtutor`, Neovim's native `:Tutor` and a custom `.tutor` exercise under `/usr/share/nvim/site/tutor`. Neither editor's user configuration is overwritten.

A future graphical UKUI Help application should integrate the same locally installed lessons, `man` pages, package metadata and safe system inspection. This is an outstanding UI milestone, **not** part of the tested CLI implementation.

Learning design reference: [Archon/Cognoscenti](https://github.com/factionparadox/Archon).
