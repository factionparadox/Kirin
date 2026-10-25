# Kirin Linux

**Status: source-stage project; not a bootable operating-system image.**

Kirin is an educational, mutable Linux distribution project based on **openKylin 3.0** and UKUI. Its goals are OpenZFS with ZFSBootMenu boot environments, graphical ZFS management, an integrated APT ecosystem, desktop web applications, a separate coding assistant and offline-first Linux education.

## Preserve upstream AI and add coding

Keep **all AI models and functions shipped with openKylin**. Kirin adds Ollama with **Qwen2.5-Coder 7B Instruct** (`qwen2.5-coder:7b-instruct`) as a *second*, dedicated coding model. Its complete model payload must be present in the offline installation image; downloading it after installation is not acceptable. Upstream general-assistant models keep their original interfaces. No upstream AI payloads are removed by the source in this repository.

`scripts/check-image-contract.py` is intended to reject a candidate image if files in its explicit upstream AI inventory differ or Qwen's full declared model blobs are absent/incorrect. It is a staging check, not proof of a bootable ISO.

## Kirin Learn

Adapts the learn/explain/doctor educational design from [Archon/Cognoscenti](https://github.com/factionparadox/Archon) to openKylin, APT, systemd and OpenZFS.

- `kirin-learn browse` — offline interactive lesson browser
- `kirin-learn topics` and `kirin-learn learn packages` — read local lessons
- `kirin-learn explain 'apt update'` — vetted explanation, never command execution
- `kirin-learn doctor` — read-only executable inventory
- `kirin-learn tutor vim` — native `vimtutor`
- `kirin-learn tutor neovim` — Neovim's custom `:Tutor kirin-01-basics`
- `kirin-learn ask-code 'Explain this function'` — optional local Ollama coding assistance

**Vim, Neovim and their tutorials are mandatory base-image packages** (see `packaging/base-packages.txt`). The education CLI, tutor file and desktop launchers are shipped in this repository. The learning material remains usable with no AI, account or internet.

## Source verification and staging

```sh
python3 -m unittest discover -s tests -v
DESTDIR="$(mktemp -d)" sh scripts/install-education.sh
```

The staging installer writes only inside `DESTDIR`; it does not run APT, change the host or build an ISO.

## Not yet complete

This repository does **not** yet provide an integrated, installable openKylin ISO, native ZFS-root boot, GTK/Qt graphical ZFS controls, MX GUI port, or verified image containing the full Qwen model and all original openKylin AI files. These require an openKylin build environment and boot tests.

Systemd's `birthDate` exclusion is a downstream source patch requirement, **not** merely a version hold: see `docs/SYSTEMD-POLICY.md`.

Primary upstream references: [openKylin](https://www.openkylin.top/), [ZFSBootMenu](https://docs.zfsbootmenu.org/), [Neovim Tutor](https://neovim.io/doc/user/pi_tutor/), [Qwen2.5-Coder](https://ollama.com/library/qwen2.5-coder:7b-instruct).
