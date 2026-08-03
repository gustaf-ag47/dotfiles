#!/usr/bin/env bash
# Static audit for common nvim-config footguns.
# Run before committing. Exit code = number of issues found.

set -uo pipefail

if [ -d "${DOTFILES:-}" ]; then
  ROOT="$DOTFILES/config/nvim"
elif [ -d "$HOME/.config/nvim" ]; then
  ROOT="$(readlink -f "$HOME/.config/nvim")"
else
  echo "ERROR: can't find nvim config root. Set DOTFILES env var." >&2
  exit 2
fi

cd "$ROOT"
echo "═══ nvim audit @ $ROOT ═══"
echo

ISSUES=0
section() { echo; echo "── $* ──"; }

section "1) vim.notify at startup-risk locations"
# Real risk = files loaded during nvim startup before the UI is ready:
#   - lua/core/*.lua          (loaded by init.lua → require('core'))
#   - $NOTES/nvim-projects/*  (dofile'd by the LazyDone autocmd)
# Inside callbacks/commands/handlers vim.notify is fine: by the time they
# fire, the UI is up. We DON'T scan lua/plugins/* or lua/features/* here
# because those are predominantly callback-time.
# NOTE: core/notify.lua is the safe wrapper; exclude it from this check.
risky=0
grepout=$(mktemp)
grep -nE 'vim\.notify\(' lua/core/*.lua 2>/dev/null | \
  grep -v lua/core/notify.lua | \
  grep -v '^[^:]*:[^:]*:[[:space:]]*require' | \
  grep -v '^[^:]*:[^:]*:[[:space:]]*--' > "$grepout" || true
while IFS=: read -r fn ln src; do
  # Check for vim.schedule in prior context
  context=$(sed -n "1,$((ln-1))p" "$fn" | tail -c 200)
  if ! echo "$context" | grep -q 'vim.schedule'; then
    echo "$fn:$ln:  $(echo "$src" | head -c 100)"
    risky=$((risky + 1))
  fi
done < "$grepout"
rm -f "$grepout"
if [ "$risky" -gt 0 ]; then
  echo "  ⚠ $risky unscheduled vim.notify in lua/core/"
  ISSUES=$((ISSUES + risky))
else
  echo "  ✓ lua/core/ clean"
fi
if [ -d "${NOTES:-}/nvim-projects" ]; then
  np=$(grep -rnE '^vim\.notify\(' "${NOTES}/nvim-projects" 2>/dev/null | wc -l)
  if [ "$np" -gt 0 ]; then
    echo "  ⚠ $np vim.notify in \$NOTES/nvim-projects/ at file-scope (wrap in vim.schedule):"
    grep -rnE '^vim\.notify\(' "${NOTES}/nvim-projects" 2>/dev/null | head -5
    ISSUES=$((ISSUES + np))
  else
    echo "  ✓ \$NOTES/nvim-projects/ clean"
  fi
fi

section "2) busy/lock flags without auto-reset"
python3 <<'PY'
import re, glob
for f in glob.glob('lua/**/*.lua', recursive=True):
    src = open(f).read()
    for m in re.finditer(r'^(\s*)local\s+(\w+)\s*=\s*(true|false)\s*(?:--|\n)', src, re.MULTILINE):
        name = m.group(2)
        if any(k in name.lower() for k in ['in_progress', 'busy', 'locked', 'is_loading', 'pending']):
            companion = name + '_since'
            if companion not in src and 'self_heal' not in src.lower() and 'TTL' not in src and 'stale_after' not in src:
                print(f"  ⚠ {f}: flag `{name}` has no _since timestamp or self-heal/TTL")
PY

section "3) lazy cmd= entries that also nvim_create_user_command in init"
python3 <<'PY'
import re, glob
issues = 0
for f in glob.glob('lua/plugins/*.lua'):
    src = open(f).read()
    cm = re.search(r'cmd\s*=\s*\{([^}]+)\}', src)
    if not cm: continue
    cmds = set(re.findall(r"['\"]([A-Z][A-Za-z0-9_]+)['\"]", cm.group(1)))
    reg  = set(re.findall(r"nvim_create_user_command\(['\"]([A-Z][A-Za-z0-9_]+)['\"]", src))
    bad = cmds & reg
    if bad:
        print(f"  ⚠ {f}: {bad} in cmd=list AND registered in init (lazy stub-deletion trap)")
        issues += 1
if issues == 0: print("  ✓ clean")
PY

section "4) duplicate top-level plugin specs across files"
python3 <<'PY'
import re, glob
def classify(src, pos):
    # Find the enclosing { ... } block by counting braces backwards.
    # Return 'DEP' if inside dependencies={}, 'OPT' if marked optional=true,
    # 'TOP' otherwise.
    ctx = src[max(0,pos-400):pos]
    if 'dependencies' in ctx:
        dp = ctx.rfind('dependencies')
        if ctx[dp:].count('{') > ctx[dp:].count('}'):
            return 'DEP'
    # Look at the immediate surrounding 400 chars (forward + backward) for
    # optional=true marker (lazy.nvim convention for extension specs)
    after = src[pos:pos+400]
    if re.search(r'optional\s*=\s*true', after):
        return 'OPT'
    return 'TOP'
seen = {}
for f in glob.glob('lua/plugins/*.lua') + glob.glob('lua/lang/*.lua'):
    src = open(f).read()
    for m in re.finditer(r"['\"]([\w-]+/[\w.-]+)['\"]", src):
        sp = m.group(1)
        if any(c in sp for c in ['.json', ' ']): continue
        if '/' not in sp or sp.count('/') != 1: continue
        cls = classify(src, m.start())
        if cls == 'TOP':
            seen.setdefault(sp, set()).add(f)
issues = 0
for sp, files in sorted(seen.items()):
    if len(files) > 1:
        print(f"  ⚠ {sp}: TOP-level spec in {sorted(files)}")
        issues += 1
if issues == 0: print("  ✓ clean")
PY

section "5) dead modules"
python3 <<'PY'
import re, glob
mods = {f.replace('lua/','').replace('.lua','').replace('/','.') for f in glob.glob('lua/**/*.lua', recursive=True)}
mods = {m for m in mods if not m.endswith('.init')}
required = set()
for f in glob.glob('lua/**/*.lua', recursive=True):
    src = open(f).read()
    # Both styles: require('X.Y') AND require 'X.Y' (no parens)
    required |= set(re.findall(r"require\(['\"]([\w.]+)['\"]\)", src))
    required |= set(re.findall(r"require\s+['\"]([\w.]+)['\"]", src))
    # Snippets are loaded by luasnip from filenames, not require()
    if 'luasnip' in src.lower() or 'load_from' in src:
        for m in mods:
            if m.startswith('snippets.'):
                required.add(m)
    # Dynamic loader
    if 'safe_require' in src or 'load_features' in src or 'load_languages' in src:
        for m in mods:
            if m.startswith(('features.','lang.','plugins.')):
                required.add(m)
dead = sorted(mods - required - {'core.modules','core.lazy'})
if not dead:
    print("  ✓ clean")
else:
    for m in dead[:20]: print(f"  ⚠ {m}")
PY

echo
echo "═══ done; $ISSUES issue(s) flagged in section 1 (sections 2-5 print inline) ═══"
exit "$ISSUES"
