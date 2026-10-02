#!/bin/bash
# Idempotent, explicit setup for the pinned browser-use/jev-ultrafast checkout.
#
# Clones the pinned commit into a persistent XDG cache directory (outside git,
# never under the dotfiles checkout) and runs `uv sync` there. Never installs
# Chrome, never touches $HOME/.pi, never modifies any other skill, config, or
# credential file. Safe to re-run: a no-op once the pin and venv already match.
set -euo pipefail

UPSTREAM_URL="https://github.com/browser-use/jev-ultrafast.git"
PINNED_COMMIT="1231850a0bf1a0c0341fe408ef1668dbbfdfac46"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/jev-ultrafast"
CHECKOUT_DIR="$CACHE_DIR/src"

log() { printf '%s\n' "$*" >&2; }

command -v git >/dev/null 2>&1 || { log "setup.sh: missing dependency: git"; exit 1; }
command -v uv  >/dev/null 2>&1 || { log "setup.sh: missing dependency: uv (https://docs.astral.sh/uv/)"; exit 1; }

if ! command -v chromium >/dev/null 2>&1 && ! command -v google-chrome >/dev/null 2>&1 \
   && ! command -v chromium-browser >/dev/null 2>&1; then
  log "setup.sh: warning: no chromium/google-chrome binary found on PATH."
  log "  jev-ultrafast connects to a real installed Chrome via Browser Harness;"
  log "  install one, then re-run 'uv run browser-harness --doctor' inside $CHECKOUT_DIR."
fi

mkdir -p "$CACHE_DIR"

if [[ -d "$CHECKOUT_DIR/.git" ]]; then
  current_commit="$(git -C "$CHECKOUT_DIR" rev-parse HEAD 2>/dev/null || true)"
  if [[ "$current_commit" == "$PINNED_COMMIT" ]]; then
    log "setup.sh: pinned checkout already at $PINNED_COMMIT"
  else
    dirty="$(git -C "$CHECKOUT_DIR" status --porcelain 2>/dev/null || true)"
    if [[ -n "$dirty" ]]; then
      log "setup.sh: $CHECKOUT_DIR has local changes at $current_commit; not touching it."
      log "  Remove or re-pin it manually, then re-run this script."
      exit 1
    fi
    log "setup.sh: $CHECKOUT_DIR is at $current_commit, pin wants $PINNED_COMMIT; re-checking out."
    git -C "$CHECKOUT_DIR" fetch --depth 1 origin "$PINNED_COMMIT"
    git -C "$CHECKOUT_DIR" checkout --detach "$PINNED_COMMIT"
  fi
else
  log "setup.sh: cloning $UPSTREAM_URL at $PINNED_COMMIT into $CHECKOUT_DIR"
  git clone --no-checkout "$UPSTREAM_URL" "$CHECKOUT_DIR"
  git -C "$CHECKOUT_DIR" checkout --detach "$PINNED_COMMIT"
fi

verified_commit="$(git -C "$CHECKOUT_DIR" rev-parse HEAD)"
if [[ "$verified_commit" != "$PINNED_COMMIT" ]]; then
  log "setup.sh: checkout at $verified_commit, expected pinned $PINNED_COMMIT; refusing to continue."
  exit 1
fi

log "setup.sh: running 'uv sync' in $CHECKOUT_DIR (creates/updates its own .venv there, not in dotfiles git)"
(cd "$CHECKOUT_DIR" && uv sync)

log "setup.sh: done. Checkout: $CHECKOUT_DIR @ $verified_commit"
log "setup.sh: next: python3 $(dirname "$0")/doctor.py"
