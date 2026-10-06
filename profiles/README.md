# Machine profiles

One file per machine, describing what that machine *is*. Read in three places:

- **install time** (`install-arch`, external) — which disk to partition, how much swap
- **link time** (`scripts/install.sh`) — which config overlays to link
- **system time** (`scripts/install-system.sh`) — which root-owned packages,
  `/etc` files, kernel parameters and services to apply (`system/README.md`)

One source of truth, so a new machine is described once rather than in a
scattering of hostname checks.

## Using one

```bash
# dotfiles (auto-detected from hostname, override with PROFILE=)
make install
```

`scripts/install.sh` picks `profiles/$(hostname).env`, falling back to
`profiles/default.env` with a warning, and writes the resolved facts to
`~/.config/dotfiles-profile.env` so runtime code (e.g. `.zshrc`) can read
`$PROFILE_CLASS` without re-deriving it.

## Fields

| Field | Used by | Meaning |
|---|---|---|
| `PROFILE_CLASS` | dotfiles | `desktop` or `laptop`. Selects class overlays. |
| `PROFILE_HAS_BATTERY` | dotfiles | `yes`/`no`. A desktop with a wireless mouse still reports a `power_supply`, so this is declared rather than detected. |
| `PROFILE_GPU` | dotfiles + system | What drives the displays: `intel` (iGPU only), `hybrid` (Intel iGPU + NVIDIA on demand, Optimus), `nvidia` (dGPU only). Selects `system/gpu/<gpu>/` and `hypr/gpu/<gpu>.conf`. |
| `PROFILE_DISK` | install-arch | Whole-disk device to partition. **No default — the installer refuses to guess.** |
| `PROFILE_SWAP_GIB` | install-arch | Swap size in **GiB**. `0` disables swap. |
| `PROFILE_HOSTNAME` | install-arch | Hostname to set. |

## The overlay system

Every participating app resolves ONE overlay file per machine, most specific
first:

```
config/<app>/hosts/<hostname>.<ext>   # host overlay (wins)
config/<app>/class/<class>.<ext>      # class overlay (fallback)
(empty placeholder)                   # neither exists
```

`link_overlay` in `scripts/install.sh` links the winner to a fixed target
**outside** the repo-symlinked config dirs (so Syncthing cannot collide the
link across machines), and each base config includes that target
unconditionally:

| App | Overlay root | Target | Included by |
|---|---|---|---|
| waybar | `config/gui/Wayland/waybar/` | `~/.config/waybar-host.jsonc` | `include` in `waybar/config` (modules-right lives ONLY here) |
| hyprland | `config/gui/Wayland/hypr/` | `~/.config/hypr-host.conf` | `source` in `hyprland.conf` (monitors, lid switch) |
| hypridle | `config/gui/Wayland/hypr/hypridle/` | `~/.config/hypridle-host.conf` | `source` in `hypridle.conf` (laptop adds backlight dim) |
| alacritty | `config/gui/alacritty/` | `~/.config/alacritty-host.toml` | `general.import` (owns `font.size`; base must not set it) |
| tmux | `config/tmux/` | `~/.config/tmux-host.conf` | `source-file -q` at the end of `tmux.conf` |
| environment.d | `config/environment.d/` | `~/.config/environment.d/50-host.conf` | systemd user env (loads every file in the dir) |
| zsh | `config/zsh/{class,hosts}/` | — (runtime) | `.zshrc` sources class then host via `dotfiles-profile.env` |

Hyprland has a second, GPU-keyed overlay: `config/gui/Wayland/hypr/gpu/<PROFILE_GPU>.conf`
is linked to `~/.config/hypr-gpu.conf` (VA-API driver, hardware cursors). It is
keyed on the GPU rather than host/class because two laptops can share a class
but not a GPU setup.

The target must be a path whose parent is **not** a symlink into the repo.
Waybar's used to be `~/.config/waybar/profile.jsonc`; since `~/.config/waybar`
links into the repo, the link landed in the working tree, was committed, and
Syncthing flipped it between machines. `tests/install-assertions.sh` now
guards against that.

zsh needs no install-time link: the repo dir is already available at runtime
and sourcing is cheap, so `.zshrc` dispatches directly (class first, host
last so the host can override).

## Machines

| Profile | Machine | Class | GPU | User |
|---|---|---|---|---|
| `arch` | Dell XPS 15 | laptop | hybrid | gustaf |
| `skrubben` | desktop, i9-9900K + RTX 2080 Ti | desktop | nvidia | gud1 |
| `xps14` | Dell XPS 14 (2026, DA14260), not delivered yet | laptop | intel | (pick at install) |
| `arch-e2e` | throwaway Proxmox VM for installer tests | laptop | intel | — |

The username is chosen at install time, not here, and differs between
machines. Never hard-code `/home/<user>` in tracked files: use `$HOME`,
`$DOTFILES`, `~`, or `@DOTFILES@` in `system/` files.

## Adding a machine

1. Copy `default.env` to `profiles/<hostname>.env` and fill it in.
2. If it needs a monitor layout, add
   `config/gui/Wayland/hypr/hosts/<hostname>.conf`.
3. Add any other `hosts/<hostname>.<ext>` overlays it needs — class overlays
   cover the common laptop/desktop differences already.
4. Put root-side needs (packages, `/etc` files, kernel parameters, services)
   in `system/hosts/<hostname>/` — see `system/README.md`.
5. `make test-system`, commit, push. A fresh install is then
   `PROFILE=<hostname> ./install.sh` from install-arch; an existing machine runs
   `make install` and `sudo scripts/install-system.sh --apply`.

For the full new-laptop runbook see
`docs/research/machine-profiles-and-xps14.md`.

Secrets never live here — this file is committed to a public repo.
