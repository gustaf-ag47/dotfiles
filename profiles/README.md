# Machine profiles

One file per machine, describing what that machine *is*. Read in two places:

- **install time** (`install-arch`) — which disk to partition, how much swap
- **link time** (`dotfiles/scripts/install.sh`) — which config overlays to symlink

One source of truth, so a new machine is described once rather than in a
scattering of hostname checks.

## Using one

```bash
# install-arch, on the target machine
PROFILE=thinkpad ./install.sh

# dotfiles (auto-detected from hostname, override with PROFILE=)
make install
```

`scripts/install.sh` picks `profiles/$(hostname).env`, falling back to
`profiles/default.env` with a warning.

## Fields

| Field | Used by | Meaning |
|---|---|---|
| `PROFILE_CLASS` | dotfiles | `desktop` or `laptop`. Selects config overlays. |
| `PROFILE_HAS_BATTERY` | dotfiles | `yes`/`no`. A desktop with a wireless mouse still reports a `power_supply`, so this is declared rather than detected. |
| `PROFILE_GPU` | both | `nvidia`, `intel`, `amd`. |
| `PROFILE_DISK` | install-arch | Whole-disk device to partition, e.g. `/dev/nvme0n1`. **No default — the installer refuses to guess.** |
| `PROFILE_SWAP_GIB` | install-arch | Swap size in **GiB**. `0` disables swap. |
| `PROFILE_HOSTNAME` | install-arch | Hostname to set. |

## What each class changes

- **waybar** — `config/gui/Wayland/waybar/profiles/<class>.jsonc` is linked to
  `~/.config/waybar/profile.jsonc` and included by the main config. The desktop
  overlay drops the `battery` module; the laptop overlay keeps it and adds
  `backlight`.
- **hyprland** — `config/gui/Wayland/hypr/hosts/<hostname>.conf` is linked to
  `~/.config/hypr-host.conf` (monitors, lid switch). Host-specific rather than
  class-specific, because monitor layouts do not generalise.

## Adding a machine

1. Copy `default.env` to `profiles/<hostname>.env` and fill it in.
2. If it needs a monitor layout, add
   `config/gui/Wayland/hypr/hosts/<hostname>.conf`.
3. Run `make install`.

Secrets never live here — this file is committed to a public repo.
