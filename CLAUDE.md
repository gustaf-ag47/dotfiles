# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a comprehensive dotfiles repository that provides a complete development environment for Arch Linux with dual desktop support (Hyprland/Wayland and i3/X11). The configuration creates a cohesive, keyboard-driven development workflow optimized for productivity.

## Development Commands

### Installation & Setup
```bash
# Install dotfiles system-wide
make install

# What install does:
# 1. Sources config/zsh/.zshenv to get $DOTFILES, $XDG_CONFIG_HOME, etc.
# 2. Moves/copies dotfiles to $DOTFILES location if not already there
# 3. Creates symlinks from $XDG_CONFIG_HOME to $DOTFILES/config/*
# 4. Clones zsh plugins (syntax-highlighting, autosuggestions)
# 5. Clones tmux plugin manager (tpm)
# 6. Symlinks both Wayland (Hyprland) and Xorg (i3) configs
# 7. Copies .desktop files to $XDG_DATA_HOME/applications

# Run E2E tests with Hurl (requires running docker compose)
make test
```

### Git Workflow (Trunk-Based Development)
```bash
# Setup Git hooks for current repository
git-setup-hooks

# Daily workflow
git sync                    # Sync with master
git nb feature add-feature  # Create new standardized branch
git feat "add new feature"  # Quick conventional commit
git pushf                   # Safe force push
git clean                   # Interactive branch cleanup

# Commit validation automatically enforced via hooks
```

### Core Scripts
- `scripts/install.sh` - Main installation script that symlinks configurations to proper XDG locations
- `scripts/test.sh` - E2E test runner using Hurl (requires docker compose services running)
- `bin/` - Custom utility scripts (40+ tools):
  - `git-*` - Git workflow tools (setup-hooks, new-branch, clean-branches, version)
  - `backup`/`restore` - System backup/restore utilities
  - `filemanager`, `browser-launcher` - Application launchers
  - `fzf-docker`, `fzk`, `fzsd` - FZF integration tools
  - `capture`, `clipboardman` - Screenshot and clipboard management

### Validation & Quality
```bash
# Git hooks automatically enforce:
# - Conventional commit format validation (via config/git/hooks/commit-msg)
# - Merge conflict marker detection
# - Large file warnings (>1MB)
# - Shell script syntax validation (bash -n)
# - **Secret detection** (AWS keys, GitHub tokens, private keys, etc.)

# E2E testing with Hurl (requires docker compose up -d)
make test                    # Run all .hurl/.http files in tests/e2e/
hurl --test tests/e2e/*.hurl # Run specific test files

# Manual validation
bash -n script.sh           # Test shell script syntax
git-setup-hooks             # Install hooks from config/git/hooks/ to .git/hooks/
```

### Security (Preventing Secret Leaks)
```bash
# Three-layer protection automatically enabled:

# 1. Global gitignore (config/git/ignore)
#    - Blocks .env files, private keys, credentials
#    - Applied during `make install`

# 2. Pre-commit hook (config/git/hooks/pre-commit)
#    - Detects AWS keys, GitHub tokens, Stripe keys, etc.
#    - Scans for high-entropy strings (base64 secrets)
#    - Blocks sensitive filenames

# 3. Best practices documentation (@docs/SECURITY.md)

# Test secret detection
echo 'API_KEY="AKIAIOSFODNN7EXAMPLE"' > test.sh
git add test.sh && git commit -m "test"  # Should be blocked!
rm test.sh

# See @docs/SECURITY.md for complete guide
```

### Documentation
- @docs/GIT_WORKFLOW.md - Complete Git workflow documentation
- @docs/KEYBINDINGS.md - Complete keybinding reference
- @docs/README.md - Repository overview and setup guide
- @docs/SECURITY.md - **Security guide for preventing secret leaks**
- @config/nvim/MODULAR_APPROACH.md - Neovim modularization plan and architecture notes

### Common Development Tasks
```bash
# Start development environment
# Hyprland auto-launches on tty1
# Tmux auto-starts in terminals with session persistence

# Tmux session management
tn                 # Open session picker (ftmuxp) — create or attach
tl                 # List tmux sessions
ta                 # Attach to session
ts                 # Save current tmux session (tmux-safe-save)
trs                # Restore last tmux session (tmux-resurrect)
tc                 # Clean old resurrect files (>7 days)
ftsess             # Interactive session killer with fzf preview

# Access file manager
Super + R  # or run: filemanager

# Calculator tools
Super + C          # Popup calculator
Super + Shift + C  # Terminal calculator

# System utilities
backup            # Backup system
restore           # Restore from backup
power             # Power management menu
```

