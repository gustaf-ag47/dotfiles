# Machine profiles across arch, skrubben and a new Dell XPS 14

Research and design record for branch `feature/machine-profile-gaps`
(dotfiles and install-arch, 2026-10-06). It covers why the machines are
separated the way they are, what was broken, and what the incoming laptop
needs. The how-to lives in `profiles/README.md` and `system/README.md`.

## Premises

Facts this design was built on, each verified on 2026-10-06 unless marked.

1. **Two machines today, a third on order.**
   - `arch`: Dell XPS 15, Intel Iris Xe + RTX 3050 Ti (Optimus), user
     `gustaf`, kernel `linux` 7.2.
   - `skrubben`: desktop, i9-9900K + RTX 2080 Ti, user `gud1`, kernel
     `linux-lts` 6.18. NVIDIA drives the display (`lspci` shows no iGPU in use).
   - `xps14`: Dell XPS 14 (2026, DA14260), being delivered. The hostname is
     a working name; rename = `git mv` of four paths.
2. **Both clones share one working tree through Syncthing.** `~/sync` is a
   Syncthing folder and `.stignore` excludes `**/.git`, so files sync but git
   state does not. Two consequences:
   - Anything an installer writes *inside* the repo shows up on the other
     machine. That is what happened to `waybar/profile.jsonc`: skrubben showed
     it as modified, pointing at `/home/gud1/.../desktop.jsonc` instead of the
     committed `/home/gustaf/.../laptop.jsonc`.
   - A branch checked out on one machine appears as uncommitted edits on the
     other until it is merged and pulled there.
   The same mechanism had left the local install-arch clone 13 commits behind
   while its files already matched `origin/master`, and stripped the +x bits
   (Syncthing does not sync permissions by default).
3. **Usernames differ** (`gustaf` vs `gud1`), so absolute home paths in tracked
   files are wrong on the other machine.
4. **A profile system already existed** (`profiles/<host>.env` → class/host
   overlays) and is the right foundation. The gaps were in how far it reached,
   not in its design.
5. **Root-side setup was documentation, not code.** `CLAUDE.md` described the
   XPS 15's `/etc` files, but the live machine had more than was written down
   (AX211 Wi-Fi workarounds, a Bluetooth udev rule, NVIDIA early KMS). The
   doc's zram section was actually skrubben's.

## Gaps found, and the fix for each

| # | Gap | Fix |
|---|---|---|
| 1 | Waybar overlay link written to `~/.config/waybar/profile.jsonc`, a dir symlinked into the repo, so it was committed and flipped across machines by Syncthing | Target moved to `~/.config/waybar-host.jsonc`; old path untracked, gitignored, removed by `install.sh`; `install-assertions.sh` guards it |
| 2 | `PROFILE_GPU` recorded but unused; `nvidia-open` installed on every machine by install-arch; NVIDIA/Intel Hyprland settings hard-coded in the shared config | `PROFILE_GPU` = `intel` / `hybrid` / `nvidia` now selects `system/gpu/<gpu>/` (drivers, early KMS, `nvidia_drm.modeset=1`) and `hypr/gpu/<gpu>.conf` (VA-API, cursors); `nvidia-open` dropped from install-arch's `apps.csv` |
| 3 | `/etc` setup documented in CLAUDE.md only; incomplete and per-machine by hand | New `system/` layer (`common/`, `gpu/`, `hosts/`), applied by `scripts/install-system.sh` (dry run by default, `--apply`, `--check`). install-arch runs it after `make install`. Captured from both live machines |
| 4a | `BAT0` hard-coded in `battery-monitor`, `toggle-power-mode`, `laptop.zsh` | Detect the first `type=Battery` supply that isn't `scope=Device` (excludes mice); AC by `type=Mains` |
| 4b | `hosts/skrubben.conf` had placeholder monitors (DP-1/DP-2/HDMI-A-1) | Real output from `hyprctl monitors`: ASUS ROG XG27UQ on DP-2. Kept at `preferred` (60 Hz, current behaviour); 144 Hz is a commented opt-in |
| 4c | Absolute `/home/gustaf` path in a system unit | `@DOTFILES@` token in `system/` files, substituted at install |

Behaviour preserved on purpose:

- skrubben's Hyprland GPU settings are unchanged in effect. `LIBVA_DRIVER_NAME=iHD`
  pointed at a driver it doesn't have, which is the same as unset. NVIDIA
  hardware decode (`libva-nvidia-driver`) is a separate decision.
