# Hardware support

## Framework Laptop 13 Pro (Intel Core Ultra Series 3)

| Part | Status in Kirin |
| --- | --- |
| Kernel | openKylin 3.0's Linux 7.0; the 13 Pro needs 6.19 or newer. Framework supports Ubuntu 26.04 (also Linux 7.0) on it with no extra tweaks. |
| Fingerprint reader | Goodix, through **fprintd** and `libpam-fprintd`: login, lock screen, sudo and admin prompts. openKylin's own biometric service is masked so the two cannot fight over the reader. Enrol with **Fingerprint Setup** (menu, Welcome to Kirin) or `kirin-fingerprint`. UKUI's biometric settings page talks to the disabled service and will not see fprintd. |
| Fingerprint firmware | Readers on firmware `01000320` need Framework's update: `fwupdmgr refresh && fwupdmgr update` (see Framework's FPR-320 guide). |
| BIOS and device firmware | `fwupd`: `fwupdmgr refresh && fwupdmgr update`. |
| Battery charge limit, fans | Mainline `cros_charge-control` and `cros_ec_hwmon` drivers in Linux 7.0. The older out-of-tree `framework-laptop-kmod` (last updated 2024) is not needed. |
| Embedded controller, LEDs, input modules | `framework_tool` (Kirin package from Framework's official release); run with sudo. |
| Ambient light sensor | `iio-sensor-proxy`. |
| Ethernet Expansion Card | udev rule for a short autosuspend delay (from NixOS's Framework module). |

Sources: Framework's linux-docs (Ubuntu 26.04 and Fedora guides for the 13 Pro), NixOS's `framework-intel-core-ultra-series3` hardware module, framework.wiki.
