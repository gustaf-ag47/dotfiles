#!/bin/bash

set -euo pipefail

# Fail loudly and early on missing tools. Without this, a fresh machine gets a
# bare "rsync: command not found" from line 15 after the repo is already cloned,
# and `make install` dies with an opaque exit 127.
missing=""
for dep in git rsync; do
	command -v "$dep" >/dev/null 2>&1 || missing="$missing $dep"
done
if [ -n "$missing" ]; then
	echo "error: missing required tools:$missing" >&2
	echo "install them first, e.g.: sudo pacman -S --needed$missing" >&2
	exit 1
fi

# Resolve relative to this script, not $PWD: `bash ~/dotfiles/scripts/install.sh`
# from any other directory used to die with "config/zsh/.zshenv: No such file".
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091  # sourced at runtime; path is resolved from $REPO_ROOT
source "$REPO_ROOT/config/zsh/.zshenv"

if [ -d "$DOTFILES/bin" ] && [ -d "$DOTFILES/config" ] && [ -f "$DOTFILES/Makefile" ]; then
	echo "Dotfiles are correctly located at $DOTFILES."
else
	mkdir -p "$DOTFILES"
	echo "Dotfiles not found or incomplete at $DOTFILES."
	ORIGINAL="$REPO_ROOT"
	rsync -av "$ORIGINAL/" "$DOTFILES"
	echo "Dotfiles installed at $DOTFILES."
	cd "$DOTFILES"
	# Only remove the staging clone, and only if it is genuinely somewhere else.
	# Without this guard an incomplete tree already at $DOTFILES rsyncs onto
	# itself and then deletes itself.
	if [ -n "${ORIGINAL:-}" ] && [ "$ORIGINAL" != "$DOTFILES" ]; then
		rm -rf "$ORIGINAL"
	fi
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

# Create symlink from dotfiles/local to $SYNC/dotfiles-local.
# A REAL local/ directory holds user data (private configs, keys): back it up
# next to itself, never rm -rf it (same non-destructive rule as link_config).
#
# The link is RELATIVE: it sits inside the repo working tree, which Syncthing
# shares between machines, so an absolute target (/home/<user>/...) flipped to
# whichever machine wrote it last and dangled on the other (users differ:
# gustaf vs gud1). Both machines keep dotfiles-local at the same place relative
# to the repo, so the relative link resolves everywhere.
local_target="$(realpath -m --relative-to="$DOTFILES" "$SYNC/dotfiles-local")"
if [ -L "$DOTFILES/local" ] && [ "$(readlink "$DOTFILES/local")" != "$local_target" ]; then
	echo "Replacing local/ link ($(readlink "$DOTFILES/local")) with relative $local_target"
	rm -f "$DOTFILES/local"
fi
if [ ! -L "$DOTFILES/local" ]; then
	if [ -d "$DOTFILES/local" ]; then
		backup="$DOTFILES/local.bak.$(date +%Y%m%d%H%M%S)"
		echo "Backing up real local/ to $backup"
		mv "$DOTFILES/local" "$backup"
	fi
	echo "Creating symlink: $DOTFILES/local → $local_target"
	ln -s "$local_target" "$DOTFILES/local"
	echo "✅ Local configurations will be stored in $SYNC/dotfiles-local"
fi

# Idempotent and non-destructive.
#
#   - an already-correct symlink is a no-op (so re-running touches nothing)
#   - a real file/dir in the way is BACKED UP, never deleted. The old
#     `rm -rf "$dst"` was the ShellCheck SC2115 shape that wiped home
#     directories in the Steam incident, and it silently destroyed any real
#     directory a user had at the target.
#   - `ln -sfn`, not `ln -sf`: without -n, pointing a directory link at an
#     existing symlink-to-directory creates the link INSIDE the target
#     (~/.config/nvim/nvim) instead of replacing it.
link_config() {
	local src=$1 dst=$2
	if [ ! -e "$src" ]; then
		echo "  warning: missing source $src, skipping" >&2
		return 0
	fi
	if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
		return 0
	fi
	if [ -e "$dst" ] && [ ! -L "$dst" ]; then
		local backup
		backup="$dst.bak.$(date +%Y%m%d%H%M%S)"
		echo "  backing up existing $dst -> $backup"
		mv "$dst" "$backup"
	fi
	mkdir -p "$(dirname "$dst")"
	ln -sfn "$src" "$dst"
}

