# Brief — Step 1: richer read side in `scripts/llm_usage.py` (Codex identity + DeepSeek label)

**Agent:** delegated pi sub-agent, worktree branch `llm-proxy/step1-usage-rich`.
**Parent:** the orchestrator pi pane in the operator's tmux session. **Date:** 2026-09-25.
**Repo:** `$DOTFILES` = `/home/gud1/sync/src/dotfiles`, default branch `master`, public repo.

## Context

Read, in this order, fully:
1. `docs/handover/llm-proxy-implementation.md` — the plan; you are **Step 1**.
2. `docs/research/openai-deepseek-account-introspection.md` — the research this step
   executes. §1.2 (JWT claims), §1.3+ (`wham/usage` fields), §3.3 (DeepSeek label),
   §4 (proposed fields + mocked output), §5 (fixture list), Appendices A/B (redacted
   live samples).
3. `scripts/llm_usage.py` and `tests/unit/test_llm_usage.py` — what exists. The
   anthropic section already renders emails, `% left` bars, relative resets and a
   routing block; match that style exactly for the other two providers.
4. `bin/llm-usage`, `config/pi/extensions/llm-usage.ts` (the `/usage` command) — callers.

Operator decisions that bind you (recorded in `docs/research/generic-llm-proxy.md`
§"Operator decisions"): #6 — DeepSeek label order is `DEEPSEEK_ACCOUNT_LABEL` env →
`auth.json` `label` field → `…<last4>` of the key. Codex label comes from the
access-token JWT claims (local decode, no network).

## Your job

1. **openai-codex adapter returns identity + richer quota.** Decode the JWT `access`
   token locally (base64url, no signature check, no network): `email`, `name`,
   `chatgpt_plan_type`. From the existing `wham/usage` call keep: `email`, `plan_type`,
   `model_usage` (per-model `available`/`available_at`/`credits_would_enable` — verify
   exact keys against Appendix A), `credits.balance`, `rate_limit_reached_type`,
   `rate_limit_upsell`, `rate_limit_reset_credits`. Unknown/missing shape → the field is
   absent, never `0`. Done when `--json` shows the new fields and the render shows
   `<email> (<plan>)` + a verdict (`READY`/`LIMIT REACHED`), the window bar, per-model
   rows for anything blocked, and a "credits would unlock <model>" hint when true.
2. **deepseek adapter returns a label** per decision #6, plus renders the top-up URL
   `https://platform.deepseek.com/top_up` when `is_available` is false or balance ≤ 0.
   **First** read pi's source under
   `/home/gud1/.local/share/npm/lib/node_modules/@earendil-works/` to answer research
   open question #3: does pi preserve unknown fields in `auth.json` when it rewrites the
   file on OAuth refresh? Record the answer (with file:line) in the introspection doc's
   "Open questions" section. If pi drops them, say so in the render hint
   (`set DEEPSEEK_ACCOUNT_LABEL`) rather than relying on the `auth.json` tier.
3. **Tests.** Add the fixtures from research §5 (redacted; never a real token/key) to
   `tests/unit/test_llm_usage.py`: JWT decode (valid, malformed, missing claims),
   `wham/usage` with/without `model_usage`, credits present/absent, DeepSeek label tiers
   (env wins, auth.json second, last-4 fallback), negative balance render. Existing
   tests must stay green.
4. **Security posture unchanged**: read-only, no token refresh, no `!cmd` credential
   execution, never print/log tokens or keys, loopback never via inherited proxy.
   The 60 s report cache stays.

Done = all four, tests green, rebased on `origin/master`, pushed.

## Scope fence

- **You own:** `scripts/llm_usage.py`, `tests/unit/test_llm_usage.py`, the "Open
  questions" section of `docs/research/openai-deepseek-account-introspection.md`.
- **Do NOT touch:** `bin/claude-token-proxy`, `tests/unit/test_claude_token_proxy.py`,
  `config/`, `~/.pi/agent/*`, the running `claude-token-proxy.service`.
- Sibling running now: **Step 2** (proxy oracle) on branch `llm-proxy/step2-oracle`,
  owning `bin/claude-token-proxy`, `config/llm-proxy/routes.json` and the proxy tests.
  It will later COPY your adapter logic into the proxy — keep `codex()` and
  `deepseek()` as self-contained functions (stdlib only, no module-level state) so the
  copy is mechanical.

## Constraints

- Read `CLAUDE.md` and `README.md` first. Commit hook enforces `type(scope): subject`,
  lowercase, imperative, ≤50 chars; it also blocks company names and secret-looking
  strings — reword, never bypass.
- Verification gates, run and report by name:
  ```bash
  python3 -m unittest tests.unit.test_llm_usage -v
  make test-unit
  llm-usage --refresh            # live render, from the worktree: bin/llm-usage
  llm-usage --refresh --json | python3 -m json.tool | head -60
  ```
- Git: `GIT_EDITOR=true`; rebase on `origin/master`, keep linear history, then
  `git push origin HEAD:master`. If the push is rejected, rebase again — never merge.
- Scratch under `$(pi-scratch dir llm-step1)`, never `/tmp`.

## Where to record findings

Commit message body + a short "Step 1 — done" note appended to
`docs/handover/llm-proxy-implementation.md` (commit sha, what was verified by name,
anything you could not verify). Raw output to
`$NOTES/<project>/driver/agent-runs/2026-09-25/<HHMM>_llm-step1-output.md`
(`$NOTES=/home/gud1/sync/Vault`) with front-matter `model`, `cost_usd`, `branch`, `landed_in`.

## When done or blocked — report back to the parent

Your parent is orchestrating four steps and will decide whether to retire you or hand
you the next one. When you finish (or are blocked), **post a summary into the parent's
pane** — the watcher will also nudge it, but do this yourself so the message carries
content:

```bash
tmux send-keys -t "$PI_PARENT_PANE" -l "STEP1 DONE <sha> — <one line: what landed, gates run, open items>"; tmux send-keys -t "$PI_PARENT_PANE" Enter
```
If `PI_PARENT_PANE` is unset, the parent pane id is `%1520` (verify with `tmux list-panes -a -F '#{pane_id} #{pane_current_command}'`).
Then stay idle; do not start other work.

## Cost guidance

Target ~$6. Stop at $12 with what you have committed and reported.
