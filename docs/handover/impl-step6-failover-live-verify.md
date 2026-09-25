# Brief — Step 6: live-verify `llm-failover.ts` switch AND switch-back; set the DeepSeek label

**Agent:** delegated pi sub-agent, worktree branch `llm-proxy/step6-failover-live`.
**Parent:** the orchestrator pi pane. **Date:** 2026-09-25.
**Repo:** `$DOTFILES` = `/home/gud1/sync/src/dotfiles`, default branch `master`, public repo.

## Context

Read `docs/handover/llm-proxy-implementation.md` fully (Step 4's "done" note and
"Remaining manual items"), then `config/pi/extensions/llm-failover.ts` and
`tests/unit/test_llm_failover.mjs`, then `docs/research/generic-llm-proxy.md`
§"Operator decisions" (#3 notify-only both directions is binding).

Step 4 verified the **switch-away** live against a stub proxy. Two things are not
verified end-to-end in a real pi process:

1. **Switch-back.** `turn_start` polls `/_route?model=<original>`; when the anthropic
   candidate is `routable` on two consecutive polls ≥60 s apart, `setModel` back and
   print `↩ back to anthropic/<model>: pool recovered`. Never driven with a real pi.
2. **The opt-out header** landed after Step 4 (`ad02886`): `config/pi/anthropic-token-proxy.ts`
   now registers the anthropic provider with `headers: {"x-cc-proxy-fallback": "none"}`
   and the proxy honours it (`FALLBACK_OPT_OUT_HEADER` in `bin/claude-token-proxy`,
   test `test_client_opt_out_header_keeps_the_unavailable_message`). Not yet observed
   from a real pi request — confirm the header actually arrives at the proxy when
   `pi-claude-sub` launches with both extensions.

Also a trivial local item: the DeepSeek row in `llm-usage` says `key …30cf` because no
label is set. Decision #6: `DEEPSEEK_ACCOUNT_LABEL` env is tier 1.

## Your job

1. **Build a stub proxy** (Python stdlib, under your scratch dir, not committed unless
   you turn it into a test fixture) on a free loopback port that: serves
   `POST /v1/messages` with the proxy's exact unavailable error (copy the shape from
   `unavailable_message()` / `_send_api_error()` in `bin/claude-token-proxy`, status
   503) while a flag file says "exhausted", and proxies to the real
   `http://127.0.0.1:8788` otherwise; serves `GET /_route?model=` returning
   anthropic `routable:false, reason:"cooldown"` while exhausted and `routable:true`
   after; logs every request's headers (redact `Authorization`) so you can see
   `x-cc-proxy-fallback`. Codex/DeepSeek candidates in the stub's `/_route` should
   mirror the real proxy's current answer (fetch it once) — today Codex is exhausted and
   DeepSeek negative, so to exercise the switch you will need the stub to claim ONE
   routable non-anthropic candidate. Use `openai-codex`/`gpt-6-luna` only if
   `llm-usage` shows it usable; otherwise the switch will land on a model that 429s —
   that is still a valid observation of the extension (report what pi shows), but
   prefer a target that answers.
2. **Drive a real pi** with `PI_ANTHROPIC_PROXY_URL=http://127.0.0.1:<stub>` via
   `pi-claude-sub -e config/pi/extensions/llm-failover.ts` in a tmux window you create
   (`tmux new-window -d`), interactive mode so `turn_start`/`turn_end` fire naturally.
   Sequence: flag exhausted → send a prompt → observe the `↪ switched …` line and the
   model badge; clear the flag → wait >60 s → send two prompts → observe `↩ back to
   anthropic/…` on the second. Capture panes as evidence. Also verify `/failover
   status` output and that `/failover off` suppresses the switch. Kill the window when
   done.
3. **Fix what you find.** If the switch-back does not fire, the model badge/cost is
   wrong, the notify line is missing in TUI mode, or the header is absent, fix it in
   `llm-failover.ts` (or `anthropic-token-proxy.ts` for the header) with a unit test in
   `tests/unit/test_llm_failover.mjs`. If the proxy needs a change, do NOT edit it —
   report the exact change needed.
4. **DeepSeek label.** Add `export DEEPSEEK_ACCOUNT_LABEL="<the account's email>"` to
   the gitignored local env (`local/env` — check how `local/` is sourced; the README
   in `local/` explains). The email is the one on the DeepSeek platform account — if
   you cannot determine it read-only, use `deepseek (gs)` and say so. Verify with
   `llm-usage --refresh --provider deepseek` in a fresh shell. Nothing here is committed.
5. **Record** the evidence (pane captures, stub log excerpt with the header line) in
   the done-note; keep the stub script if it became a fixture, else in the vault output.

## Scope fence

- **You own:** `config/pi/extensions/llm-failover.ts`, `tests/unit/test_llm_failover.mjs`,
  `config/pi/anthropic-token-proxy.ts` (header only), `local/env`, your stub under scratch.
- **Do NOT touch:** `bin/claude-token-proxy`, `scripts/llm_usage.py`, their tests,
  `config/llm-proxy/`, `~/.pi/agent/*`, the running `claude-token-proxy.service`
  (you point pi at your stub via env; never restart the real service).
- Sibling running now: **Step 5** on `llm-proxy/step5-pi-loading` owning
  `scripts/pi_setup.py`, `config/pi/**` wiring, `tests/unit/test_pi_*`,
  `bin/pi-claude-sub`, and `~/.pi/agent/extensions/` links. Launch pi with explicit
  `-e` paths from your worktree so its linking cannot change what you load.

## Constraints

- `CLAUDE.md`/`README.md` first. Commit hook: `type(scope): subject`, lowercase,
  imperative, ≤50 chars; blocks company names / secret-looking strings.
- Anthropic sessions go through `pi-claude-sub`, never plain `pi` (operator rule).
- Gates by name: `node --test tests/unit/test_llm_failover.mjs`; `make test-unit`
  (report count; a pre-existing red in `test_pi_provider_integration` is Step 5's, not
  yours — say so if it is still red); the live sequence in job 2 with pane evidence.
- Git: `GIT_EDITOR=true`; rebase on `origin/master`, linear, `git push origin HEAD:master`.
- Scratch under `$(pi-scratch dir llm-step6)`, never `/tmp`.
- Never print tokens/keys; redact `Authorization` in the stub log.

## Where to record findings

Commit bodies + "Step 6 — done" note in `docs/handover/llm-proxy-implementation.md`
(sha if any, the live sequence result line by line, header observed yes/no, label set).
Raw output → `$NOTES/<project>/driver/agent-runs/2026-09-25/<HHMM>_llm-step6-output.md`
(`$NOTES=/home/gud1/sync/Vault`) with front-matter `model`, `cost_usd`, `branch`, `landed_in`.

## When done or blocked — report back to the parent

```bash
tmux send-keys -t "$PI_PARENT_PANE" -l "STEP6 DONE <sha|no-code-change> — <one line: switch ✓/✗, switch-back ✓/✗, header ✓/✗, label set, open items>"; tmux send-keys -t "$PI_PARENT_PANE" Enter
```
`PI_PARENT_PANE` is exported; fallback pane id `%1520`. Then stay idle.

## Cost guidance

Target ~$8. Stop at $15 with what you have committed and reported.
