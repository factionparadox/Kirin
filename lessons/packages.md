# APT and trustworthy package sources

APT resolves dependencies and uses signed repository indexes to locate packages. dpkg tracks local installed packages.

Try these read-only commands:

    apt-cache policy vim
    apt list --installed
    man apt_preferences

A large repository ecosystem needs explicit boundaries: adding Debian, Ubuntu or MX packages must not silently replace openKylin's core libraries. External sources should be opt-in with verified identities and package-specific pinning. Pinning alone does not solve compatibility problems.

**Exercise:** Inspect `apt-cache policy neovim`. Identify the candidate version and package origin without installing anything.
