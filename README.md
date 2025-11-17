# Dotfiles

A comprehensive development environment configuration for Arch Linux with Hyprland/Wayland and i3/X11 support.

## Quick Start

```bash
# Install dotfiles
make install

# Test in Docker
make test
```

## Documentation

All documentation is located in the `docs/` directory:

- **[Setup Guide](docs/README.md)** - Installation and features overview
- **[Keybindings](docs/KEYBINDINGS.md)** - Complete keyboard shortcuts reference
- **[Git Workflow](docs/GIT_WORKFLOW.md)** - Trunk-based development standards

## Features

- Modern development environment with Tokyo Night theme
- Keyboard-driven workflow (Hyprland + Neovim + Tmux + Zsh)
- Automated Git workflow with conventional commits
- 40+ custom utility scripts
- Cross-platform compatibility (Wayland/X11)

## Architecture

The configuration provides integrated components:
- **Shell**: Zsh with vi-mode and FZF integration
- **Editor**: Neovim with LSP and 25+ plugins
- **WM**: Hyprland (primary) and i3 (fallback)
- **Terminal**: Tmux with session persistence
- **Git**: Trunk-based workflow with automated enforcement

For detailed information, see the documentation in `docs/`.