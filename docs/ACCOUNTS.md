# Kirin: local accounts, no openKylin cloud sign-in

**Kirin never requires a vendor account, openKylin ID, device binding, token check-ins or online activation to install, boot, update, operate UKUI or use its offline coding model.** Local Linux accounts, login, PAM, accountsservice, sudo/polkit, and normal UKUI user administration are explicitly preserved. ChatGPT/Claude web apps may offer their own voluntary, independent logins.

## Verified upstream integration

* openKylin's 3.0 release announcement explicitly describes the preinstalled **Token Center** and signing in and binding a device for cloud AI credits: https://www.openkylin.top/news/4099-en.html
* The openKylin Huanghe build archive publishes the source package **openkylin-token-center**: https://build.openkylin.top/openkylin/huanghe
* UKUI control centre's upstream English documentation describes **Cloud Account**, Kylin ID login and remote settings sync: https://gitee.com/openkylin/ukui-control-center/blob/cf66dc5e1a89f163ca4792a722d8e9aa03e50596/data/en_US/index.md
* The upstream 2026-10-14 update includes Token Centre and data-tracking fixes. That establishes account-related services exist upstream, **not** that any particular installed 3.0 ISO has been fully inventoried: https://www.openkylin.top/news/4166-en.html

## Build policy

1. **Before modification**, unpack the official openKylin 3.0 ISO into a disposable, offline image root; record the original package manifest, account-related services, AI model inventory and checksum.
2. Use the `scripts/audit-online-accounts.py --root <root> --plan` utility to enumerate blocked or unverified cloud-account packages/launchers and plan changes. The script is **read-only**; it does not purge packages or mutate the image.
3. In a disposable openKylin build root with APT properly configured, simulate `apt-get -s purge openkylin-token-center` and examine every removal. If this removes any protected local-account, UKUI or local AI components, **stop** and package a narrower patch. Do not use `autoremove` without examining the dependency closure.
4. Purge the verified Token Centre package during image construction, not on a host or user's installed system. For cloud-account integration embedded into UKUI Control Centre or other apps, **patch and rebuild** those packages against Huanghe, removing online-account entry points and background sync while retaining local user settings and AI functions. Determine actual plugin paths from packaged files before patching; do not blindly delete a shared library or panel.
5. Stage `scripts/stage-account-policy.sh` with `DESTDIR=<root>` to install APT priority -1 for `openkylin-token-center`, preventing future routine installation via APT. Verify `apt-cache policy openkylin-token-center` within the built image.
6. Run `python3 scripts/audit-online-accounts.py --root <root>` after every update, localisation pass and image build. Treat `BLOCK`, `REVIEW`, missing dpkg metadata and symlinks as failures. Ensure no cloud account sign-in prompts, token centre launchers, autostart jobs or cloud settings sync remain.
7. Boot the image offline and test local user creation/login, local UKUI settings, system updates, existing upstream local AI models, Ollama/Qwen and Web App Studio. Confirm offline use doesn't ask for a vendor account; only user-launched third-party webapps should request web credentials.

## Scope and limitations

The source-stage audit detects the confirmed package, *candidate* package names and declarative launchers/services. It is not proof of comprehensive removal. Compiled UKUI plugins, system-level D-Bus activation, code-embedded URLs and vendor APIs need package-specific source audits and runtime network verification. Do not equate account UI removal with proof of no background network traffic.

This repo currently contains **no extracted openKylin 3.0 installation image**. Therefore no claim of actual package removal or a successfully boot-tested account-free system is made.

Primary APT reference: https://manpages.debian.org/trixie/apt/apt_preferences.5.en.html
