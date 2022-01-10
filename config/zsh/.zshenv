# Personal directories
export DOTFILES="$HOME/sync/src/dotfiles"

export NOTES="$HOME/sync/Vault"
export SYNC="$HOME/sync"
export BACKUP_DIR="$SYNC/backup"

export OBSIDIAN_PATH="$HOME/.local/bin/Obsidian-1.5.12.AppImage"

# XDG Base Directory Specification
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_CACHE_HOME="$HOME/.cache"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_STATE_HOME="$HOME/.local/state"

# ZSH configuration
export ZDOTDIR="$XDG_CONFIG_HOME/zsh"
export HISTFILE="$ZDOTDIR/.zhistory"
# X11
export XINITRC="$XDG_CONFIG_HOME/X11/.xinitc"

# History configuration
export HISTSIZE=10000
export SAVEHIST=$HISTSIZE
export KEYTIMEOUT=1

# Editor settings
export EDITOR="nvim"
export VISUAL="$EDITOR" # Reuse the EDITOR value
export MANPAGER='nvim +Man!'

# Browser setting, with a fallback if Firefox is not installed
if command -v firefox >/dev/null; then
    export BROWSER=$(command -v firefox)
else
    echo "Firefox is not installed. Please set the BROWSER variable manually."
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
export GOPATH="$XDG_DATA_HOME"/go
export GOMODCACHE="$XDG_CACHE_HOME"/go/mod
export NPM_CONFIG_USERCONFIG=$XDG_CONFIG_HOME/npm/npmrc
export RUSTUP_HOME="$XDG_DATA_HOME"/rustup
export GNUPGHOME="$XDG_DATA_HOME"/gnupg

# fzf configuration
export FZF_DEFAULT_COMMAND="rg --files --hidden --glob '!.git'"
export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"

export JAVA_HOME=/usr/lib/jvm/java-23-openjdk
export PATH=$JAVA_HOME/bin:$PATH