## Architecture Overview

### Core Components
1. **Shell Environment (Zsh)**
   - Location: `config/zsh/`
   - Vi-mode enabled, FZF integration
   - Auto-launches Hyprland on tty1, tmux on other terminals
   - Modern CLI tools with conditional aliases (bat, eza, fd, ripgrep, etc.)

2. **Editor (Neovim)**
   - Location: `config/nvim/`
   - Lazy.nvim plugin manager with 25+ plugins
   - LSP support, Treesitter, Telescope, DAP debugging
   - Tokyo Night theme, Space as leader key
   - Integration: Obsidian notes, AI assistance (avante), tmux navigation
   - **Modular architecture** (planned): `lua/lang/` for language configs, `lua/features/` for features, `lua/core/` for base config

3. **Window Management**
   - **Hyprland** (Primary): `config/gui/Wayland/hypr/`
     - 4K multi-monitor support with HiDPI scaling
     - NVIDIA optimization, modern blur effects
     - Waybar status bar with custom styling
   - **i3** (Fallback): `config/gui/Xorg/i3/`
     - Polybar integration, Rofi launcher

4. **Terminal Multiplexer (Tmux)**
   - Location: `config/tmux/`
   - Prefix: Ctrl-Space
   - **Automatic session persistence** with resurrect/continuum (saves every 5min)
   - **Interactive session picker** on terminal startup via `ftmuxp` (attach, load layout, or create new)
   - **Auto-restore** when tmux server starts via continuum (not on every terminal open)
   - Manual save/restore: `Ctrl-Space + Ctrl-S` (save via wrapper) / `Ctrl-Space + Ctrl-R` (restore)
   - Vim-tmux-navigator for seamless pane navigation
   - Tokyo Night theme matching other components

### Directory Structure
```
config/
├── zsh/          # Shell configuration
├── nvim/         # Editor configuration
├── git/          # Git settings
├── tmux/         # Terminal multiplexer
├── gui/          # Desktop environments
│   ├── Wayland/  # Hyprland, Waybar, Wofi
│   └── Xorg/     # i3, Polybar, Rofi
├── lf/           # File manager
└── applications/ # Custom .desktop files

bin/              # 40+ utility scripts
scripts/          # Installation and testing
```

### Key Integration Points
- **Visual Consistency**: Tokyo Night theme across all components
- **Navigation**: Vim-style keybindings throughout (hjkl movement)
- **Session Management**: Tmux persistence, automatic session restoration
- **Clipboard**: Unified clipboard across Wayland/X11 with history (cliphist)
- **Development Workflow**: Integrated LSP, debugging, Git tools

## Configuration Highlights

### Environment Variables
- Follows XDG Base Directory Specification
- Wayland-optimized application settings
- Custom paths for Go, Rust, Python environments
- Location: `config/zsh/.zshenv`

### Modern CLI Tools
The system uses enhanced versions of standard tools:
- `ls` → `eza` (with icons and colors)
- `grep` → `ripgrep`
- `find` → `fd`
- `cat` → `bat` (syntax highlighting)
- `du` → `dust`, `df` → `duf`
- `ps` → `procs`

### Keyboard-Driven Workflow
- **Hyprland**: Super key + vim-style navigation
- **Tmux**: Ctrl-Space prefix + vim bindings
- **Neovim**: Space leader key + comprehensive shortcuts
- **Shell**: Vi-mode with FZF fuzzy finding

## Platform Support

### Primary: Arch Linux (`arch` host — Dell XPS 15)

**Hardware:** Intel Iris Xe + NVIDIA RTX 3050 Ti Mobile (Optimus hybrid)

The `make install` script only manages user-space configs. The following
system-level files must be created manually on a fresh install:

#### `/etc/modprobe.d/nvidia-suspend.conf`
Required for the display to survive suspend/resume (lid close). The laptop has
no S3 sleep; only s2idle (Modern Standby / S0ix) is available.

**Critical**: `EnableS0ixPowerManagement=1` implicitly activates
`UseKernelSuspendNotifiers`, which means the kernel handles GPU state save/restore
via PM callbacks — **not** via the nvidia-suspend/resume systemd services. The
services must therefore be **disabled**; having both active double-handles GPU
state and corrupts the driver on resume.

`DynamicPowerManagement=0x01` is required: the default value (3) on laptops
causes GSP Xid 120 task panics on resume with nvidia-open 595 on Optimus systems.