# NOTE: do NOT `rm -rf "$ZDOTDIR"` here. HISTFILE is $ZDOTDIR/.zhistory, so
# that wiped the entire zsh history on every `make install`, along with
# .zcompdump and the cloned plugins (forcing a re-clone, and making the
# install pointlessly depend on the network).
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
mkdir -p "$XDG_CONFIG_HOME/mycli"
link_config "$DOTFILES/config/mycli/myclirc" "$XDG_CONFIG_HOME/mycli/myclirc"
link_config "$DOTFILES/config/xdg-user-dirs/user-dirs.dirs" "$XDG_CONFIG_HOME/user-dirs.dirs"

# Claude Code auth helper: sourced by .zshenv to select the OAuth token with the
# most quota headroom (see bin/claude-token-refresh / bin/claude-token-proxy).
mkdir -p "$XDG_CONFIG_HOME/claude-code"
link_config "$DOTFILES/config/claude-code/env.sh" "$XDG_CONFIG_HOME/claude-code/env.sh"

# Hot-swap proxy as a user service so EVERY session can rotate tokens mid-run
# (env.sh routes through it via ANTHROPIC_BASE_URL when it is active). The
# units use %h/.local/bin ExecStart paths; the bin/* loop below provides those
# links before any unit starts.
mkdir -p "$XDG_CONFIG_HOME/systemd/user" "${XDG_CACHE_HOME:-$HOME/.cache}/cc-proxy"
# Link EVERY unit file -- public ones from this repo, private ones (company
# infra, personal services) from the local/ overlay -- but enable only what the
# machine's roles and host declare (system/{roles/<role>,hosts/<host>}/
# user-services, after the profile is read below). A linked-but-not-enabled
# unit is inert.
for unit_dir in "$DOTFILES/config/systemd/user" "$DOTFILES/local/config/systemd/user"; do
	[ -d "$unit_dir" ] || continue
	for unit in "$unit_dir"/*.service "$unit_dir"/*.timer "$unit_dir"/*.path "$unit_dir"/*.socket; do
		[ -f "$unit" ] || continue
		link_config "$unit" "$XDG_CONFIG_HOME/systemd/user/$(basename "$unit")"
	done
done

# mkdir -p, not rm -rf + mkdir: transmission keeps its runtime state (stats,
# resume files, torrent list) in this directory and wiping it every install
# loses all of it.
mkdir -p "$XDG_CONFIG_HOME/transmission-daemon"
link_config "$DOTFILES/config/transmission/settings.json" "$XDG_CONFIG_HOME/transmission-daemon/settings.json"
link_config "$DOTFILES/config/newsboat" "$XDG_CONFIG_HOME/newsboat"
link_config "$DOTFILES/config/pulsemixer" "$XDG_CONFIG_HOME/pulsemixer"

# Link tmuxp configs from local directory (project/work-specific sessions)
if [ -d "$LOCAL_CONFIG/config/tmuxp" ]; then
    link_config "$LOCAL_CONFIG/config/tmuxp" "$XDG_CONFIG_HOME/tmuxp"
fi
link_config "$DOTFILES/config/tmux" "$XDG_CONFIG_HOME/tmux"

# tmux.conf loads plugins from $XDG_CONFIG_HOME/tmux/plugins (the symlinked,
# gitignored config/tmux/plugins/), so tpm must be cloned there.
[ ! -d "$XDG_CONFIG_HOME/tmux/plugins/tpm" ] &&
	git clone https://github.com/tmux-plugins/tpm "$XDG_CONFIG_HOME/tmux/plugins/tpm"

link_config "$DOTFILES/config/gui/dunst" "$XDG_CONFIG_HOME/dunst"
link_config "$DOTFILES/config/gui/alacritty" "$XDG_CONFIG_HOME/alacritty"
link_config "$DOTFILES/config/gui/zathura" "$XDG_CONFIG_HOME/zathura"
link_config "$DOTFILES/config/gui/gtk-3.0" "$XDG_CONFIG_HOME/gtk-3.0"
link_config "$DOTFILES/config/gui/gtk-2.0" "$XDG_CONFIG_HOME/gtk-2.0"
link_config "$DOTFILES/config/gui/jetbrains/ideavim" "$XDG_CONFIG_HOME/ideavim"

link_config "$DOTFILES/config/gui/Wayland/hypr" "$XDG_CONFIG_HOME/hypr"
link_config "$DOTFILES/config/gui/Wayland/waybar" "$XDG_CONFIG_HOME/waybar"
link_config "$DOTFILES/config/gui/Wayland/wofi" "$XDG_CONFIG_HOME/wofi"

# --- machine profile ------------------------------------------------------
# One file per machine describing what it IS (class, battery, gpu, disk), read
# both here and by install-arch. See profiles/README.md.
HOSTNAME="${HOST:-$(cat /etc/hostname 2>/dev/null || echo 'unknown')}"
PROFILE="${PROFILE:-$HOSTNAME}"
PROFILE_FILE="$DOTFILES/profiles/$PROFILE.env"
if [ ! -f "$PROFILE_FILE" ]; then
	echo "Warning: no profile at profiles/$PROFILE.env, falling back to default"
	echo "  create one so this machine gets the right config overlays"
	PROFILE_FILE="$DOTFILES/profiles/default.env"
fi
# shellcheck disable=SC1090  # path is computed at runtime
. "$PROFILE_FILE"
echo "Profile: $PROFILE (class=${PROFILE_CLASS:-unknown} battery=${PROFILE_HAS_BATTERY:-unknown})"

# systemd --user units this machine runs: declared per role and host, in the
# same system/ layers that hold its packages (see system/README.md).
if command -v systemctl >/dev/null 2>&1; then
	systemctl --user daemon-reload 2>/dev/null || true
	unit_lists=()
	for role in ${PROFILE_ROLES:-}; do
		unit_lists+=("$DOTFILES/system/roles/$role/user-services")
	done
	unit_lists+=("$DOTFILES/system/hosts/$PROFILE/user-services")
	for list in "${unit_lists[@]}"; do
		[ -f "$list" ] || continue
		while read -r action unit; do
			case "$action" in
			enable)
				if systemctl --user enable --now "$unit" 2>/dev/null; then
					echo "  user unit: $unit"
				else
					echo "  warning: could not enable user unit $unit"
				fi
				;;
			disable) systemctl --user disable --now "$unit" 2>/dev/null || true ;;
			esac
		done < <(sed -e 's/#.*//' -e '/^[[:space:]]*$/d' "$list")
	done
