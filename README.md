# Dotfiles

A keyboard-driven Arch Linux development environment with Hyprland (Wayland), i3 (X11), Zsh, Neovim, tmux and Pi.

```bash
make install                             # user config symlinks
make install-system                      # root-side drift (dry run)
sudo scripts/install-system.sh --apply   # apply root-side layer
make test && make lint
```

Documentation lives in the operator notes, not in this repo: `$NOTES/Homelab/dotfiles/`
(`README.md`, `SYSTEM_LAYER.md`, `PROFILES.md`, `TESTING.md`, `KEYBINDINGS.md`,
`GIT_WORKFLOW.md`, `LINTING.md`, `SECURITY.md`, `BACKUP.md`).
