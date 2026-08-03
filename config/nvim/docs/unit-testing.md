# Unit Testing Pattern for DBUI Modules

Modules should have pure functions that are testable without a running nvim instance. This page documents the pattern.

## Template: The DML Guard Parser

The cleanest example is `features/dbui_dml_guard.lua`:

```lua
-- Pure function, testable without DB connection or nvim instance
function M.check(lines)
  -- input: array of strings (buffer lines)
  -- output: string (detected keyword) or nil (safe)
  -- no side effects, deterministic
end
```

**Tested by**: 22 `:lua` calls in the regression suite that feed different SQL strings and check the output. No DB, no plugin load, ~0.5s per test.

---

## How to Test Pure Functions

### In the regression suite (`$NOTES/db_ui/scripts/regression.sh`)

```bash
probe_parser <name> <sql> <expect:HIT|MISS|HIT:KW>

# Example
probe_parser "p_bare_DELETE" "DELETE FROM t;" HIT:DELETE
probe_parser "p_string_literal" "SELECT 'DELETE me';" MISS
```

The function:
1. Writes SQL to a tempfile
2. Runs `:lua M.check(vim.fn.readfile(...))` in nvim
3. Captures output to a file
4. Asserts expected vs got

**Why this works**: No network, no DB connection, just Lua → string comparison.

---

## Pattern: How to Structure Testable Code

### ✅ Good: Pure function

```lua
-- In features/my_feature.lua
function M.analyze(lines)
  -- Takes array of strings, returns result or nil
  -- No vim.notify, no global state, no I/O
  for i, line in ipairs(lines) do
    if line:match('DANGEROUS') then
      return 'DANGEROUS'
    end
  end
  return nil
end
```

### ✅ Good: Facade wraps pure function + side effects

```lua
function M.on_buffer_execute()
  -- This runs inside autocmd (has I/O, vim.notify)
  local lines = vim.api.nvim_buf_get_lines(0, 0, -1, false)
  local result = M.analyze(lines)  -- pure, testable
  if result then
    vim.notify('Blocked: ' .. result, vim.log.levels.ERROR)
  end
end
```

### ❌ Avoid: Side effects inside the logic function

```lua
-- Hard to test
function M.check(lines)
  for _, line in ipairs(lines) do
    if line:match('DANGEROUS') then
      vim.notify('Found dangerous keyword')  -- ❌ can't test this
      return true
    end
  end
  return false
end
```

---

## Example: Adding Tests to a New Module

Let's say you add `dbui_feature_xyz.lua`. Here's how to add regression tests:

### 1. Export a pure function from the module

```lua
-- lua/features/dbui_feature_xyz.lua
function M.parse(input)
  -- Pure logic here
  return result
end
```

### 2. Add test cases to `$NOTES/db_ui/scripts/regression.sh`

```bash
probe_xyz() {
  local name="$1" input="$2" expect="$3"
  local outfile=/tmp/regression_xyz.out
  rm -f "$outfile"
  tmux send-keys -t "$P" Escape
  local lua_cmd=":lua local m=require('features.dbui_feature_xyz') local r=m.parse('$input') io.open('/tmp/regression_xyz.out','w'):write(r or 'nil'):close()"
  tmux send-keys -t "$P" -l "$lua_cmd"
  tmux send-keys -t "$P" Enter
  sleep 0.3
  local got; got=$(cat "$outfile" 2>/dev/null || echo "TIMEOUT")
  local ok=1 mark="✓"
  [ "$got" = "$expect" ] || { ok=0; mark="✗"; }
  if [ "$ok" -eq 1 ]; then pass=$((pass+1)); else fail=$((fail+1)); fi
  results+=("$(printf '  %s  %-32s  expect=%-9s got=%s' "$mark" "$name" "$expect" "$got")")
}

run_xyz_tests() {
  note "── XYZ feature tests ──"
  probe_xyz "case_1" "input_a" "expected_output_a"
  probe_xyz "case_2" "input_b" "expected_output_b"
  probe_xyz "case_edge" "edge_case" "expected"
}

# In main section, add to the case statement:
case "$ONLY" in
  xyz) run_xyz_tests ;;
  *)   run_autocomplete_matrix; run_dml_matrix; run_health; run_xyz_tests ;;
esac
```

### 3. Run and verify

```bash
cd $NOTES/db_ui && bash scripts/regression.sh --xyz
# Should show all cases pass
```

---

## When to Add Tests

Add tests when:
- ✅ Function has non-trivial logic (parsing, filtering, matching)
- ✅ Edge cases exist (empty input, special characters, multi-line)
- ✅ The function could regress silently (easy to break later)

Don't add tests when:
- ❌ Function is just a wrapper around vim API calls
- ❌ Testing requires a running database or external service
- ❌ The logic is trivial (1-2 lines)

---

## Debugging a Test Failure

If `regression.sh` shows a failure:

```bash
# Run with verbose output
bash scripts/regression.sh -v

# Check the pane capture (tmux send-keys can be flaky)
tmux capture-pane -t "dbgflow-regression" -p

# Run a single probe to debug
bash scripts/regression.sh --xyz
```

Common issues:
- **Timeout**: lua code took too long or nvim crashed
- **Empty output**: file wasn't written (check lua_cmd syntax)
- **Flaky timing**: increase `sleep` duration in probe function
- **Tmux send-keys issues**: special chars need `-l` flag

---

## Extending DML Guard Tests (Reference)

The dml_guard tests are in `run_dml_parser_unit_tests()`:

```bash
probe_parser "p_bare_DELETE"        "DELETE FROM customer;"           HIT:DELETE
probe_parser "p_string_literal"     "SELECT 'DELETE me' AS note;"     MISS
```

To add a new case:
1. Write the SQL
2. Choose expect (HIT or MISS, or HIT:KEYWORD)
3. Add probe_parser call
4. Run regression suite
5. If it fails, debug the M.check() logic in dbui_dml_guard.lua

---

## Future: Standalone Test Harness

Once there are enough tests, consider extracting to a standalone harness:

```bash
# Hypothetical
nvim --headless -c "TestDDBUI" "+qa!"
# Runs all probes, exits with fail count
```

For now, the tmux-based regression suite is sufficient and integrates with the existing CI workflow.

---

## Summary

**Testable code pattern**:
- Pure functions: `input → output` (no side effects)
- Facade functions: call pure logic, handle vim I/O
- Tests live in `scripts/regression.sh` (tmux-driven)
- Run before commits: `bash scripts/regression.sh`

**Benefits**:
- Can run tests without a DB connection
- Fast feedback (35s for 52 probes)
- Integrates with audit + pre-commit hook
- Documentation-as-tests (each probe is a behavior spec)
