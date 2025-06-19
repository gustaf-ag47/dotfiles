# Changelog

All notable changes to this dotfiles project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive README.md with installation and usage instructions
- Modern CLI tool aliases: `bat`, `eza`, `fd`, `dust`, `duf`, `procs`, `ripgrep`
- Bluetooth backup cleanup script with automatic rotation
- Enhanced Starship prompt with battery status and command duration
- Workspace rules for automatic application organization
- Additional window rules for floating dialogs and system tools
- Calculator answer continuation functionality (`* 2` to operate on last result)
- Bluetooth backup management with rotation (keeps 3 most recent)

### Fixed
- Syntax error in zsh aliases (`bigf` alias missing command)
- Bluetooth backup directory accumulation (now auto-rotates)

### Enhanced
- Starship configuration with additional modules (battery, jobs, time, cmd_duration)
- Hyprland window rules for better workspace organization
- Calculator functionality with `ans` variable support and operator continuation
- Terminal calculator prompt now shows current answer value

### Changed
- Bluetooth backups now limited to 3 most recent (auto-cleanup)
- Modern CLI tools now conditionally aliased based on availability

## [2025-06-19] - Previous State

### Existing Features
- Complete Hyprland (Wayland) and i3 (X11) configurations
- Tokyo Night theme across all applications
- Comprehensive Neovim setup with 25+ plugins
- Zsh with vi-mode and custom functions
- Tmux with vim-style keybindings
- Custom scripts for development workflow
- Bluetooth device management with automatic backups
- Calculator tools (popup and terminal versions)
- Comprehensive keybinding documentation
- Application launcher configurations
- Git workflow enhancements
- Database client configurations
- File manager setup with preview
- Notification system configuration
- Power management tools
- Screenshot and capture utilities

### Infrastructure
- Makefile for easy installation
- Bootstrap script for automated setup
- Comprehensive keybinding documentation
- Custom desktop application entries
- Systemd service configurations
- Tmux plugin management
- Git hooks and configurations