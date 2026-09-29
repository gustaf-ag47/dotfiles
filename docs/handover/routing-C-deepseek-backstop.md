# Brief C — DeepSeek as a working last-resort backstop

**Agent:** delegated pi sub-agent. **Branch:** `feat/routing-c-deepseek-backstop`
(worktree, off `feat/pi-wait-for-quota-reset`). **Parent:** tmux
the tmux window recorded by delegate.sh. **Date:** 2026-09-27.

## Context

DeepSeek is the third provider in `config/llm-proxy/routes.json` and the only one the
proxy can forward to without translation (Anthropic-compatible endpoint,
`https://api.deepseek.com/anthropic`; see `bin/claude-token-proxy` module docstring
"DeepSeek Anthropic-passthrough" and `docs/research/generic-llm-proxy.md` decision 4).
Status today (`llm-usage`, 2026-09-27):

```
deepseek
  key …30cf  EXHAUSTED
    balance -0.12 USD   UNAVAILABLE   (granted 0.00 · topped-up -0.12)
```

and in `/_usage`: `deepseek_fallback.enabled = false`. So the backstop is worth exactly
zero right now. Policy that stands: DeepSeek costs money, not a resetting window, so it
is **last** in every ranking and is never chosen on pressure (sibling A enforces that
in the oracle). Its job is to keep a session alive when every subscription window is
spent — for pi via the extension (native DeepSeek provider), for Claude Code via the
proxy passthrough.

Credential: `~/.pi/agent/auth.json` has a `deepseek` `api_key` entry (read-only; never
print it). Balance endpoint: `GET https://api.deepseek.com/user/balance`.
Topping up requires a human with a card: https://platform.deepseek.com/top_up — **you
cannot do it; the operator must.**

## Your job

1. **Wizard for the human step.** Using the `wizard` skill
   (`/home/gud1/.agents/skills/mattpocock/skills/engineering/wizard/SKILL.md`), write
   `scripts/deepseek-topup-wizard.sh`: walks the operator through topping up, then
   verifies with the balance endpoint (key from `auth.json`, never echoed) that
   `total_balance > CC_PROXY_DEEPSEEK_MIN_BALANCE` (default 1.0) and `is_available` is
   true, and prints the `llm-usage --provider deepseek --refresh` line. Recommend an
   amount in the wizard text based on real pricing: fetch current DeepSeek prices
   (`web-research` skill) and estimate cost of one heavy day of `deepseek-v4-pro` /
   `deepseek-flash` use at, say, 5 M input / 200 k output tokens; cite the source in the
   report.