```
options nvidia NVreg_PreserveVideoMemoryAllocations=1
options nvidia NVreg_EnableS0ixPowerManagement=1
options nvidia NVreg_DynamicPowerManagement=0x01
```
After creating the file: `sudo mkinitcpio -P`

#### Systemd services — keep DISABLED
```bash
# DO NOT enable these — kernel notifiers (activated by EnableS0ixPowerManagement)
# handle GPU state. Enabling the services alongside notifiers causes double
# save/restore which corrupts the driver and produces a black screen on resume.
sudo systemctl disable nvidia-suspend.service nvidia-resume.service nvidia-hibernate.service
```

#### `/etc/systemd/logind.conf.d/idle.conf`
Prevents logind from double-suspending alongside idle-manager:
```ini
[Login]
IdleAction=ignore
```

#### Kernel cmdline (`/etc/default/grub` → `GRUB_CMDLINE_LINUX_DEFAULT`)
```
nvidia_drm.modeset=1 i915.enable_psr=0 pcie_aspm=off acpi_osi=!ACPI-Video
```
- `i915.enable_psr=0`: disables Intel Panel Self Refresh. Without it, i915 on
  Alder Lake can fail to re-initialize the eDP link at the correct clock
  frequency on s2idle resume (black screen despite NVIDIA resuming correctly).
- `pcie_aspm=off`: prevents ASPM link state transitions that can race with
  NVIDIA S0ix resume, causing hangs.
- `acpi_osi=!ACPI-Video`: stops the ACPI subsystem from delivering D-Notifier
  events to the NVIDIA driver during resume. Without it, the driver logs
  `RmHandleDNotifierEvent: Failed … status=0x11` on every wake — the RM objects
  haven't been reconstructed yet when the events arrive, leaving the driver in
  an inconsistent state that can cause downstream crashes.

After editing grub: `sudo grub-mkconfig -o /boot/grub/grub.cfg`

#### Lid switch handling (Hyprland host config)
Use **`dispatch dpms`** for lid open/close — never `keyword monitor "eDP-1, disable"`.

`keyword monitor` tears down Aquamarine's `SDRMConnector` for eDP-1. On resume
the reconnect path hits a use-after-free in `CLogger` inside
`SDRMConnector::disconnect()`, crashing Hyprland (confirmed in coredump, March
2026). `dispatch dpms off eDP-1` / `dispatch dpms on` only toggles display
power; the DRM pipeline stays intact, so there is nothing to reconstruct.

```ini
# config/gui/Wayland/hypr/hosts/arch.conf
bindl=,switch:on:Lid Switch,exec,hyprctl dispatch dpms off eDP-1
bindl=,switch:off:Lid Switch,exec,sleep 2 && hyprctl dispatch dpms on
```

#### `/etc/systemd/system-sleep/hyprland-sigstop`
Prevents Hyprland from issuing DRM/NVIDIA ioctls during the GPU suspend/resume
transition. Without this, Hyprland blocks on an NVIDIA driver call that only
resolves after a ~20 s timeout, after which Hyprland calls `exit()` — producing
a black screen with no coredump (confirmed June 2026).

```bash
#!/bin/bash
HYPRLAND_PID=$(pgrep -x Hyprland 2>/dev/null)
[[ -z "$HYPRLAND_PID" ]] && exit 0
case "$1" in
    pre)  kill -STOP "$HYPRLAND_PID" ;;
    post) kill -CONT "$HYPRLAND_PID" ;;
esac
```
Make executable: `sudo chmod +x /etc/systemd/system-sleep/hyprland-sigstop`

**Do not** use `nvidia-suspend/resume.service` for this — those services must
stay disabled (see modprobe.conf note above).

#### `/usr/src/hid-annepro2-1.0/` — AnnePro2 BLE keyboard DKMS module
The AnnePro2 sends a malformed 44-byte HID descriptor over BLE. A DKMS module
is required to replace it with a valid 6KRO descriptor. Without it, the kernel
truncates the descriptor to 4 bytes, creating no input device.

The module source lives at `/usr/src/hid-annepro2-1.0/hid-annepro2.c` and is
**not owned by any pacman package** — it must be created manually. The key fix:
`report_fixup` must return a hardcoded valid descriptor, not try to trim the
malformed one (the trim approach always produces a 4-byte no-op descriptor).

```bash
sudo dkms add /usr/src/hid-annepro2-1.0
sudo dkms build hid-annepro2/1.0
sudo dkms install hid-annepro2/1.0
```
`AUTOINSTALL=yes` in `dkms.conf` rebuilds automatically on kernel updates.

