#!/bin/bash
# Build nix/agent-git's `agent-git`/`agent-gh` and point config/pi/bin's
# `git`/`gh` dispatchers at the built store paths. Agents-only: this does not
# touch Gustaf's interactive shells (their PATH never includes
# ~/.pi/agent/bin). See $NOTES/Homelab/dotfiles/agent-git.md.
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
FLAKE_DIR="$ROOT/nix/agent-git"

if ! command -v nix >/dev/null 2>&1; then
	export PATH="/nix/var/nix/profiles/default/bin:$PATH"
fi
command -v nix >/dev/null 2>&1 || {
	echo "nix not found. Install the Arch 'nix' package, enable nix-daemon.service," >&2
	echo "and set 'experimental-features = nix-command flakes' in /etc/nix/nix.conf first." >&2
	exit 1
}

mkdir -p "$FLAKE_DIR/.built"
nix build --extra-experimental-features "nix-command flakes" \
	"$FLAKE_DIR#agent-git" -o "$FLAKE_DIR/.built/agent-git"
nix build --extra-experimental-features "nix-command flakes" \
	"$FLAKE_DIR#agent-gh" -o "$FLAKE_DIR/.built/agent-gh"

echo "$FLAKE_DIR/.built/agent-git/bin/git" >"$FLAKE_DIR/.built/git-path"
echo "$FLAKE_DIR/.built/agent-gh/bin/gh" >"$FLAKE_DIR/.built/gh-path"

echo "agent-git: $(cat "$FLAKE_DIR/.built/git-path")"
echo "agent-gh:  $(cat "$FLAKE_DIR/.built/gh-path")"
echo "Run bin/pi-setup to (re)link config/pi/bin into the live agent bin dir."
