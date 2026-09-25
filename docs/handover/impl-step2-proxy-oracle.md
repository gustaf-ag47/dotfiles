# Brief — Step 2: `claude-token-proxy` becomes the cross-provider quota + route oracle

**Agent:** delegated pi sub-agent, worktree branch `llm-proxy/step2-oracle`.
**Parent:** the orchestrator pi pane in the operator's tmux session. **Date:** 2026-09-25.
**Repo:** `$DOTFILES` = `/home/gud1/sync/src/dotfiles`, default branch `master`, public repo.

## Context

Read, in this order, fully:
1. `docs/handover/llm-proxy-implementation.md` — the plan; you are **Step 2**.
2. `docs/research/generic-llm-proxy.md` — §"Operator decisions" (binding), §3(c), §4
   (equivalence table), §5 (risks: `/_observe`-style endpoints must never accept
   bodies or Authorization; oracle readings from undocumented endpoints degrade to
   `unavailable`, never 0 %).
3. `docs/research/openai-deepseek-account-introspection.md` — the codex/deepseek
   endpoints you will poll from inside the proxy (§1, §3, Appendices).
4. `bin/claude-token-proxy` (~1100 lines, stdlib-only, single file, `ThreadingHTTPServer`)
   and `tests/unit/test_claude_token_proxy.py`. Key seams: `Tok`, `pick()`,
   `pressure()`, `routing_preview()` (added today — read-only dry run of `pick()` per
   weekly bucket, exposed on `GET /_usage` as `routing`), `fetch_oauth_usage()` +
   the `USAGE_INTERVAL` watcher thread, `_usage_page()`, `_status_page()`, `do_GET`.
5. `scripts/llm_usage.py` — `codex()` and `deepseek()` adapters and `deepseek_key()`.
   **Copy** their logic into the proxy (stdlib-only, single-file rule); do not import
   `scripts/`. A sibling agent (Step 1) is enriching those adapters right now on
   `llm-proxy/step1-usage-rich`; if it has landed on `origin/master` before you copy,
   copy the enriched version, otherwise copy today's and note it.

Binding decisions: #2 (architecture c — oracle only, **no request routing in this
step**), #5 (equivalence table below), #6 (labels: Codex from JWT claims; DeepSeek
`DEEPSEEK_ACCOUNT_LABEL` → `auth.json` `label` → last-4).

## Your job

1. **`config/llm-proxy/routes.json`** (tracked, no secrets):
   ```json
   {"claude-fable-5-1": [["openai-codex","gpt-6-astra"],["openai-codex","gpt-6-sol"],["deepseek","deepseek-v4-pro"]],
    "claude-opus-5-5":  [["openai-codex","gpt-6-luna"],["deepseek","deepseek-v4-pro"]],
    "claude-sonnet-5":  [["openai-codex","gpt-6-sol"],["deepseek","deepseek-flash"]],
    "claude-haiku-4-5": [["openai-codex","gpt-6-luna"],["deepseek","deepseek-flash"]]}
   ```
   Match by model *prefix* (`claude-opus-5-5-20260901` → `claude-opus-5-5`; also
   `claude-fable-5` → nearest fable row). Loaded at start, re-read on mtime change.
   Path resolved relative to the proxy file (`../config/llm-proxy/routes.json`),
   overridable by `CC_PROXY_ROUTES`.
2. **`/_usage` gains `providers`**: `{"anthropic": {...existing tokens+routing...},
   "openai-codex": {...}, "deepseek": {...}}` where the codex/deepseek shapes are
   exactly what `scripts/llm_usage.py` returns for them (so the reader can switch to
   the proxy as its single source in a later step with no re-mapping). Poll them on
   the existing watcher thread every `USAGE_INTERVAL`, cache in memory, `checked_at`
   per provider, any failure → `{"status":"unavailable","reason":...}` — never raise,
   never block a request. Credentials: read pi's `~/.pi/agent/auth.json`
   (`PI_CODING_AGENT_DIR` honoured) read-only, exactly as `llm_usage.py` does; **never
   refresh OAuth, never execute `!cmd` keys, never log tokens.**