fi

# Machine facts at a fixed runtime path, so shells and scripts can read the
# profile without re-deriving it (e.g. .zshrc selects the class overlay).
cat > "$XDG_CONFIG_HOME/dotfiles-profile.env" <<EOF
# Generated by scripts/install.sh from profiles/$PROFILE.env - do not edit.
export PROFILE="$PROFILE"
export PROFILE_CLASS="${PROFILE_CLASS:-laptop}"
export PROFILE_GPU="${PROFILE_GPU:-}"
export PROFILE_HAS_BATTERY="${PROFILE_HAS_BATTERY:-}"
export PROFILE_ROLES="${PROFILE_ROLES:-}"
EOF

# Unified overlay resolution: hosts/<hostname>.<ext> wins, else
# class/<class>.<ext>, else an empty placeholder (base configs include the
# target unconditionally). Targets live OUTSIDE repo-symlinked dirs so
# Syncthing cannot collide them across machines.
link_overlay() {
	local root="$1" ext="$2" target="$3" placeholder="${4:-}" src=""
	if [ -f "$root/hosts/$HOSTNAME.$ext" ]; then
		src="$root/hosts/$HOSTNAME.$ext"
	elif [ -f "$root/class/${PROFILE_CLASS:-laptop}.$ext" ]; then
		src="$root/class/${PROFILE_CLASS:-laptop}.$ext"
	fi
	mkdir -p "$(dirname "$target")"
	if [ -n "$src" ]; then
		ln -sf "$src" "$target"
		echo "  overlay: ${src#"$DOTFILES/"}"
	else
		# No overlay for this machine: replace any stale link with a placeholder.
		[ -L "$target" ] && rm -f "$target"
		[ -e "$target" ] || printf '%s' "$placeholder" > "$target"
	fi
}

