# Brief — Step 3: opt-in DeepSeek Anthropic-passthrough in `claude-token-proxy` (for Claude Code)

**Agent:** delegated pi sub-agent, worktree branch `llm-proxy/step3-deepseek-passthrough`.
**Parent:** the orchestrator pi pane in the operator's tmux session. **Date:** 2026-09-25.
**Repo:** `$DOTFILES` = `/home/gud1/sync/src/dotfiles`, default branch `master`, public repo.
**Prerequisite:** Step 2 (`/_route`, `routes.json`, provider polling) has landed on
`origin/master`. Confirm with `git log origin/master --oneline -5` before starting.

## Context

Read, in this order, fully:
1. `docs/handover/llm-proxy-implementation.md` — the plan; you are **Step 3**. Read the
   "Step 2 — done" note at the bottom for what actually landed.
2. `docs/research/generic-llm-proxy.md` — §"Operator decisions" #4 (binding), §TL;DR
   point 3, §3(a) "a-lite", §5 risks (DeepSeek is a different billing party and
   jurisdiction; a silent fallback burns prepaid balance; 402 when negative).
3. DeepSeek's Anthropic API guide: https://api-docs.deepseek.com/guides/anthropic_api
   (fetch it; note exactly which headers/fields it accepts, the model mapping it
   documents, and how it treats `anthropic-beta`, `cache_control`, `thinking`).
4. `bin/claude-token-proxy` — `_proxy()` (the request loop: `pick()` → `upstream()` →
   failover), `unavailable_message()`, `upstream()`, the Step-2 provider cache and
   `routes.json` loader, `routing_preview()`.

Why this exists: pi will get its own failover (Step 4), but the **real Claude Code
CLI** also goes through this proxy and has no extension point — when the Anthropic pool
is exhausted it just receives the "no OAuth account can serve" error. DeepSeek exposes
an Anthropic-compatible endpoint, so the *unchanged* Messages request can be forwarded
there with a different host, auth header and model name. Zero translation.

## Your job

1. **Config.** `CC_PROXY_DEEPSEEK_FALLBACK` (default `0`; `1` enables),
   `CC_PROXY_DEEPSEEK_MIN_BALANCE` (default `1.0`, USD; Step 2 may already define this —
   reuse it), DeepSeek key resolved the same way Step 2 resolves it for polling.
2. **Trigger.** Only when `pick()` returns `None` for the request's model (hard
   unavailability), never on pressure or threshold, and only if the cached DeepSeek
   balance is above the floor and `is_available` is not false. Otherwise the existing
   `unavailable_message()` path is unchanged.
3. **Forward.** Upstream `api.deepseek.com`, path unchanged (`/v1/messages`),
   `x-api-key: <deepseek key>` instead of `Authorization: Bearer`, model rewritten via
   `routes.json` (the `deepseek` entry for the matched Claude model; if none, do not
   fall back — return the unavailable message). Strip headers DeepSeek rejects (find
   out empirically: `anthropic-beta`? OAuth-specific headers?). Streaming must work
   (the existing read-to-EOF streaming path). Never send the OAuth token to DeepSeek.
   Never retry a DeepSeek 4xx against Anthropic (that would loop).
4. **Surface it.** One log line per fallback request
   (`-> deepseek deepseek-v4-pro (fallback: anthropic pool exhausted)`), a counter per
   model in the persisted usage state, and `routing.fallback = {"provider":"deepseek",
   "model":..., "since": <iso>, "requests": n}` in `/_usage` while the pool is exhausted
   and the feature is on (cleared when a real token becomes pickable again).
   `scripts/llm_usage.py` is NOT yours to edit — just make the JSON self-explanatory;
   Step 1's owner or a later pass renders it.
5. **Tests** in `tests/unit/test_claude_token_proxy.py` with a fake upstream: feature
   off → unavailable message (unchanged behaviour); on + balance ok + pool exhausted →
   forwarded with rewritten model and `x-api-key`, no `Authorization`; on + balance
   below floor → unavailable; on + pool healthy → never fires; DeepSeek 402 → returned
   to the client as-is, no Anthropic retry; the OAuth token never appears in the
   DeepSeek request. Existing tests green.
6. **Live check, once, opt-in.** After landing on master: restart the service with
   `CC_PROXY_DEEPSEEK_FALLBACK=1` ONLY IF the DeepSeek balance is above the floor (it
   was −0.12 USD on 2026-09-25 — if still negative, do the fake-upstream tests only and
   record that the live check is pending a top-up). Do not top up anything. Do not
   leave the feature enabled in the service environment.

## Scope fence

- **You own:** `bin/claude-token-proxy`, `tests/unit/test_claude_token_proxy.py`,
  `config/llm-proxy/routes.json` (only if a field is missing for this step).
- **Do NOT touch:** `scripts/llm_usage.py`, `config/pi/*`, `~/.pi/agent/*`, the
  service unit file. Do not enable the feature persistently.
- Sibling running now: **Step 4** (pi extension) on `llm-proxy/step4-pi-failover`,
  owning `config/pi/extensions/llm-failover.ts` and its test. It reads `/_route`; it
  does not touch the proxy. If you find `/_route` needs a change for it, coordinate by
  noting it in your report — do not edit its files.

## Constraints

- `CLAUDE.md`/`README.md` first. Commit hook: `type(scope): subject`, lowercase,
  imperative, ≤50 chars; blocks company names / secret-looking strings.
- Stdlib-only, single-file proxy. Existing style.
- Gates, by name:
  ```bash
  python3 -m unittest tests.unit.test_claude_token_proxy -v
  make test-unit
  systemctl --user restart claude-token-proxy.service && sleep 6 && llm-usage --refresh
  ```
- Git: `GIT_EDITOR=true`; rebase on `origin/master`, linear, `git push origin HEAD:master`.
- Scratch under `$(pi-scratch dir llm-step3)`, never `/tmp`.

## Where to record findings

Commit body + "Step 3 — done" note in `docs/handover/llm-proxy-implementation.md`
(sha, gates by name, which headers DeepSeek rejected, whether the live check ran).
Raw output to `$NOTES/<project>/driver/agent-runs/2026-09-25/<HHMM>_llm-step3-output.md`
(`$NOTES=/home/gud1/sync/Vault`) with front-matter `model`, `cost_usd`, `branch`, `landed_in`.

## When done or blocked — report back to the parent

```bash
tmux send-keys -t "$PI_PARENT_PANE" -l "STEP3 DONE <sha> — <one line: what landed, gates run, open items>"; tmux send-keys -t "$PI_PARENT_PANE" Enter
```
If `PI_PARENT_PANE` is unset, the parent pane id is `%1520` (verify with `tmux list-panes -a -F '#{pane_id} #{pane_current_command}'`).
Then stay idle.

## Cost guidance

Target ~$8. Stop at $15 with what you have committed and reported.
