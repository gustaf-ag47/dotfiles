# Machine profiles

One file per machine, describing what that machine *is*. Read in two places:

- **install time** (`install-arch`, external) — which disk to partition, how much swap
- **link time** (`scripts/install.sh`) — which config overlays to link

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
| `PROFILE_GPU` | both | `nvidia`, `intel`, `amd`. |
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
| waybar | `config/gui/Wayland/waybar/` | `~/.config/waybar/profile.jsonc` | `include` in `waybar/config` (modules-right lives ONLY here) |
| hyprland | `config/gui/Wayland/hypr/` | `~/.config/hypr-host.conf` | `source` in `hyprland.conf` (monitors, lid switch) |
| hypridle | `config/gui/Wayland/hypr/hypridle/` | `~/.config/hypridle-host.conf` | `source` in `hypridle.conf` (laptop adds backlight dim) |
| alacritty | `config/gui/alacritty/` | `~/.config/alacritty-host.toml` | `general.import` (owns `font.size`; base must not set it) |
| tmux | `config/tmux/` | `~/.config/tmux-host.conf` | `source-file -q` at the end of `tmux.conf` |
| environment.d | `config/environment.d/` | `~/.config/environment.d/50-host.conf` | systemd user env (loads every file in the dir) |
| zsh | `config/zsh/{class,hosts}/` | — (runtime) | `.zshrc` sources class then host via `dotfiles-profile.env` |

zsh needs no install-time link: the repo dir is already available at runtime
and sourcing is cheap, so `.zshrc` dispatches directly (class first, host
last so the host can override).

## Adding a machine

1. Copy `default.env` to `profiles/<hostname>.env` and fill it in.
2. If it needs a monitor layout, add
   `config/gui/Wayland/hypr/hosts/<hostname>.conf`.
3. Add any other `hosts/<hostname>.<ext>` overlays it needs — class overlays
   cover the common laptop/desktop differences already.
4. Run `make install`.

Secrets never live here — this file is committed to a public repo.
