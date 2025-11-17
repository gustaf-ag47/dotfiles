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
ts                 # Save current tmux session
tr                 # Restore last tmux session
tc                 # Clean old session files
tl                 # List tmux sessions
ta                 # Attach to session
tn                 # Create new session

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
   - **Auto-restore** on terminal startup via enhanced `ftmuxp` function
   - Manual save/restore: `Ctrl-Space + Ctrl-S/Ctrl-R`
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

### Primary: Arch Linux
- Full hardware support including NVIDIA graphics
- Hyprland with Wayland as primary desktop
- i3 with X11 as fallback option

### Testing: Docker
- Dockerfile provides clean testing environment
- Includes essential packages for dotfiles functionality

## Important Notes

### Configuration Management
- **Symlinks, not copies**: `scripts/install.sh` creates symlinks from `$DOTFILES` to XDG locations
- **XDG compliance**: Configurations follow XDG Base Directory Specification (defined in `config/zsh/.zshenv`)
- **Auto-detection**: System detects Wayland/X11 and loads appropriate configs
- **Modular independence**: Components (shell, editor, WM) function independently

### Auto-start Behavior
- **tty1**: Automatically launches Hyprland (see `config/zsh/.zshrc`)
- **Other terminals**: Automatically starts tmux with session restoration
- **Session persistence**: Tmux saves every 5min, auto-restores on terminal startup

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