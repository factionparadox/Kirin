# Offline image integration contract

Kirin is based on openKylin 3.0. **Retain every openKylin AI model and existing AI application** while adding the independent Ollama coding model. Never delete or replace the upstream payload to reduce ISO size.

An eventual image builder must:

1. Check the exact official upstream ISO and record its checksum, architecture and package metadata.
2. Inspect the actual image to identify model files and upstream services; do not guess their location.
3. Build an **explicit, nonempty SHA-256 upstream model inventory**, including every retained model file. Record package ownership and service configuration separately.
4. Stage a candidate containing the same upstream model files and their original application integration.
5. Include Vim, Neovim, offline lessons, tutors, Qwen2.5-Coder 7B Instruct, Ollama and the complete required Ollama manifests/blobs **before ISO generation**.
6. Run `scripts/check-image-contract.py` against staged image contents; reject missing or altered upstream files and missing, wrong-sized or wrong-hash coding-model blobs.
7. With network disconnected, boot and test UKUI, upstream AI functions, the local Qwen response, Vim and Neovim tutorials, OpenZFS pool persistence and selectable root environments.

Example staging audit:

```sh
python3 scripts/check-image-contract.py \
  --upstream-inventory upstream-models.json \
  --candidate-root /path/to/staged-root \
  --qwen-index qwen-blobs.json \
  --qwen-blobs /path/to/ollama/models/blobs
```

The coding model index is an explicit object such as `{"model":"qwen2.5-coder:7b-instruct","blobs":[{"sha256":"<64 hex digits>","size":123}]}`, generated from **actual downloaded and verified payloads**. Do not substitute sample blobs. The audit cannot by itself verify a bootable image, a functional inference runtime, completeness of an upstream inventory, or model licensing; those need additional testing and release review.

## APT repository policy

Retain openKylin Huanghe repositories as primary. Cross-distribution Debian/Ubuntu/MX sources are opt-in, authenticated and constrained by package allowlists and priority. APT pinning cannot make ABI-incompatible packages safe. Prefer Kirin-built compatibility packages for incompatible dependencies.

## ZFS

ZFS-root, ZFSBootMenu, boot-environment cloning, rollback and graphical storage controls remain separate release requirements. No current teaching component claims to implement or validate them.

## Language-localisation stage

After installing packages and staging the upstream AI payloads, use scripts/kirin-localise.py --root /path/to/staged-root --apply and --audit. Generate both en_GB.UTF-8 and ru_RU.UTF-8 locales inside the target image; test UKUI in both languages, and rerun the audit after package changes. See docs/LANGUAGES.md. Chinese catalogues may be excluded; never remove fonts or upstream model files.

## Vendor account-removal gate

Kirin must not ship openKylin ID, Token Centre, device registration or settings cloud sync. First inventory exact installed Huanghe packages and plugins; simulate dependency removal in the disposable target build environment. Purge the verified `openkylin-token-center` package, patch other confirmed account-dependent UI/service components, and preserve local Linux accounts, UKUI, installed AI model blobs and offline services. Stage the APT policy with `DESTDIR=/path/to/staged-root sh scripts/stage-account-policy.sh`, then run `python3 scripts/audit-online-accounts.py --root /path/to/staged-root` as a mandatory release gate. See `docs/ACCOUNTS.md` for source evidence, limitations and runtime tests.

## Software Store replacement

Kirin removes the openKylin Software Store (not the OS updater or APT/dpkg), and preinstalls the Flatpak runtime, Warehouse and Flatseal plus their dependencies and desktop exports into the OFFLINE image. Verify source package ownership and simulate removal before purging any Software Store component. The read-only image contract is checked by scripts/audit-software-image.py --root /path/to/staged-root. See docs/SOFTWARE.md. This cannot substitute for desktop and offline boot testing.
