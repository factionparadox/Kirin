# Building the Kirin ISO

`build/kirin-build.sh` produces a Kirin installation ISO by **remastering the official openKylin 3.0 x86-64 ISO**. Remastering, rather than rebuilding from packages, is deliberate: it is the only way to guarantee that openKylin's own AI models and their integration reach Kirin byte-for-byte unchanged (see [IMAGE-BUILD.md](IMAGE-BUILD.md)).

This is the first build stage. The resulting ISO boots and installs with openKylin's own boot loader and installer on ext4, not OpenZFS. See [What this build does not do yet](#what-this-build-does-not-do-yet).

## Build host

- x86-64 Linux, run as root. **WSL2 works** on Windows if its virtual disk has room; Docker or another container needs `--privileged` for the bind mounts and chroot.
- At least **70 GB free** in the work directory, or about **150 GB** with the Russian learning kit. The upstream ISO, its unpacked tree, the unpacked root, the 4.7 GB coding model and the new squashfs all coexist.
- Python 3.11 or newer, `xorriso`, `squashfs-tools`, `curl` and `zstd`. On Debian or Ubuntu, install them with `apt install xorriso squashfs-tools curl zstd python3`.
- Internet access to openKylin's package mirrors (used by APT inside the image), `dl.flathub.org`, `github.com` (for the Ollama release) and `registry.ollama.ai` (for the model).

## Steps

1. Download the x86-64 ISO from <https://www.openkylin.top/downloads>.
2. Start the build from the repository root:

   ```sh
   sudo build/kirin-build.sh --iso openKylin-Desktop-V3.0-20260918-x86_64.iso
   ```

   Optionally add `--iso-sha256 HEX` to refuse an ISO that doesn't match openKylin's published checksum. Either way, the ISO's hash is recorded in the build record.

3. The build **stops after the inventory stage** (exit code 10). Review `work/upstream/upstream-models.json` and `work/upstream/upstream-models-owners.json`:
   - Every upstream AI model file should be listed.
   - Nothing unrelated should be listed. Delete any wrong entries, and add missing files with their `sha256sum`.
4. Continue past the review:

   ```sh
   sudo build/kirin-build.sh --iso … --from inventory --accept-inventory \
        --model-inventory work/upstream/upstream-models.json
   ```

5. The ISO, its `.sha256` and a `.build.json` record are written to `out/`.

The build resumes where it stopped. Completed stages are skipped. `--from STAGE` redoes a stage and everything after it, and `--only STAGE` runs a single stage.

## Stages

| Stage | What it does |
| --- | --- |
| preflight | Checks the host OS and architecture, root access, tools, Python version and free space |
| verify | Records the ISO's SHA-256, size and volume ID, and checks the hash if you passed `--iso-sha256` |
| extract | Unpacks the ISO tree and finds the root-filesystem squashfs (pass `--squashfs` if this is ambiguous), then unpacks it. openKylin 3.0's squashfs is about 7.5 GB, and the ISO records its size wrapped at 4 GiB, so extraction cuts it short; the build detects this and copies the full file straight out of the ISO (`scripts/build/recover-squashfs.py`), proving the copy matches what was already extracted |
| inventory | Lists candidate AI model files with hashes and owning packages, proves the list matches the untouched image, then **stops for review** |
| payloads | Downloads Ollama from its GitHub release and checks it against the release's `sha256sum.txt`; pulls `qwen2.5-coder:7b-instruct` and the Russian tutor `qwen3:30b-a3b-instruct-2507-q4_K_M`, verifying every blob; fetches Piper, the Russian voices, the course library and the Wiktionary ZIM ([RUSSIAN.md](RUSSIAN.md); skip with `--no-russian`) |
| customise | Applies the language policy and APT pin; installs the base packages; purges the Token Centre and Software Store; installs Warehouse and Flatseal system-wide from Flathub; installs Ollama, its service and the model; installs Kirin Learn; generates `en_GB` and `ru_RU` locales |
| audit | Runs the AI-payload contract, software, language and accounts audits |
| pack | Rebuilds the squashfs with the original compression and replaces it in the upstream ISO. The original BIOS/UEFI boot records are replayed, and `filesystem.size`, `filesystem.manifest` and `md5sum.txt` are updated if present |

## Safety gates

- **Package removal is fail-closed.** Each purge is simulated first. The build stops if APT would remove anything not requested, or anything protected: UKUI, APT/dpkg, the installer, the updater, login/PAM, Flatpak, kernels, and any package that owns an upstream model file. After reviewing `work/audit/purge-simulation.txt`, allow a specific extra removal with `--allow-removal PKG`. Protected packages can never be allowed.
- **The AI-payload contract is never waived.** If an inventoried upstream model changes or a coding-model blob is wrong, the build fails, even with `--test-build`.
- **Policy audits gate release.** These are the software, language and accounts audits. `--test-build` packs the image anyway for VM testing and names it `…-TEST-UNVERIFIED.iso`. A first build will probably need this, because the language audit flags Chinese-only menu labels that still need real translations.

## Testing the ISO

Boot it in a disposable VM with UEFI, at least 8 GB of RAM and 64 GB of disk, first **with networking disabled**. Work through step 7 of [IMAGE-BUILD.md](IMAGE-BUILD.md) and the runtime checks in [ACCOUNTS.md](ACCOUNTS.md) and [SOFTWARE.md](SOFTWARE.md). Check in particular that:

- Warehouse and Flatseal open offline;
- `ollama run qwen2.5-coder:7b-instruct` answers offline;
- the upstream AI features still work;
- `kirin-learn` runs;
- the installed system, not just the live session, carries all of the above.

## Testing the builder

`tests/mock-build/run.sh` runs the real builder end-to-end against stubbed `xorriso`, `squashfs` and `chroot` tools and a fake image. It checks the review stop, the purge refusal, the test-build label and model-tamper detection, and it needs root but no network. The Python helpers are covered by the normal `python3 -m unittest discover -s tests`.

## What this build does not do yet

- OpenZFS root, ZFSBootMenu and boot environments: these need their own installer work.
- The systemd `birthDate` removal from [SYSTEMD-POLICY.md](SYSTEMD-POLICY.md): openKylin's systemd is shipped unchanged.
- Patching UKUI Control Centre's cloud-account panels: the accounts audit only catches declarative launchers and services.
- The MX Package Installer port, Synaptic, Web App Studio and the graphical help centre.
- Kirin branding: the boot menu, installer and volume ID are still openKylin's.
- Image signing and Secure Boot changes. The upstream signed boot chain is kept as-is, since the boot files are not modified.
