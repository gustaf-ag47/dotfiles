#!/bin/bash
# Idempotent, explicit setup for the pinned browser-use/jev-ultrafast checkout.
#
# Clones the pinned commit into a persistent XDG cache directory (outside git,
# never under the dotfiles checkout) and runs `uv sync --frozen` there (never
# updates the lockfile). Never installs Chrome, never touches $HOME/.pi,
# never modifies any other skill, config, or credential file. Safe to re-run:
# a no-op once the pin matches AND the tree is clean -- a dirty tree at the
# pinned commit is refused, not silently accepted, because HEAD matching the
# pin does not prove the working tree still matches it.
set -euo pipefail

UPSTREAM_URL="https://github.com/browser-use/jev-ultrafast.git"
PINNED_COMMIT="1231850a0bf1a0c0341fe408ef1668dbbfdfac46"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/jev-ultrafast"
CHECKOUT_DIR="$CACHE_DIR/src"

log() { printf '%s\n' "$*" >&2; }

# Pure, read-only check: prints one of ok | absent | dirty | unreadable |
# wrong_commit:<sha> on stdout, exit 0 only for "ok". No mutation, so this is
# safe to call repeatedly and to source+test in isolation without cloning
# anything.
verify_pinned_clean() {
  local dir="$1" expected="$2"
  if [[ ! -d "$dir/.git" ]]; then
    echo "absent"; return 1
  fi
  local commit
  if ! commit="$(git -C "$dir" rev-parse HEAD 2>/dev/null)"; then
    echo "unreadable"; return 1
  fi
  local dirty
  dirty="$(git -C "$dir" status --porcelain 2>/dev/null || echo "?")"
  if [[ -n "$dirty" ]]; then
    echo "dirty"; return 1
  fi
  if [[ "$commit" != "$expected" ]]; then
    echo "wrong_commit:$commit"; return 1
  fi
  echo "ok"; return 0
}

main() {
  command -v git >/dev/null 2>&1 || { log "setup.sh: missing dependency: git"; exit 1; }
  command -v uv  >/dev/null 2>&1 || { log "setup.sh: missing dependency: uv (https://docs.astral.sh/uv/)"; exit 1; }

  if ! command -v chromium >/dev/null 2>&1 && ! command -v google-chrome >/dev/null 2>&1 \
     && ! command -v chromium-browser >/dev/null 2>&1; then
    log "setup.sh: warning: no chromium/google-chrome binary found on PATH."
    log "  jev-ultrafast connects to a real installed Chrome via Browser Harness;"
    log "  install one, then re-run 'uv run browser-harness --doctor' inside $CHECKOUT_DIR."
  fi

  mkdir -p "$CACHE_DIR"

  local status
  status="$(verify_pinned_clean "$CHECKOUT_DIR" "$PINNED_COMMIT")" || true
  case "$status" in
    ok)
      log "setup.sh: pinned, clean checkout already at $PINNED_COMMIT"
      ;;
    absent)
      log "setup.sh: cloning $UPSTREAM_URL at $PINNED_COMMIT into $CHECKOUT_DIR"
      git clone --no-checkout "$UPSTREAM_URL" "$CHECKOUT_DIR"
      git -C "$CHECKOUT_DIR" checkout --detach "$PINNED_COMMIT"
      ;;
    dirty)
      log "setup.sh: $CHECKOUT_DIR has local changes; refusing to touch it."
      log "  Matching the pinned commit's HEAD is not enough -- a dirty tree may not run the pinned code."
      log "  Stash/discard the changes or delete the directory, then re-run."
      exit 1
      ;;
    unreadable)
      log "setup.sh: $CHECKOUT_DIR exists but its git state is unreadable; refusing to touch it."
      exit 1
      ;;
    wrong_commit:*)
      local current="${status#wrong_commit:}"
      log "setup.sh: $CHECKOUT_DIR is clean at $current, pin wants $PINNED_COMMIT; re-checking out."
      git -C "$CHECKOUT_DIR" fetch --depth 1 origin "$PINNED_COMMIT"
      git -C "$CHECKOUT_DIR" checkout --detach "$PINNED_COMMIT"
      ;;
    *)
      log "setup.sh: unexpected checkout state: '$status'"; exit 1
      ;;
  esac

  status="$(verify_pinned_clean "$CHECKOUT_DIR" "$PINNED_COMMIT")" || true
  if [[ "$status" != "ok" ]]; then
    log "setup.sh: checkout still not pinned+clean after update (state: $status); refusing to continue."
    exit 1
  fi

  log "setup.sh: running 'uv sync --frozen' in $CHECKOUT_DIR (uses uv.lock as-is, never updates it)"
  (cd "$CHECKOUT_DIR" && uv sync --frozen)

  log "setup.sh: done. Checkout: $CHECKOUT_DIR @ $PINNED_COMMIT"
  log "setup.sh: next: python3 $(dirname "$0")/doctor.py"
}

# Allow this file to be `source`d (e.g. by offline tests exercising
# verify_pinned_clean directly) without running main().
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
