#!/usr/bin/env bash
# Install pre-commit hook for nvim config audit
#
# Run once to set up automatic audit checks before commits.
# After this, any commit touching config/nvim/ will run audit.sh first.
#
# Usage:
#   bash install-pre-commit-hook.sh
#
# To remove:
#   rm -f .git/hooks/pre-commit

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel)
HOOKS_DIR="$REPO_ROOT/.git/hooks"
HOOK_FILE="$HOOKS_DIR/pre-commit"

if [ -f "$HOOK_FILE" ]; then
  echo "✓ Hook already exists at $HOOK_FILE"
  read -p "  Overwrite? (y/n) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
  fi
fi

mkdir -p "$HOOKS_DIR"

cat > "$HOOK_FILE" <<'HOOK_SCRIPT'
#!/usr/bin/env bash
# Pre-commit hook: run nvim audit if config/nvim/ has staged changes

REPO_ROOT=$(git rev-parse --show-toplevel)
AUDIT_SCRIPT="$REPO_ROOT/config/nvim/tools/audit.sh"

# Check if any staged files touch config/nvim/
if ! git diff --cached --name-only | grep -q '^config/nvim/'; then
  exit 0
fi

echo "Running nvim audit (config/nvim/ has changes)..."
if bash "$AUDIT_SCRIPT"; then
  exit 0
else
  echo ""
  echo "✗ Audit failed. Fix issues or run:"
  echo "  git commit --no-verify"
  exit 1
fi
HOOK_SCRIPT

chmod +x "$HOOK_FILE"

echo "✓ Pre-commit hook installed at $HOOK_FILE"
echo ""
echo "What it does:"
echo "  • Runs audit.sh before any commit that touches config/nvim/"
echo "  • Blocks the commit if audit finds issues"
echo "  • Use --no-verify to skip (discouraged)"
echo ""
echo "To remove:"
echo "  rm -f $HOOK_FILE"