2. **Passthrough readiness (proxy).** Verify the opt-in passthrough end to end **without
   spending money**: run a second proxy instance from your worktree
   (`CC_PROXY_PORT=8790 CC_PROXY_DEEPSEEK_FALLBACK=1`, `CCTOKEN_FILE=$HOME/cctoken`) with
   every OAuth fingerprint listed in `$XDG_CACHE_HOME/cc-proxy/force_cooldown` (mind:
   that control file is shared with the live service on 8788 — use a **separate
   `XDG_CACHE_HOME`** for your instance so the operator's proxy is not affected), send
   one Messages request and confirm the proxy *attempts* DeepSeek and returns
   DeepSeek's own error (402 / insufficient balance) unchanged, logged as a fallback
   request. Fix anything that is broken on that path. Decide and document whether
   `CC_PROXY_DEEPSEEK_FALLBACK=1` should be the default for the user's service
   (`systemctl --user cat claude-token-proxy.service` — where does its env come from?
   it is in the dotfiles repo somewhere under `config/`; find it) and, if yes, make
   the change in the repo but **do not enable it on the live service** — the parent
   decides after review.
3. **Extension side.** Confirm (read + existing tests) that `llm-failover.ts` will
   select `deepseek/deepseek-v4-pro` when `/_route` says only DeepSeek is routable, and
   that pi has the `deepseek` provider configured with that model id
   (`pi` model registry — check `~/.pi/agent/models.json` or the provider docs under
   `/home/gud1/.local/share/npm/lib/node_modules/@earendil-works/pi-coding-agent/docs/`).
   If the model ids in `routes.json` do not exist in pi's registry, fix `routes.json`
   (you own it) and say so.
4. **Tests.** Add to a **new file** `tests/unit/test_proxy_deepseek_backstop.py` (sibling
   B owns `test_claude_token_proxy.py`); the existing `DeepseekPassthroughTests` there
   stay as they are. Cover any code change you make.
5. **Report** at `docs/handover/routing-C-deepseek-backstop-report.md`, including the
   exact command the operator runs (`bash scripts/deepseek-topup-wizard.sh`).

Done = wizard runs (dry path) and is `bash -n`/shellcheck-clean, passthrough path
proven with logs, gates green, report pushed, parent handshake sent.

## Scope fence

- **You own:** `scripts/deepseek-topup-wizard.sh`; in `bin/claude-token-proxy` only
  `fallback_target()`, `rewrite_model()`, `deepseek_upstream()`, `deepseek_candidate()`,
  `_deepseek_fallback()`, `deepseek_key()`/`deepseek_state` polling; `config/llm-proxy/
  routes.json` (deepseek entries only); the service unit/env file for the proxy (change
  in repo only); `tests/unit/test_proxy_deepseek_backstop.py`; your report.
- **Do NOT touch:** `pick()`/`rank_pool()`/`pressure()` (sibling **B**);
  `codex_candidate()`, `anthropic_candidate()`, `route_payload()`, `/_route`,
  `config/pi/extensions/llm-failover.ts` (sibling **A**); `/_usage` builder and
  `scripts/llm_usage.py` (sibling **D**); `tests/unit/test_claude_token_proxy.py`,
  `tests/unit/test_llm_usage.py`, `tests/unit/test_llm_failover.mjs`.
- **Never** touch the live service on port 8788, its `usage.json`, or the shared
  `force_cooldown` file. Never spend DeepSeek money (there is none anyway).
- Siblings in parallel: A (`feat/routing-a-cross-provider`), B (`feat/routing-b-affinity-5h`),
  D (`feat/routing-d-observability`).

## Constraints

- Read `CLAUDE.md` fully. Shell scripts: `#!/bin/bash`, `set -euo pipefail`, pass
  `bash -n` and `shellcheck` (the pre-commit hook runs both). Python stdlib only.
- Gates (report **by name**):
  ```bash
  bash -n scripts/deepseek-topup-wizard.sh && shellcheck scripts/deepseek-topup-wizard.sh
  python3 -m unittest tests.unit.test_claude_token_proxy tests.unit.test_proxy_deepseek_backstop
  make test-unit
  ```
- Conventional commits; `GIT_EDITOR=true` for rebase/merge continuation. **Parent owns
  merges** — push your branch only.
- Scratch: `scratch="$(pi-scratch dir routing-c)"`, never `/tmp`. Use it for your
  instance's `XDG_CACHE_HOME`.

## Where to record findings

`docs/handover/routing-C-deepseek-backstop-report.md`: pricing + recommended top-up with
source, passthrough evidence (redacted log lines), the default-on decision and
reasoning, gates by name, anything out of scope.

## When blocked

Record it, leave the branch reviewable, push, handshake as blocked.

## Parent handshake (mandatory — do not just go idle)

When done **or** blocked, after pushing, print exactly one final message in this shape and
then wait for the parent's reply (stay in the session; do not exit):

```
PARENT: task C <done|blocked>. branch feat/routing-c-deepseek-backstop @ <sha>.
gates: <name: pass/fail …>. report: docs/handover/routing-C-deepseek-backstop-report.md.
Human step required: <yes/no — what>. Awaiting review — reply with further instructions or "retire".
```

## Cost guidance

Target ≤ ~$8. If exceeded without a green gate, write up and handshake as blocked.
