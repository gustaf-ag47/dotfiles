# Personal directories
# DOTFILES: Root directory for dotfiles repository
# Used by: Hyprland, Waybar, shell scripts, installation scripts
export DOTFILES="$HOME/sync/src/dotfiles"

# SYNC: Parent directory for synced files
# Used by: Neovim (leetcode storage), backup scripts, local configs
export SYNC="$HOME/sync"
export NOTES="$SYNC/Vault"
export BACKUP_DIR="$SYNC/backup"

# LOCAL_CONFIG: Personal/private configurations (symlinked in dotfiles)
# Stored in $SYNC for automatic backup and sync between machines
export LOCAL_CONFIG="$SYNC/dotfiles-local"

# Find latest Obsidian AppImage dynamically
OBSIDIAN_PATH="$(ls -t "$HOME/.local/bin"/Obsidian-*.AppImage 2>/dev/null | head -1)"
export OBSIDIAN_PATH="${OBSIDIAN_PATH:-}"

# XDG Base Directory Specification
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_CACHE_HOME="$HOME/.cache"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_STATE_HOME="$HOME/.local/state"

# ZSH configuration
export ZDOTDIR="$XDG_CONFIG_HOME/zsh"
export HISTFILE="$ZDOTDIR/.zhistory"
# X11
export XINITRC="$XDG_CONFIG_HOME/X11/.xinitrc"

# History configuration
export HISTSIZE=10000
export SAVEHIST=$HISTSIZE
export KEYTIMEOUT=1

# Editor settings
export EDITOR="nvim"
export VISUAL="$EDITOR" # Reuse the EDITOR value
export MANPAGER='nvim +Man!'

# Browser setting - use our custom browser launcher for Wayland compatibility
export BROWSER="$DOTFILES/bin/browser-launcher"

# Wayland environment variables for better application support
if [ -n "${WAYLAND_DISPLAY:-}" ]; then
    export MOZ_ENABLE_WAYLAND=1
    export MOZ_WEBRENDER=1
    export GDK_BACKEND=wayland,x11
    export QT_QPA_PLATFORM=wayland;xcb
    export SDL_VIDEODRIVER=wayland
    export CLUTTER_BACKEND=wayland
fi

# Path settings
export PYENV_ROOT="$XDG_DATA_HOME/pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"

if [ -d "$XDG_CONFIG_HOME/bin" ]; then
    export PATH="$XDG_CONFIG_HOME/bin:$PATH"
fi

if [ -d "$HOME/.local/bin" ]; then
    export PATH="$HOME/.local/bin:$PATH"
fi

export PATH="$DOTFILES/bin/:$PATH"

# Cleanup
export GOPATH="${XDG_DATA_HOME:-$HOME/.local/share}"/go
export PATH="$GOPATH/bin:$PATH"
export GOMODCACHE="$XDG_CACHE_HOME"/go/mod
export NPM_CONFIG_USERCONFIG=$XDG_CONFIG_HOME/npm/npmrc
export RUSTUP_HOME="$XDG_DATA_HOME"/rustup
export GNUPGHOME="$XDG_DATA_HOME"/gnupg

# fzf configuration
export FZF_DEFAULT_COMMAND="rg --files --hidden --glob '!.git'"
export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"

export JAVA_HOME=/usr/lib/jvm/java-23-openjdk
export PATH=$JAVA_HOME/bin:$PATH
