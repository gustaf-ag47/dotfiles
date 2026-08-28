#!/bin/bash
# Assert `make install` is idempotent and non-destructive.
#
# The snapshot records each entry's TYPE and, for symlinks, its TARGET (%l).
# The target column is what catches the classic `ln -sf` bug where a second run
# nests the link inside its own target (~/.config/nvim/nvim -> ...) instead of
# replacing it -- a diff of names alone would not notice.
set -uo pipefail

: "${DOTFILES:=$HOME/sync/src/dotfiles}"
: "${XDG_CONFIG_HOME:=$HOME/.config}"
: "${ZDOTDIR:=$XDG_CONFIG_HOME/zsh}"

snapshot() {
	find "$XDG_CONFIG_HOME" "$HOME/.local/bin" "$HOME/.zshenv" \
		-maxdepth 2 -printf '%y %p -> %l\n' 2>/dev/null | sort
}

cd "$DOTFILES" || exit 1
rc=0

echo "== idempotency =="

echo "-- run 1 --"
make install >/tmp/idem1.log 2>&1 || { echo "  FAIL: first install failed"; tail -15 /tmp/idem1.log; exit 1; }

# Seed data that must survive a re-install. Do this BEFORE the first snapshot,
# otherwise the sentinels themselves show up as a diff and the test fails on
# its own fixtures.
echo 'sentinel-history-entry' >"$ZDOTDIR/.zhistory"
touch "$ZDOTDIR/plugins/.sentinel-marker"
snapshot >/tmp/idem-state1

echo "-- run 2 --"
make install >/tmp/idem2.log 2>&1 || { echo "  FAIL: second install failed"; tail -15 /tmp/idem2.log; exit 1; }
snapshot >/tmp/idem-state2

if diff -u /tmp/idem-state1 /tmp/idem-state2 >/tmp/idem.diff; then
	echo "  ok   symlink tree identical across runs"
else
	echo "  FAIL symlink tree changed on second run:"
	sed 's/^/       /' /tmp/idem.diff | head -30
	rc=1
fi

if grep -qx 'sentinel-history-entry' "$ZDOTDIR/.zhistory" 2>/dev/null; then
	echo "  ok   zsh history survived re-install"
else
	echo "  FAIL zsh history destroyed by re-install (HISTFILE is \$ZDOTDIR/.zhistory)"
	rc=1
fi

if [ -e "$ZDOTDIR/plugins/.sentinel-marker" ]; then
	echo "  ok   zsh plugins not wiped/re-cloned"
else
	echo "  FAIL zsh plugins wiped and re-cloned (install needs the network every run)"
	rc=1
fi

# A real directory at a link target must be backed up, never deleted.
echo "-- non-destructive --"
rm -f "$XDG_CONFIG_HOME/nvim"
mkdir -p "$XDG_CONFIG_HOME/nvim"
echo 'precious-user-data' >"$XDG_CONFIG_HOME/nvim/USERDATA.txt"
make install >/tmp/idem3.log 2>&1
if grep -rqx 'precious-user-data' "$XDG_CONFIG_HOME"/nvim.bak.* 2>/dev/null; then
	echo "  ok   real directory backed up, not deleted"
else
	echo "  FAIL real directory at link target was destroyed"
	rc=1
fi
if [ -L "$XDG_CONFIG_HOME/nvim" ]; then
	echo "  ok   link restored after backup"
else
	echo "  FAIL link not restored"
	rc=1
fi

exit "$rc"
