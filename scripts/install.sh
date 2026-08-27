#!/bin/bash

echo "Bootstrap script"

set -euo pipefail

source "config/zsh/.zshenv"

if [ -d "$DOTFILES/bin" ] && [ -d "$DOTFILES/config" ] && [ -f "$DOTFILES/Makefile" ]; then
	echo "Dotfiles are correctly located at $DOTFILES."
else
	mkdir -p "$DOTFILES"
	echo "Dotfiles not found or incomplete at $DOTFILES."
	ORIGINAL="$(pwd)"
	rsync -av . "$DOTFILES"
	echo "Dotfiles installed at $DOTFILES."
	cd "$DOTFILES"
	rm -rf "$ORIGINAL"
fi

mkdir -p "$XDG_CONFIG_HOME"
mkdir -p "$XDG_DATA_HOME"

# Setup local configuration directory in $SYNC
# This allows personal configs to be backed up and synced
if [ ! -d "$SYNC/dotfiles-local" ]; then
	echo "Creating local configuration directory in $SYNC..."
	mkdir -p "$SYNC/dotfiles-local"/{applications,bin,config/zsh,config/git,env}
	echo "✅ Created $SYNC/dotfiles-local/"
fi

# Create symlink from dotfiles/local to $SYNC/dotfiles-local
if [ ! -L "$DOTFILES/local" ]; then
	echo "Creating symlink: $DOTFILES/local → $SYNC/dotfiles-local"
	rm -rf "$DOTFILES/local"
	ln -s "$SYNC/dotfiles-local" "$DOTFILES/local"
	echo "✅ Local configurations will be stored in $SYNC/dotfiles-local"
fi

link_config() {
	local src=$1 dst=$2
	rm -rf "$dst"
	ln -sf "$src" "$dst"
}

rm -rf "$ZDOTDIR"
mkdir -p "$ZDOTDIR"
link_config "$DOTFILES/config/zsh/.zshenv" "$HOME/.zshenv"
# Also link into $ZDOTDIR: a login shell reads $HOME/.zshenv (ZDOTDIR unset),
# but it then exports ZDOTDIR, so every child/nested zsh looks for
# $ZDOTDIR/.zshenv instead. Without this link those shells skip .zshenv
# entirely and miss all env/PATH exports.
link_config "$DOTFILES/config/zsh/.zshenv" "$ZDOTDIR/.zshenv"
link_config "$DOTFILES/config/zsh/.zshrc" "$ZDOTDIR/.zshrc"
link_config "$DOTFILES/config/zsh/aliases" "$ZDOTDIR/aliases"
link_config "$DOTFILES/config/zsh/external" "$ZDOTDIR/external"
link_config "$DOTFILES/config/zsh/scripts" "$ZDOTDIR/scripts"

PLUGIN_DIR="$ZDOTDIR/plugins"

if [ ! -d "$PLUGIN_DIR" ]; then
	mkdir "$PLUGIN_DIR"
fi

if [ ! -d "$PLUGIN_DIR/zsh-syntax-highlighting" ]; then
	git clone https://github.com/zsh-users/zsh-syntax-highlighting.git "$PLUGIN_DIR/zsh-syntax-highlighting"
fi

if [ ! -d "$PLUGIN_DIR/zsh-autosuggestions" ]; then
	git clone https://github.com/zsh-users/zsh-autosuggestions.git "$PLUGIN_DIR/zsh-autosuggestions"
fi

echo "Plugins installed. Please ensure your .zshrc is configured to source them."

link_config "$DOTFILES/config/nvim" "$XDG_CONFIG_HOME/nvim"
link_config "$DOTFILES/config/git" "$XDG_CONFIG_HOME/git"
link_config "$DOTFILES/config/lf" "$XDG_CONFIG_HOME/lf"
link_config "$DOTFILES/config/npm" "$XDG_CONFIG_HOME/npm"
link_config "$DOTFILES/config/mycli/myclirc" "$XDG_CONFIG_HOME/myclirc"
link_config "$DOTFILES/config/xdg-user-dirs/user-dirs.dirs" "$XDG_CONFIG_HOME/user-dirs.dirs"

