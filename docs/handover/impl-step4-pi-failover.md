# Brief — Step 4: pi extension `llm-failover` — notify-only cross-provider switch via the proxy oracle

**Agent:** delegated pi sub-agent, worktree branch `llm-proxy/step4-pi-failover`.
**Parent:** the orchestrator pi pane in the operator's tmux session. **Date:** 2026-09-25.
**Repo:** `$DOTFILES` = `/home/gud1/sync/src/dotfiles`, default branch `master`, public repo.
**Prerequisite:** Step 2 (`GET /_route?model=`) has landed on `origin/master` and the
service is running it: `curl -s --noproxy '*' 'http://127.0.0.1:8788/_route?model=claude-opus-5-5'`
must return JSON with `candidates` and `first_routable`. Confirm before starting.

## Context

Read, in this order, fully:
1. `docs/handover/llm-proxy-implementation.md` — the plan; you are **Step 4**. Read the
   "Step 2 — done" note for the exact `/_route` shape that landed.
2. `docs/research/generic-llm-proxy.md` — §"Operator decisions" #2, #3 (binding:
   **notify-only, both directions, no confirmation prompt, no deny-list**), §3(c)
   including the pi hooks it names (`after_provider_response`, `model_select`,
   `pi.setModel()`), §5 (prompt-cache economics: switch only on hard unavailability;
   switch back when the pool recovers).
3. pi extension docs — read completely:
   `/home/gud1/.local/share/npm/lib/node_modules/@earendil-works/pi-coding-agent/docs/extensions.md`
   and the examples under `.../examples/extensions/`. Confirm the actual hook names and
   `setModel` signature in the installed version (`pi --version`); the research names
   may be approximate.
4. How extensions are loaded in this dotfiles setup: `bin/pi-claude-sub` passes `-e`
   for `config/pi/anthropic-oauth-claude-code-identity.ts` and
   `config/pi/anthropic-token-proxy.ts`; `config/pi/extensions/` holds
   `anthropic-subscription.ts`, `goal.ts`, `llm-usage.ts`;
   `docs/research/pi-unified-providers-and-dotfiles.md` describes the intended layout.
   `~/.pi/agent/settings.json` has `defaultProvider: anthropic`, `defaultModel:
   claude-fable-5`. Find how `config/pi/extensions/*.ts` actually reach a running pi
   (symlink? `-e` flag? settings?) and follow that — do not invent a new loading path.
5. `bin/claude-token-proxy` `unavailable_message()` / `_send_api_error()` — the exact
   error type/message the proxy returns when no OAuth account can serve. That is your
   trigger signal.

## Your job

1. **`config/pi/extensions/llm-failover.ts`.** On an Anthropic response that is the
   proxy's "no OAuth account can serve" error (match the error type/message from the
   proxy, not a generic 4xx), call `GET <PI_ANTHROPIC_PROXY_URL|http://127.0.0.1:8788>/_route?model=<current model>`
   (loopback, no inherited proxy, 3 s timeout). If `first_routable` is non-null and is
   not the anthropic entry, call `pi.setModel(provider, model)` and print ONE line in
   the session UI (`ctx.ui.notify` when there is a UI, `console.log` in print mode):
   `↪ switched to <provider>/<model>: anthropic pool exhausted (next reset <relative>)`.
   Remember the original provider/model in extension state. If nothing is routable,
   print `✗ no provider routable — anthropic <reason>, codex <reason>, deepseek <reason>`
   once and let the error propagate.
2. **Switch back.** While switched, before each turn (find the right hook — a
   pre-request / turn-start hook), poll `/_route?model=<original>` (respect a 60 s
   in-extension cache so it isn't a call per token). When the anthropic candidate is
   `routable`, `setModel` back to the original and print
   `↩ back to anthropic/<model>: pool recovered`. Never flap: require the anthropic
   candidate to be routable on two consecutive polls ≥ 60 s apart.
3. **Manual override.** Register `/failover` with subcommands `status` (prints current
   state + the `/_route` ranking), `off` (disable auto-switching for this session),
   `on`. No confirmation dialogs anywhere (decision #3).
4. **Never** log request bodies, tokens, or the proxy's full error payload; the notify
   line carries provider/model/reason only.
5. **Tests.** A unit test runnable with `node --test` or the repo's existing TS test
   pattern (check `tests/unit/test_pi_route.mjs` for how pi-side code is tested here):
   stub `/_route` responses for (codex routable → switch), (none routable → single
   error line), (recovery on two polls → switch back), (one poll only → no switch
   back), (`/failover off` → no switch). Existing tests green.
6. **Wire it in** the same way the other `config/pi/extensions/*.ts` are wired (see
   Context 4) and verify with a real pi session: `pi -e config/pi/extensions/llm-failover.ts
   -p "say hi"` (or the loader path you found) with the proxy running. Today the
   anthropic pool has one routable account, so the switch will not fire live — test
   the trigger by temporarily pointing `PI_ANTHROPIC_PROXY_URL` at a tiny local stub
   that returns the proxy's unavailable error and a canned `/_route`; document the
   command in your report.

## Scope fence

- **You own:** `config/pi/extensions/llm-failover.ts`, its test file, and — only if
  the loader path requires it — the one line that registers the extension
  (`bin/pi-claude-sub` or wherever Context 4 leads; keep that diff minimal).
- **Do NOT touch:** `bin/claude-token-proxy`, `tests/unit/test_claude_token_proxy.py`,
  `scripts/llm_usage.py`, `config/llm-proxy/routes.json`, `~/.pi/agent/*`.
- Sibling running now: **Step 3** on `llm-proxy/step3-deepseek-passthrough` owning the
  proxy. If `/_route` lacks something you need, note it in your report; do not edit
  the proxy.

## Constraints

- `CLAUDE.md`/`README.md` first. Commit hook: `type(scope): subject`, lowercase,
  imperative, ≤50 chars; blocks company names / secret-looking strings.
- TypeScript style of the existing extensions (tabs, `import type { ExtensionAPI }`).
- Gates, by name:
  ```bash
  <your node --test command>
  make test-unit
  pi -e config/pi/extensions/llm-failover.ts -p "reply with OK"     # loads without error
  ```
- Git: `GIT_EDITOR=true`; rebase on `origin/master`, linear, `git push origin HEAD:master`.
- Scratch under `$(pi-scratch dir llm-step4)`, never `/tmp`.

## Where to record findings

Commit body + "Step 4 — done" note in `docs/handover/llm-proxy-implementation.md`
(sha, gates by name, the exact hooks used with pi version, the stub command for the
live trigger test). Raw output to
`$NOTES/<project>/driver/agent-runs/2026-09-25/<HHMM>_llm-step4-output.md`
(`$NOTES=/home/gud1/sync/Vault`) with front-matter `model`, `cost_usd`, `branch`, `landed_in`.

## When done or blocked — report back to the parent

```bash
tmux send-keys -t "$PI_PARENT_PANE" -l "STEP4 DONE <sha> — <one line: what landed, gates run, open items>"; tmux send-keys -t "$PI_PARENT_PANE" Enter
```
If `PI_PARENT_PANE` is unset, the parent pane id is `%1520` (verify with `tmux list-panes -a -F '#{pane_id} #{pane_current_command}'`).
Then stay idle.

## Cost guidance

Target ~$10. Stop at $18 with what you have committed and reported.
