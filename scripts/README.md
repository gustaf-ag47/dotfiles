# scripts/

Repo-level scripts. User-facing commands live in `bin/`; these are installers,
setup helpers and libraries that `bin/` wrappers import.

- `install.sh` / `install-system.sh`: `make install` / `make install-system`
- `scan_keybindings.py`: scan the Neovim config for keymaps (stdlib only)

  ```bash
  python3 scripts/scan_keybindings.py [config_path] [--format markdown|json] [-o FILE] [-v]
  ```

  Review the output before merging into `$NOTES/Homelab/dotfiles/KEYBINDINGS.md`.
