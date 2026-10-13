# CLAUDE.md

Dotfiles for an Arch Linux fleet (Hyprland primary, i3 fallback): user config in
`config/`, tools in `bin/`, root-owned machine layer in `system/`, one
`profiles/<hostname>.env` per machine (class, GPU, roles, disk).

## Commands

```bash
make install                             # symlink config/ into XDG paths, bin/ into ~/.local/bin,
                                         # enable role/host user units, run pi-setup
make install-system                      # dry run: root-side drift for this machine
sudo scripts/install-system.sh --apply   # apply system/ (packages, /etc, kernel params, services, DKMS)
scripts/install-system.sh --profile <host> --list   # a machine's apps
make test                                # python + node unit tests (tests/unit/)
make test-install / test-system / test-bootstrap     # installer, system layer, bootstrap kit
make lint                                # shellcheck, luacheck, yamllint, stylua, ruff
```

Before committing, run the gates CI runs (`.github/workflows/dotfiles.yml`,
`nvim.yml`): bash -n + shellcheck, luacheck, stylua v2.5.2 `--check config/nvim/`,
yamllint, `ruff check --select F bin scripts tests/unit`, unit tests. Hooks from
`git-setup-hooks` enforce conventional commits (subject ≤ 50 chars) and secret
detection.

## Invariants

- **Symlinks, not copies.** Edit files here; `install.sh` links them. Machine
  differences go in overlays (`profiles/`, `config/zsh/{class,hosts}/`,
  `config/gui/Wayland/hypr/hosts/`, `system/{gpu,hosts,roles}/`).
- **`/etc` changes go through `system/`.** Change the repo copy, then
  `install-system.sh --apply`; `make install-system` shows drift.
- **User units** live in `config/systemd/user/` and are enabled per
  `system/{roles,hosts}/*/user-services`. A unit missing from those lists never runs.
- **Private config** lives in `$SYNC/state/dotfiles-local` (linked as `local/`,
  gitignored): company launchers, `env/.env` secrets, work aliases, private units.
  This repo is public.
- **Docs live in operator notes** (`$NOTES/Homelab/dotfiles/`). Reports, audits and
  agent briefs go to the runs folder from `ws route dotfiles`.
  `tests/unit/test_doc_links.py` fails on any tracked `.md` except README.md,
  CLAUDE.md and runtime-loaded pi skills/prompts and the Hermes persona.
- **Git history is machine-local** (Syncthing ignores `.git`): `git-bundle-backup`
  bundles unpushed work weekly; `git-rehydrate` rebuilds `.git` on a new machine.

## Hardware guardrails (arch: XPS 15, NVIDIA Optimus, s2idle only)

Each one prevents a confirmed crash or black screen on resume. Read
`$NOTES/Homelab/dotfiles/HARDWARE.md` before touching suspend, GPU, lid,
kernel cmdline or the AnnePro2 DKMS module.

- `nvidia-{suspend,resume,hibernate}.service` stay disabled: `EnableS0ixPowerManagement=1`
  makes the kernel save GPU state, and the services would do it twice.
- Lid open/close uses `hyprctl dispatch dpms`; `keyword monitor … disable` crashes Hyprland on resume.
- Keep `system-sleep/hyprland-sigstop` (SIGSTOP Hyprland across GPU suspend) and the
  cmdline `i915.enable_psr=0 pcie_aspm=off acpi_osi=!ACPI-Video`.
- Idle and lock: `hypridle` + `hyprlock-safe`; session via `bin/hyprland-session` (keeps Hyprland logs).

## Scripting conventions

- `bin/<name>`: no extension, executable, `#!/bin/bash`, `set -euo pipefail` for
  anything load-bearing. `install.sh` links it into PATH and prunes dead links.
- Load-bearing scripts get unit tests in `tests/unit/test_<name_with_underscores>.{py,mjs}`
  (Python loads extensionless `bin/` files via `SourceFileLoader`).
- `config/zsh/.zshenv` defines `$DOTFILES`, `$SYNC`, `$NOTES` and the XDG paths; start there.

## Reference (operator notes, `$NOTES/Homelab/dotfiles/`)

- `SYSTEM_LAYER.md`, `PROFILES.md`: adding a machine, role, package or `/etc` file
- `HARDWARE.md`: suspend/GPU/lid/kernel/DKMS rationale; skrubben zram; Syncthing tuning
- `TESTING.md`, `LINTING.md`: test conventions, reproducing CI locally
- `SECURITY.md`, `LOCAL_CONFIG.md`: secrets, hook rules, the private overlay
- `pi-resources.md`, `pi-delegate-contract.md`, `HERMES.md`: pi resources, delegation, Hermes
- `GIT_WORKFLOW.md`, `KEYBINDINGS.md`, `OVERVIEW.md`, `nvim/`: user-facing workflow and feature tour
