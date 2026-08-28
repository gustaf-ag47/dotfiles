#!/bin/bash
# Post-install assertions for the dotfiles installer.
#
# Runs as an unprivileged user AFTER `make install`. Designed to be identical
# locally and in CI, so a CI failure is reproducible with one docker command:
#
#   docker run --rm -v "$PWD:/src:ro" archlinux:latest \
#     bash -c 'pacman -Syu --noconfirm --needed base-devel git rsync zsh curl sudo >/dev/null
#              useradd -m t; install -d -o t -g t /home/t/sync/src
#              rsync -a --exclude .git --exclude local /src/ /home/t/sync/src/dotfiles/
#              chown -R t:t /home/t/sync
#              su - t -c "cd ~/sync/src/dotfiles && make install && bash tests/install-assertions.sh"'
set -uo pipefail

pass=0 fail=0
ok() {
	printf '  \033[32mok\033[0m   %s\n' "$1"
	pass=$((pass + 1))
}
no() {
	printf '  \033[31mFAIL\033[0m %s\n' "$1"
	fail=$((fail + 1))
}
check() { # check DESCRIPTION test-command...
	local desc=$1
	shift
	if "$@"; then ok "$desc"; else no "$desc"; fi
}
is_link_to() { [ -L "$1" ] && [ "$(readlink "$1")" = "$2" ]; }

: "${DOTFILES:=$HOME/sync/src/dotfiles}"
: "${XDG_CONFIG_HOME:=$HOME/.config}"
: "${ZDOTDIR:=$XDG_CONFIG_HOME/zsh}"

echo "== dotfiles install assertions =="
echo "   DOTFILES=$DOTFILES"

echo "-- core symlinks --"
check "HOME/.zshenv -> repo" is_link_to "$HOME/.zshenv" "$DOTFILES/config/zsh/.zshenv"
check "\$ZDOTDIR/.zshrc -> repo" is_link_to "$ZDOTDIR/.zshrc" "$DOTFILES/config/zsh/.zshrc"
for c in nvim git tmux lf hypr waybar alacritty dunst atuin; do
	check "config/$c is a symlink" test -L "$XDG_CONFIG_HOME/$c"
done
check "local/bin/git-setup-hooks exists" test -e "$HOME/.local/bin/git-setup-hooks"

echo "-- resolvable through the link --"
check "tmux.conf resolves" test -f "$XDG_CONFIG_HOME/tmux/tmux.conf"
check "nvim init.lua resolves" test -f "$XDG_CONFIG_HOME/nvim/init.lua"

echo "-- zsh plugins --"
check "zsh-autosuggestions cloned" test -d "$ZDOTDIR/plugins/zsh-autosuggestions"
check "zsh-syntax-highlighting cloned" test -d "$ZDOTDIR/plugins/zsh-syntax-highlighting"

echo "-- no breakage --"
broken=$(find "$XDG_CONFIG_HOME" "$HOME/.local/bin" -maxdepth 2 -xtype l 2>/dev/null | wc -l)
if [ "$broken" -eq 0 ]; then
	ok "0 broken symlinks"
else
	no "$broken broken symlinks:"
	find "$XDG_CONFIG_HOME" "$HOME/.local/bin" -maxdepth 2 -xtype l 2>/dev/null | sed 's/^/       /'
fi

echo "-- env resolves in a real zsh --"
if command -v zsh >/dev/null 2>&1; then
	got=$(zsh -c 'source "$HOME/.zshenv"; printf "%s" "$DOTFILES"' 2>/dev/null)
	check "zsh resolves \$DOTFILES" test "$got" = "$DOTFILES"
else
	echo "  skip zsh not installed"
fi

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
