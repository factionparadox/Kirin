# Kirin APT repository

Kirin builds its own packages from `packaging/debs/<package>/spec.json` with `scripts/build/build-debs.py`. Each spec pins its upstream files by SHA-256 and declares its dependencies, so APT installs them (from openKylin, or the pinned Ubuntu/Debian repositories). The first package is **ani-cli**.

Packages reach users two ways:

1. **In the ISO** (works now): the image build builds and installs them.
2. **Signed APT repository** on GitHub Pages, `https://factionparadox.github.io/Kirin/apt`, so installed systems get updates with `apt upgrade`. Published by `.github/workflows/kirin-apt-repo.yml`. It needs a signing key, set up once:

## One-time setup

On your Arch machine:

```sh
export GNUPGHOME=~/kirin-signing && mkdir -p -m 700 "$GNUPGHOME"
gpg --batch --passphrase '' --quick-gen-key 'Kirin Linux Archive Signing Key' ed25519 sign never
gpg --armor --export-secret-keys 'Kirin Linux Archive Signing Key' > ~/kirin-signing/secret.asc
cd ~/kirin
gpg --armor --export 'Kirin Linux Archive Signing Key' > packaging/apt/kirin-archive-keyring.asc
gpg --with-colons --list-keys 'Kirin Linux Archive Signing Key' | awk -F: '/^fpr/{print $10; exit}' > packaging/apt/kirin-archive-keyring.fingerprint
git add packaging/apt/kirin-archive-keyring.* && git commit -m 'Add Kirin APT signing key' && git push
```

On GitHub, in the Kirin repository:

1. **Settings → Secrets and variables → Actions → New repository secret**: name `KIRIN_APT_SIGNING_KEY`, value: the whole contents of `~/kirin-signing/secret.asc`.
2. **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. **Actions → Kirin APT repository → Run workflow**.

Keep `~/kirin-signing` private and backed up: anyone with the secret key can publish packages Kirin systems will trust. Delete `secret.asc` once it is stored in GitHub and in your backup.

From then on, every image build adds the repository (verifying the committed key against its committed fingerprint), and every change under `packaging/debs/` republishes it.

## Adding a package

Create `packaging/debs/<name>/spec.json` (see `ani-cli`): `package`, `version` (end it in `-1kirinN`), `architecture`, `depends`, `summary`, `description`, and `files` with `url`, `sha256`, `dest` and `mode`. Pin URLs to a commit or release, never a moving branch.
