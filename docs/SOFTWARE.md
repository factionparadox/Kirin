# Kirin software management

Kirin will replace the **openKylin Software Store** with dedicated tools for Flatpak application administration. It will keep APT/dpkg and the operating-system update machinery; a Software Store, an installer and a system updater are not interchangeable.

## Desktop tools

| Need | Application |
| --- | --- |
| Flatpak apps, remotes, rollback, cleanup | [Warehouse](https://github.com/flattool/warehouse) — io.github.flattool.Warehouse |
| Flatpak sandbox permissions | [Flatseal](https://github.com/tchx84/Flatseal) — com.github.tchx84.Flatseal |
| Native APT packages | Planned MX Package Installer port |
| Advanced native package administration | Proposed Synaptic |
| System updates | Retain openKylin update capability until a Kirin replacement passes testing |

Warehouse is a GTK/libadwaita application: verify visual/accessibility integration with UKUI. Warehouse handles installed Flatpaks and remotes; it is not primarily a curated app-store front page. Flatseal adds detailed permission administration.

Official sources: https://flathub.org/apps/io.github.flattool.Warehouse ; https://flathub.org/apps/com.github.tchx84.Flatseal ; https://docs.flatpak.org/en/latest/using-flatpak.html

## Removing the Software Store

openKylin's 3.0 release/update documentation mentions the Software Store. Published package sources use **kylin-software-center**, but the *complete installed binary package list for the exact 3.0 ISO is not yet audited*. Candidate names in the read-only image checker include that name and older/alternative names; they are not a licence to delete packages whose ownership has not been confirmed.

For a disposable image build root:

1. Record the official ISO hash and installed dpkg manifest; identify Software Store packages, launcher files, autostarts, daemons and service activations.
2. Simulate removal of only the confirmed packages through APT in a proper openKylin build environment. Inspect the transaction. **Stop** if it removes UKUI, APT/dpkg, the OS updater, login, the installer, AI models, or other protected components.
3. Purge reviewed store components or rebuild narrower dependent packages as needed. Prevent obsolete store metapackages from reinstalling the client.
4. Install Flatpak and any necessary desktop portals from compatible openKylin packages.
5. Configure Flathub with the official signed .flatpakrepo definition. Include system-wide Warehouse, Flatseal and required runtimes **in the build image**, not after a first-boot network download.
6. Re-run the read-only inventory audit after package and localisation changes.
7. Boot and install offline: Warehouse and Flatseal must start without internet, be visible in UKUI and manage already installed Flatpaks. Reconnect and check remote management, app installs/removals, permissions, system updates, British English and Russian.

**Do not purge kylin-installer merely because of its name.** Do not remove system update services without a working replacement. Keep upstream AI model payloads untouched.

## Package sources

openKylin Huanghe remains the base source. Debian, Ubuntu and MX sources are optional, signed, explicitly allowlisted and package-pinned. ABI compatibility must be tested; pinning does not make incompatible native packages safe. Prefer rebuilding useful packages for Kirin or using Flatpak when suitable.

## Automated check

A source-stage read-only checker is included:

~~~sh
python3 scripts/audit-software-image.py --root /path/to/unpacked-image
~~~

It inspects dpkg status and expected system-wide Flatpak deployment/desktop-export paths. The check is intentionally limited: a successful inventory does **not** prove dependency safety, desktop launch, portal integration or a functioning image.

**Status:** Nothing has been removed from an actual openKylin ISO in this repository. This document specifies the build/removal and acceptance contract.