- The XPS 15's live files were copied byte for byte, with two exceptions:
  `wifi-powersave-off.service` had `type=oneshot` (lowercase, ignored by
  systemd) and now says `Type=oneshot`; `iwlwifi-watchdog.service`'s
  `/home/gustaf/...` path became `@DOTFILES@`.
- Kernel parameters moved to `/etc/default/grub.d/*.cfg` drop-ins that only
  append. On the XPS 15 they duplicate what is already in
  `/etc/default/grub` until that base line is tidied. Duplicates are harmless.

Excluded on purpose: the XPS 15's `ax211-reset-monitor.service` (an
experiment logging into `~/ax211-trial/`), and skrubben's homelab, backup,
VPN and runner units (they belong to those services' own repos).

## Dell XPS 14 (2026, DA14260): research

### Specifications

| | |
|---|---|
| CPU | Intel Core Ultra (Series 3, Panther Lake): Ultra 5 325, Ultra 7 355, Ultra X7 358H, Ultra X9 388H |
| GPU | Integrated only: Intel Graphics (4 Xe3 cores) on 325/355; Arc B390 (12 Xe3 cores) on X7/X9. **No discrete/NVIDIA option** |
| Memory | 16 / 32 / 64 GB LPDDR5X (7467 or 9600 MT/s), soldered |
| Storage | 512 GB – 4 TB PCIe 4.0 SSD, single slot, user-replaceable |
| Display | 14" 16:10: 1920×1200 IPS non-touch, 1–120 Hz VRR, ~535 nits; or 2880×1800 OLED touch, 20–120 Hz VRR, ~406 nits, 100% P3 |
| Ports | 3× Thunderbolt 4 (USB-C, DP 2.1, PD charging), 3.5 mm jack. No USB-A, HDMI or card reader |
| Wireless | Intel Wi-Fi 7 BE211 2×2, Bluetooth 6.0 |
| Camera | 8 MP (1440p video) + IR (Windows Hello). No fingerprint reader |
| Audio | Quad speakers (2× 3 W + 2× 2 W) |
| Battery | 70 Wh, 3-cell; 100 W USB-C adapter |
| Size | 309.5 × 209.7 × 14.6 (OLED) / 15.2 (IPS) mm; 1.36–1.38 kg |
| Input | Haptic touchpad (now with edge markers), physical F-row restored |

Reviewers measured the battery at about 21 h (IPS) and about 15 h (OLED) on
CNET's test. Dell has sold an Ubuntu 24.04 SKU in North America since
2026-06-02, at $100 less than the Windows one.

### Linux status

| Component | Status | Needs |
|---|---|---|
| Graphics (Xe3) | Works, in-kernel `xe` | `mesa vulkan-intel intel-media-driver` (`system/gpu/intel`) |
| Wi-Fi / BT (BE211) | Works, `iwlwifi` | `linux-firmware`; `wireless-regdb` (else regdom stays "00") |
| Audio | Works (SOF + SoundWire, 4× Cirrus CS35L57 amps, SDCA jack codec), **but see the race below** | `sof-firmware alsa-ucm-conf` |
| Touchpad | Works on current kernels (Ubuntu 26.04 live OK; Fedora 43 did not) | — |
| Webcam (IPU7 + OV08X40) | Kernel driver from 7.2; needs userspace | `libcamera pipewire-libcamera`; Chromium needs `#enable-webrtc-pipewire-camera` |
| IR camera (Himax HM1092) | **No Linux driver** | — |
| Fingerprint | None on this model (the Synaptics USB device is the camera's vision chip) | — |
| Suspend | s2idle only; S0ix residency reported, ~1%/day | `mem_sleep_default=s2idle` |
| Firmware | BIOS via fwupd/LVFS | `fwupd` |

**Speaker amps vs. camera chip race.** The amps' `spk-id` GPIO and the camera
vision chip driver's (`intel_cvs`) wake IRQ are the same ACPI pin. Whichever
probes first wins. When `intel_cvs` wins, the amps fail with `-EBUSY` and
there is **no sound card at all**, reportedly on about half of boots. An upstream
patch ("media: i2c: cvs: Get the wake IRQ without claiming the GPIO", Cc
stable) was not merged as of kernel 7.2.8. Workaround implemented in
`system/hosts/xps14`: blacklist `intel_cvs` from autoload, and
`intel-cvs-late.service` loads it after every Cirrus (`sdw:m01FA`) SoundWire
device has a driver.

*Confidence:* the race and its fix come from **one** source (a single owner's
three-month report). The script was written from that description, not
copied. Treat it as the first thing to verify on the real machine.

### Firmware/BIOS setup before installing

- Storage → **AHCI/NVMe**, not "RAID On" (Intel VMD hides the SSD from the
  installer). install-arch now adds `vmd` to the initramfs if VMD is still
  active, as a safety net.
- Secure Boot **off** for install-arch (it uses unsigned GRUB).
- Only USB-C ports: use a USB-C stick or a hub for the ISO.
- Boot menu: F12; BIOS setup: F2.

## New-laptop runbook (xps14)

Before delivery (done on this branch): profile, Hyprland host and GPU
overlays, system layer, install-arch hook. After merging both PRs, nothing
else is required up front.

On delivery day:

1. **BIOS** (F2): storage AHCI/NVMe, Secure Boot off. Update BIOS later via
   fwupd.
2. **Boot** the Arch ISO from a USB-C stick (F12). Connect Wi-Fi with
   `iwctl`. Check `lsblk`: the SSD should be `/dev/nvme0n1`.
3. **Install**:
   ```bash
   curl -fsSLO https://raw.githubusercontent.com/gustaf-ag47/install-arch/master/install.sh
   PROFILE=xps14 ROOT_PASSWORD=… ENCRYPTION_PASSWORD=… bash install.sh
   ```
4. **First boot**, as root: `bash /root/post_install_root.sh` (asks for the
   username). This installs `apps.csv`, clones dotfiles, runs `make install`,
   applies the system layer (`install-system.sh --apply`), then restores the
   bootstrap kit with the YubiKey and joins Syncthing as a **new** device.
5. **Admit it to the mesh**: add its Syncthing device ID to
   `secrets/known-devices.txt`, accept it on arch/skrubben, and
   `sudo tailscale up`.
6. **Verify the premises** (record what you find in `system/README.md`):
   - Panel: `hyprctl monitors`, then pin the scale in `hosts/xps14.conf`
     (1.6 OLED / 1.25 IPS).
   - Audio across ~5 reboots: `aplay -l` lists a `sof-soundwire` card and
     `journalctl -b -k | grep spk-id` is empty.
   - `ls /sys/bus/soundwire/devices/*/modalias` shows `sdw:m01FA…`.
   - Camera: `cam -l` (libcamera) lists the OV08X40.
   - `cat /sys/power/mem_sleep` → `[s2idle]`; suspend/resume via lid.
   - `fwupdmgr get-updates`.
7. **Tidy**: `make install-system` should print `In sync.`

## Sources

- Dell product page (ports, Wi-Fi card, battery, dimensions):
  https://www.dell.com/en-us/shop/laptop-computers/spd/xps14da14260
- CNET review (IPS vs OLED panels, memory speeds, IR camera, no fingerprint):
  https://www.cnet.com/tech/computing/dell-xps-14-review-ultraportable-laptop/
- TechRadar review (configurations, 2880×1800 OLED, LPDDR5X, PCIe 4.0):
  https://www.techradar.com/computing/windows-laptops/dell-xps-14-2026
- Expert Reviews (VRR ranges, BE211, speakers, SSD/battery serviceable):
  https://www.expertreviews.co.uk/technology/laptops/dell-xps-14-2026-review
- Notebookcheck spec sheet: https://www.notebookcheck.net/Dell-XPS-14-2026-DA14260.1241000.0.html
- Notebookcheck on the Ubuntu SKU (2026-06-02, up to 64 GB/4 TB, panels):
  https://www.notebookcheck.net/Cheaper-Dell-XPS-14-2026-released-internationally-with-Ubuntu-Linux-and-up-to-64-GB-RAM.1313448.0.html
- Liliputing on the Ubuntu SKU: https://liliputing.com/dell-xps-14-laptop-is-now-available-with-ubuntu-linux/
- Techtest (German), live-USB tests on the sibling XPS 16 DA16260
  (Ubuntu 26.04 mostly works, webcam not; Fedora 43 broken):
  https://techtest.org/dell-xps-14-16-2026-linux/
- Arch on the DA14260, installer kit plus three-month report (IPU7/libcamera,
  CS35L57/intel_cvs race, s2idle, regdb, VMD, no fingerprint):
  https://github.com/jim-wyatt/arch-da14260
- Live machines: `lspci`, `hyprctl monitors`, `/proc/cmdline`,
  `/etc/{modprobe.d,udev/rules.d,systemd}`, `pacman -Q` on arch and skrubben,
  2026-10-06.

Not verified: the Arch wiki has no DA14260 page yet, and Phoronix was not
reachable from this host.