3. **`GET /_route?model=<model>`** — pure, side-effect free. Returns
   ```json
   {"model":"claude-opus-5-5","candidates":[
     {"provider":"anthropic","model":"claude-opus-5-5","routable":true|false,"reason":null|"cooldown"|"exhausted"|"no token","quota_left_percent":..,"reset_at":..},
     {"provider":"openai-codex","model":"gpt-6-luna","routable":..,"reason":..,"quota_left_percent":..,"reset_at":..},
     {"provider":"deepseek","model":"deepseek-v4-pro","routable":..,"reason":"balance below floor"|..,"balance":..}],
    "first_routable": {...} | null}
   ```
   Anthropic first (derive from `routing_preview()` for the model's bucket), then the
   table order. Codex routable = window `used_percent < 100` and `allowed != false` and
   (if `model_usage` present) that model not blocked. DeepSeek routable = balance >
   `CC_PROXY_DEEPSEEK_MIN_BALANCE` (default `1.0`) and `is_available` not false.
   Unknown model → 404 JSON. Unknown provider state → `routable:false, reason:"unknown"`.
4. **Tests** in `tests/unit/test_claude_token_proxy.py`: routes.json loading + prefix
   match + reload; `/_route` ranking for (all routable), (anthropic cooling → codex),
   (codex at 100 % → deepseek), (deepseek below floor → none); providers block with a
   failing upstream → `unavailable`; no token/key string ever appears in any response
   body (assert on the JSON of `/_usage` and `/_route`). Existing 40 tests stay green.
5. **Restart and verify live** — the service is `systemctl --user
   claude-token-proxy.service` and runs the file from `$DOTFILES/bin` via a symlink in
   `~/.local/bin`; the running copy is the `master` checkout, NOT your worktree. So:
   land on master first, then restart, then `curl -s --noproxy '*'
   http://127.0.0.1:8788/_route?model=claude-opus-5-5`. Wait ~5 s after restart (it
   seeds tokens before listening). Confirm `llm-usage` still renders (it reads
   `/_usage`; the added `providers` key must not break it).

## Scope fence

- **You own:** `bin/claude-token-proxy`, `tests/unit/test_claude_token_proxy.py`,
  `config/llm-proxy/routes.json` (new), the proxy docstring at the top of the file.
- **Do NOT touch:** `scripts/llm_usage.py`, `tests/unit/test_llm_usage.py`,
  `config/pi/*`, `~/.pi/agent/*`. Do NOT implement any request forwarding to DeepSeek
  or OpenAI — that is Step 3, a later agent.
- Sibling running now: **Step 1** on `llm-proxy/step1-usage-rich` owning
  `scripts/llm_usage.py` + its test.

## Constraints

- Read `CLAUDE.md` and `README.md` first. Commit hook: `type(scope): subject`,
  lowercase, imperative, ≤50 chars; blocks company names and secret-looking strings.
- Keep the proxy **stdlib-only and single-file**; the existing style is docstrings +
  sparse comments — match it.
- Verification gates, run and report by name:
  ```bash
  python3 -m unittest tests.unit.test_claude_token_proxy -v
  make test-unit
  systemctl --user restart claude-token-proxy.service && sleep 6 && \
    curl -s --noproxy '*' 'http://127.0.0.1:8788/_route?model=claude-opus-5-5' | python3 -m json.tool
  llm-usage --refresh
  ```
- Git: `GIT_EDITOR=true`; rebase on `origin/master`, linear history,
  `git push origin HEAD:master`; on rejection rebase again, never merge.
- Scratch under `$(pi-scratch dir llm-step2)`, never `/tmp`.

## Where to record findings

Commit body + a "Step 2 — done" note appended to
`docs/handover/llm-proxy-implementation.md` (sha, gates by name, the live `/_route`
output redacted, open items). Raw output to
`$NOTES/<project>/driver/agent-runs/2026-09-25/<HHMM>_llm-step2-output.md`
(`$NOTES=/home/gud1/sync/Vault`) with front-matter `model`, `cost_usd`, `branch`, `landed_in`.

## When done or blocked — report back to the parent

Steps 3 and 4 are gated on you. When finished (or blocked), post into the parent's
pane yourself, then stay idle:

```bash
tmux send-keys -t "$PI_PARENT_PANE" -l "STEP2 DONE <sha> — <one line: what landed, gates run, open items>"; tmux send-keys -t "$PI_PARENT_PANE" Enter
```
If `PI_PARENT_PANE` is unset, the parent pane id is `%1520` (verify with `tmux list-panes -a -F '#{pane_id} #{pane_current_command}'`).

## Cost guidance

Target ~$10. Stop at $18 with what you have committed and reported.
