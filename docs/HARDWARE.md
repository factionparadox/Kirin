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
| Graphics (Xe3, `xe` driver) | Mesa 26.0.3 and the Panther Lake GuC/HuC/GSC and display firmware are already in openKylin. Kirin adds `mesa-vulkan-drivers`, `intel-opencl-icd` and `vulkan-tools`. |
| Video decode and encode | openKylin has no Intel VA-API driver, so video used the CPU. Kirin adds Ubuntu's `intel-media-va-driver-non-free` (falls back to the free one), oneVPL (`libvpl2`, `libmfx-gen1.2`) and `vainfo`. |
| Audio | SOF firmware and Panther Lake topologies are in openKylin's `linux-firmware`. `alsa-ucm-conf` (the per-machine audio profiles) is taken from Ubuntu 26.04 if Ubuntu's is newer. |
| Wi-Fi 7 (Intel BE211) | Firmware from `linux-firmware`; `wireless-regdb` for 6 GHz channels. |
| CPU | `intel-microcode`, `thermald`, `power-profiles-daemon` (what Framework's battery guide uses; UKUI's power settings still work alongside it). `intel_gpu_top` from `intel-gpu-tools`. |
| Thunderbolt / USB4 | `bolt` authorises docks and devices. |
| Kernel module options | `/etc/modprobe.d/kirin-framework.conf`: `nvme noacpi=1` (lower suspend drain) and blacklist `cros-usbpd-charger` (unused by Framework's EC; logs a boot error). Both from NixOS's Framework module. |

### Packages taken from Ubuntu when newer

`packaging/prefer-ubuntu.txt` lists hardware data packages (`alsa-ucm-conf`, `alsa-topology-conf`, `intel-microcode`, `thermald`, `wireless-regdb`). For each, the build uses Ubuntu 26.04's version only when its upstream version is newer than openKylin's and nothing else would come from Ubuntu with it, then pins that package to Ubuntu so it keeps getting Ubuntu's updates. `work/audit/prefer-ubuntu.log` shows each decision. Everything else stays openKylin's.

### Live USB stuck on the boot splash

On a new 13 Pro, set the date and time in the BIOS (or update the BIOS) first: with the factory clock, Ubuntu 26.04 and other installers can sit on the splash screen for many minutes. Press Esc on the splash to see the boot log.

### Checking it works

```
vainfo | grep -i -E 'driver|H264|HEVC|AV1'      # iHD driver and hardware codecs
fprintd-list "$USER"                             # Goodix reader found
ls /lib/firmware/intel/iwlwifi /lib/firmware | grep -i -E 'iwlwifi-(sc|bz)'   # BE211 firmware
powerprofilesctl                                 # power modes
fwupdmgr get-devices                             # BIOS and fingerprint firmware
```

Sources: Framework's Linux support table and Ubuntu 26.04 guide for the 13 Pro, Framework community reports (Arch GPU write-up, Ubuntu 26.04 boot stall), NixOS's `framework/13-inch/intel-core-ultra-series3`, `common/intel.nix` and `common/gpu/intel` modules, framework.wiki.