# Claude Code auth helper: sourced by .zshenv to select the OAuth token with the
# most quota headroom (see bin/claude-token-refresh / bin/claude-token-proxy).
mkdir -p "$XDG_CONFIG_HOME/claude-code"
link_config "$DOTFILES/config/claude-code/env.sh" "$XDG_CONFIG_HOME/claude-code/env.sh"

# Hot-swap proxy as a user service so EVERY session can rotate tokens mid-run
# (env.sh routes through it via ANTHROPIC_BASE_URL when it is active).
# Symlink the binaries into ~/.local/bin so the unit's %h-relative ExecStart
# resolves regardless of where $DOTFILES lives or what PATH systemd uses.
mkdir -p "$HOME/.local/bin"
link_config "$DOTFILES/bin/claude-token-proxy" "$HOME/.local/bin/claude-token-proxy"
link_config "$DOTFILES/bin/claude-token-refresh" "$HOME/.local/bin/claude-token-refresh"
mkdir -p "$XDG_CONFIG_HOME/systemd/user" "${XDG_CACHE_HOME:-$HOME/.cache}/cc-proxy"
link_config "$DOTFILES/config/systemd/user/claude-token-proxy.service" \
	"$XDG_CONFIG_HOME/systemd/user/claude-token-proxy.service"
if command -v systemctl >/dev/null 2>&1; then
	systemctl --user daemon-reload 2>/dev/null || true
	systemctl --user enable --now claude-token-proxy.service 2>/dev/null || true
fi

rm -rf "$XDG_CONFIG_HOME/transmission-daemon"
mkdir "$XDG_CONFIG_HOME/transmission-daemon"
link_config "$DOTFILES/config/transmission/settings.json" "$XDG_CONFIG_HOME/transmission-daemon/settings.json"
link_config "$DOTFILES/config/newsboat" "$XDG_CONFIG_HOME/newsboat"
link_config "$DOTFILES/config/pulsemixer" "$XDG_CONFIG_HOME/pulsemixer"

# Link tmuxp configs from local directory (project/work-specific sessions)
if [ -d "$LOCAL_CONFIG/config/tmuxp" ]; then
    link_config "$LOCAL_CONFIG/config/tmuxp" "$XDG_CONFIG_HOME/tmuxp"
fi
link_config "$DOTFILES/config/tmux" "$XDG_CONFIG_HOME/tmux"

if [ ! -d "$XDG_DATA_HOME/tmux" ]; then
	mkdir "$XDG_DATA_HOME/tmux"
fi
[ ! -d "$XDG_DATA_HOME/tmux/plugins" ] &&
	git clone https://github.com/tmux-plugins/tpm "$XDG_DATA_HOME/tmux/plugins/tpm"

link_config "$DOTFILES/config/gui/dunst" "$XDG_CONFIG_HOME/dunst"
link_config "$DOTFILES/config/gui/alacritty" "$XDG_CONFIG_HOME/alacritty"
link_config "$DOTFILES/config/gui/zathura" "$XDG_CONFIG_HOME/zathura"
link_config "$DOTFILES/config/gui/gtk-3.0" "$XDG_CONFIG_HOME/gtk-3.0"
link_config "$DOTFILES/config/gui/gtk-2.0" "$XDG_CONFIG_HOME/gtk-2.0"
link_config "$DOTFILES/config/gui/jetbrains/ideavim" "$XDG_CONFIG_HOME/ideavim"

link_config "$DOTFILES/config/gui/Wayland/hypr" "$XDG_CONFIG_HOME/hypr"
link_config "$DOTFILES/config/gui/Wayland/waybar" "$XDG_CONFIG_HOME/waybar"
link_config "$DOTFILES/config/gui/Wayland/wofi" "$XDG_CONFIG_HOME/wofi"