#### Lock manager notes
- Idle daemon: `hypridle` — started via `exec-once` in hyprland.conf
- Screen locker: `hyprlock` with `hyprlock-safe` wrapper (restarts on crash)
- Session launcher: `bin/hyprland-session` wrapper (saves Hyprland log to
  `~/.local/share/hyprland/logs/` on every exit for post-mortem debugging)
- `bin/idle-manager` (swayidle wrapper) is kept as fallback but is no longer active.

### Testing: Docker
- Dockerfile provides clean testing environment
- Includes essential packages for dotfiles functionality

## Important Notes

### Configuration Management
- **Symlinks, not copies**: `scripts/install.sh` creates symlinks from `$DOTFILES` to XDG locations
- **XDG compliance**: Configurations follow XDG Base Directory Specification (defined in `config/zsh/.zshenv`)
- **Auto-detection**: System detects Wayland/X11 and loads appropriate configs
- **Modular independence**: Components (shell, editor, WM) function independently

### Local/Private Configurations
- **Location**: `$SYNC/dotfiles-local/` (symlinked as `$DOTFILES/local/`)
- **Purpose**: Store personal, company-specific, or sensitive configs (gitignored but backed up)
- **Structure**: `local/{applications,bin,config,env}/` - automatically loaded during installation
- **Backup**: Automatically backed up via `$SYNC` and synced across machines
- **Use cases**:
  - Company-specific `.desktop` launchers
  - Personal API keys in `local/env/.env`
  - Work aliases in `local/config/zsh/*.zsh`
  - Private scripts in `local/bin/`
- **See**: `local/README.md` for complete documentation

### Auto-start Behavior
- **tty1**: Automatically launches Hyprland (see `config/zsh/.zshrc`)
- **Other terminals**: Automatically starts tmux with session restoration
- **Session persistence**: Tmux saves every 5min via continuum; restores when tmux server starts

### Shell Functions (config/zsh/scripts/functions.zsh)
- `docker-nuke <project>` - Complete cleanup of Docker resources for a project
- `extract <file>` - Universal archive extraction
- `mkcd <dir>` - Create directory and cd into it
- `up <n>` - Move up n directories

### FZF Integration (config/zsh/scripts/fzf.sh)
Key FZF-powered commands available throughout the system:
- `fkill` - Fuzzy process killer with preview
- `fdocker` - Docker container interaction (start, stop, logs, exec)
- `fglog` - Interactive git log browser with diffs
- `fgco` - Fuzzy git branch checkout
- `fgbr` - Quick switch to recent git branches
- `calc "expression"` - Quick calculations with history

## Scripting Conventions

### Shell Scripts (bin/ and scripts/)
- **Shebang**: Always use `#!/bin/bash` (not `/usr/bin/env bash`)
- **Error handling**: Use `set -euo pipefail` for critical scripts
- **Validation**: All shell scripts are validated via git hooks using `bash -n`
- **Testing**: Scripts that interact with services should have corresponding .hurl tests in `tests/e2e/`

### Adding New Utilities
1. Create script in `bin/<script-name>` (no .sh extension)
2. Make executable: `chmod +x bin/<script-name>`
3. Scripts in `bin/` are automatically available in PATH via symlink
4. Follow existing patterns: check `bin/git-*` for git utilities, `bin/fzf-*` for FZF tools

## File Locations

Key files to understand when making changes:
- `config/zsh/.zshenv` - **START HERE**: Defines all XDG paths and environment variables
- `config/zsh/.zshrc` - Shell startup, auto-launch logic, plugin loading
- `config/zsh/scripts/functions.zsh` - Custom shell functions
- `config/zsh/scripts/fzf.sh` - FZF integration commands
- `config/nvim/init.lua` - Editor initialization (loads `lua/core/`)
- `config/nvim/lua/core/init.lua` - Core Neovim setup orchestration
- `config/gui/Wayland/hypr/hyprland.conf` - Hyprland window manager config
- `config/tmux/tmux.conf` - Terminal multiplexer setup
- `scripts/install.sh` - Installation logic and symlinking
- `config/git/hooks/` - Git hook templates (installed via `git-setup-hooks`)
- @docs/KEYBINDINGS.md - Complete reference of all shortcuts
- @docs/GIT_WORKFLOW.md - Git workflow and branching strategy
- @docs/README.md - Setup and feature overview

This dotfiles system provides a complete, integrated development environment optimized for keyboard-driven productivity with modern tooling and visual consistency.