# Waybar's target used to be $XDG_CONFIG_HOME/waybar/profile.jsonc. That dir is a
# symlink INTO the repo, so the link landed in the working tree, got committed,
# and Syncthing fought over it between machines. Remove the old one if present.
legacy_waybar="$DOTFILES/config/gui/Wayland/waybar/profile.jsonc"
[ -L "$legacy_waybar" ] && rm -f "$legacy_waybar"
link_overlay "$DOTFILES/config/gui/Wayland/waybar" jsonc "$XDG_CONFIG_HOME/waybar-host.jsonc" '{}'
link_overlay "$DOTFILES/config/gui/Wayland/hypr" conf "$XDG_CONFIG_HOME/hypr-host.conf"
link_overlay "$DOTFILES/config/gui/Wayland/hypr/hypridle" conf "$XDG_CONFIG_HOME/hypridle-host.conf"
link_overlay "$DOTFILES/config/gui/alacritty" toml "$XDG_CONFIG_HOME/alacritty-host.toml"
link_overlay "$DOTFILES/config/tmux" conf "$XDG_CONFIG_HOME/tmux-host.conf"
link_overlay "$DOTFILES/config/environment.d" conf "$XDG_CONFIG_HOME/environment.d/50-host.conf"

# GPU overlay: keyed on PROFILE_GPU, not host/class (one hybrid laptop and one
# intel laptop share a class but not a GPU setup).
gpu_overlay="$DOTFILES/config/gui/Wayland/hypr/gpu/${PROFILE_GPU:-intel}.conf"
if [ -f "$gpu_overlay" ]; then
	ln -sfn "$gpu_overlay" "$XDG_CONFIG_HOME/hypr-gpu.conf"
	echo "  overlay: ${gpu_overlay#"$DOTFILES/"}"
else
	echo "Warning: no hypr gpu overlay for PROFILE_GPU=${PROFILE_GPU:-}, using an empty one"
	[ -L "$XDG_CONFIG_HOME/hypr-gpu.conf" ] && rm -f "$XDG_CONFIG_HOME/hypr-gpu.conf"
	[ -e "$XDG_CONFIG_HOME/hypr-gpu.conf" ] || : >"$XDG_CONFIG_HOME/hypr-gpu.conf"
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
link_config "$DOTFILES/config/environment.d/workspace.conf" "$XDG_CONFIG_HOME/environment.d/workspace.conf"

# Link starship configuration
link_config "$DOTFILES/config/starship.toml" "$XDG_CONFIG_HOME/starship.toml"

# Link atuin configuration (shell history sync)
link_config "$DOTFILES/config/atuin" "$XDG_CONFIG_HOME/atuin"

# Link yazi configuration (file manager)
[ -d "$DOTFILES/config/yazi" ] && link_config "$DOTFILES/config/yazi" "$XDG_CONFIG_HOME/yazi"

# Link bin directory (utility scripts). Prune dangling links first so deleted
# scripts do not linger on machines that installed them earlier.
mkdir -p "$HOME/.local/bin"
find "$HOME/.local/bin" -maxdepth 1 -xtype l -lname "$DOTFILES/bin/*" -delete 2>/dev/null || true
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

# Pi: provision extensions, libs, bin, and skills (public + private) into
# ~/.pi/agent via pi-setup. File-level symlinks, reversible backups; never
# touches auth.json, settings.json or runtime state. pi-setup replaced the
# older pi-link-extensions, which linked extensions WITHOUT config/pi/lib and
# so broke every new pi session on ../lib imports (2026-10-03).
if command -v pi >/dev/null 2>&1; then
    "$DOTFILES/bin/pi-setup" --apply || echo "  warning: pi-setup reported problems" >&2
fi

# Link Claude Code user configuration (private overlay only; not in this repo)
if [ -f "$DOTFILES/.claude/CLAUDE.md" ]; then
    mkdir -p "$HOME/.claude"
    link_config "$DOTFILES/.claude/CLAUDE.md" "$HOME/.claude/CLAUDE.md"
fi