# Create host-specific Hyprland config symlink (outside hypr dir to avoid sync issues)
HOSTNAME="${HOST:-$(cat /etc/hostname 2>/dev/null || echo 'unknown')}"
HOST_HYPR_CONF="$DOTFILES/config/gui/Wayland/hypr/hosts/$HOSTNAME.conf"
if [ -f "$HOST_HYPR_CONF" ]; then
    ln -sf "$HOST_HYPR_CONF" "$XDG_CONFIG_HOME/hypr-host.conf"
    echo "Linked host-specific Hyprland config: $HOSTNAME.conf"
else
    echo "Warning: No host-specific Hyprland config found for $HOSTNAME"
    echo "  Create one at: config/gui/Wayland/hypr/hosts/$HOSTNAME.conf"
    # Create empty fallback to prevent Hyprland errors
    touch "$XDG_CONFIG_HOME/hypr-host.conf"
fi

link_config "$DOTFILES/config/gui/Xorg/i3" "$XDG_CONFIG_HOME/i3"
link_config "$DOTFILES/config/gui/Xorg/rofi" "$XDG_CONFIG_HOME/rofi"
link_config "$DOTFILES/config/gui/Xorg/polybar" "$XDG_CONFIG_HOME/polybar"
link_config "$DOTFILES/config/gui/Xorg/X11" "$XDG_CONFIG_HOME/X11"

mkdir -p "$XDG_DATA_HOME/applications"
cp -r "$DOTFILES/config/applications/"* "$XDG_DATA_HOME/applications/"

# Copy local/personal desktop files (if they exist)
if [ -d "$DOTFILES/local/applications" ]; then
	echo "Installing personal desktop files..."
	for file in "$DOTFILES/local/applications"/*.desktop; do
		[ -f "$file" ] && cp "$file" "$XDG_DATA_HOME/applications/" && echo "  - $(basename "$file")"
	done
fi

# Copy local/personal autostart entries (if they exist)
if [ -d "$DOTFILES/local/autostart" ]; then
	echo "Installing personal autostart entries..."
	mkdir -p "$XDG_CONFIG_HOME/autostart"
	for file in "$DOTFILES/local/autostart"/*.desktop; do
		[ -f "$file" ] && cp "$file" "$XDG_CONFIG_HOME/autostart/" && echo "  - $(basename "$file")"
	done
fi

link_config "$DOTFILES/config/mimeapps/mimeapps.list" "$XDG_CONFIG_HOME/mimeapps.list"

# Link Wayland environment configuration
mkdir -p "$XDG_CONFIG_HOME/environment.d"
link_config "$DOTFILES/config/environment.d/wayland.conf" "$XDG_CONFIG_HOME/environment.d/wayland.conf"

# Link starship configuration
link_config "$DOTFILES/config/starship.toml" "$XDG_CONFIG_HOME/starship.toml"

# Link atuin configuration (shell history sync)
link_config "$DOTFILES/config/atuin" "$XDG_CONFIG_HOME/atuin"

# Link yazi configuration (file manager)
[ -d "$DOTFILES/config/yazi" ] && link_config "$DOTFILES/config/yazi" "$XDG_CONFIG_HOME/yazi"

# Link bin directory (utility scripts)
mkdir -p "$HOME/.local/bin"
for script in "$DOTFILES/bin/"*; do
    if [ -f "$script" ]; then
        ln -sf "$script" "$HOME/.local/bin/$(basename "$script")"
    fi
done

# Link private/personal utility scripts (if they exist)
if [ -d "$DOTFILES/local/bin" ]; then
    for script in "$DOTFILES/local/bin/"*; do
        if [ -f "$script" ]; then
            ln -sf "$script" "$HOME/.local/bin/$(basename "$script")"
        fi
    done
fi

# Link Claude Code user configuration
mkdir -p "$HOME/.claude"
link_config "$DOTFILES/.claude/CLAUDE.md" "$HOME/.claude/CLAUDE.md"
