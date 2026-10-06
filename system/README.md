# System layer

Root-owned machine setup: packages, `/etc` files, kernel parameters, services
and DKMS sources. It is the counterpart of `scripts/install.sh` (which only
links user config) and replaces the "create these files by hand" lists that
used to live in `CLAUDE.md`.

Applied by `scripts/install-system.sh`, from the same `profiles/<name>.env`
that drives `install-arch` and `make install`.

```bash
make install-system                        # dry run: what differs on this machine
scripts/install-system.sh --check          # same, exit 1 on drift
sudo scripts/install-system.sh --apply     # make it so
PROFILE=xps14 scripts/install-system.sh    # another machine's plan
```

`install-arch` runs `--apply` automatically right after `make install`, so a
fresh machine gets all of this without manual steps.

## Layers

Applied in order; a later layer wins when two write the same path.

| Layer | Selected by | Holds |
|---|---|---|
| `common/` | always | logind idle hand-off to hypridle, AnnePro2 BLE keyboard DKMS source |
| `gpu/<PROFILE_GPU>/` | `PROFILE_GPU` | graphics drivers; early KMS + `nvidia_drm.modeset=1` for NVIDIA |
| `hosts/<profile>/` | profile name | everything specific to one machine |

`PROFILE_GPU` values:

| Value | Meaning | Machine |
|---|---|---|
| `intel` | Intel iGPU drives every display | xps14 |
| `hybrid` | Intel iGPU drives displays, NVIDIA dGPU on demand (Optimus) | arch |
| `nvidia` | NVIDIA dGPU drives every display | skrubben |

The same value selects the Hyprland GPU overlay,
`config/gui/Wayland/hypr/gpu/<gpu>.conf`.

Each layer directory may contain:

- `packages`: one pacman package per line, `#` comments allowed. Official
  repos only (CI resolves every name against today's Arch repos).
- `services`: `enable|disable|mask <unit>` per line. Enabled, not started;
  the next boot (or a manual `systemctl start`) picks them up.
- `files/`: a tree mirrored onto `/`. The repo decides the mode: executable
  becomes `0755`, everything else `0644`, owned by root. The token
  `@DOTFILES@` is replaced with the repo path, so units can reference `bin/`
  scripts without hard-coding a home directory (`gustaf` vs `gud1`).

## What happens after files change

| Changed path | Action |
|---|---|
| `etc/systemd/**` | `systemctl daemon-reload` |
| `etc/udev/rules.d/**` | `udevadm control --reload` |
| `usr/src/<name>-<ver>/dkms.conf` | `dkms add` + `dkms install` (install only when headers for the running kernel exist; otherwise dkms builds it when they arrive) |
| `etc/modprobe.d/**`, `etc/mkinitcpio.conf.d/**` | `mkinitcpio -P` |
| `etc/default/grub.d/**` | `grub-mkconfig -o /boot/grub/grub.cfg` |

Kernel parameters live in `etc/default/grub.d/*.cfg` drop-ins, which
`grub-mkconfig` sources after `/etc/default/grub`. They only ever **append**
to `GRUB_CMDLINE_LINUX_DEFAULT` (the test enforces it), so the LUKS
`cryptdevice=` line that `install-arch` writes is never touched. On a machine
whose `/etc/default/grub` already lists the same parameter, it appears twice
on the command line; that is harmless, and you can tidy the base file at leisure.

mkinitcpio drop-ins use `MODULES+=(...)` so several layers compose (for
example the NVIDIA modules, plus `vmd` that `install-arch` may add).

## Hosts

### arch: Dell XPS 15 (Intel Iris Xe + RTX 3050 Ti, Optimus)

Captured from the live machine on 2026-10-06. Rationale for each item is in
`CLAUDE.md` § Platform Support and in the file headers.

- NVIDIA S0ix suspend (`modprobe.d/nvidia-suspend.conf`), with the
  `nvidia-{suspend,resume,hibernate}` services **disabled**.
- `system-sleep/hyprland-sigstop`: freeze Hyprland across the GPU transition.
- Kernel parameters: `i915.enable_psr=0 pcie_aspm=off acpi_osi=!ACPI-Video`.
- Intel AX211 Wi-Fi crash-loop mitigations: `modprobe.d/iwlwifi.conf`,
  `udev 81-iwlwifi-d3cold.rules`, `system-sleep/iwlwifi-reload`,
  `iwlwifi-watchdog.service`, `wifi-powersave-off.service`.
- Bluetooth autosuspend off: `modprobe.d/bluetooth-optimize.conf`,
  `udev 50-bluetooth-power.rules`.
- `tlp`.

Deliberately **not** captured: `ax211-reset-monitor.service`. It is an
experiment that logs into `~/ax211-trial/`, not configuration.

### skrubben: desktop, i9-9900K + RTX 2080 Ti

Captured from the live machine on 2026-10-06.

- LTS kernel (`linux-lts`, headers for the nvidia and zfs DKMS modules).
- 24G lz4 zram swap (`zram-swap.service`).
- ASUS USB-BT500 Bluetooth dongle autosuspend off (`modprobe.d/btusb.conf`,
  `udev 50-bluetooth-power.rules`).

Deliberately **not** captured: the homelab, backup, VPN and GitHub-runner units
under `/etc/systemd/system`. They belong to the services they run, not to the
workstation.

### xps14: Dell XPS 14 (2026, DA14260), Panther Lake, Intel-only

Prepared **before delivery** from published research
(`docs/research/machine-profiles-and-xps14.md`). Verify every item on the
real machine and drop what turns out to be unnecessary.

- Audio: `sof-firmware`, `alsa-ucm-conf`.
- Webcam: `libcamera` + `pipewire-libcamera` (IPU7 has a kernel driver from
  7.2, but the image pipeline is libcamera's software ISP).
- Wi-Fi 7: `wireless-regdb`, `iw`.
- Firmware: `fwupd` + `fwupd-refresh.timer` (Dell ships BIOS updates on LVFS).
- `mem_sleep_default=s2idle`.
- **Speaker amps vs. camera chip race**: `intel_cvs` is blacklisted from
  autoload and `intel-cvs-late.service` loads it after the CS35L57 amps have
  bound. Without this, roughly half of all boots have no sound card at all.
  How to retire it is in the header of `modprobe.d/intel-cvs-late.conf`.

  First-boot check: `ls /sys/bus/soundwire/devices/*/modalias` should show
  `sdw:m01FA…` entries (Cirrus Logic); the wait loop keys on that.

## Adding a machine

1. `profiles/<name>.env` (see `profiles/README.md`).
2. `system/hosts/<name>/` with only what is unique to it. Prefer moving a
   setting to a `gpu/` layer or `common/` the second time it is needed.
3. `make test-system`.

A failing command (for example a DKMS build) is reported and counted rather
than aborting the run, so the rest of the layer is still applied. The script
exits 1 at the end if anything failed.
