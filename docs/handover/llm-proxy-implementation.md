# LLM proxy — implementation plan (option c)

Decisions: `docs/research/generic-llm-proxy.md` §"Operator decisions" and
`docs/research/openai-deepseek-account-introspection.md`. Date: 2026-09-25.

Ordered so every step ships value on its own and nothing routes until step 4.

## Step 1 — richer read side (no behaviour change)

`scripts/llm_usage.py` + `tests/unit/test_llm_usage.py`.

- openai-codex: decode the access-token JWT locally (`email`, `name`,
  `chatgpt_plan_type`); keep `wham/usage` fields `email`, `plan_type`, `model_usage`
  (per-model `available_at`, `credits_would_enable`), `credits.balance`,
  `rate_limit_reached_type`, `rate_limit_upsell`. Render account line as
  `<email> (<plan>)` + verdict, per-model rows, and "credits would unlock X".
  Undocumented endpoint: any unknown shape → `unavailable`, never 0 %.
- deepseek: label = `DEEPSEEK_ACCOUNT_LABEL` → `auth.json` `label` → `…<last4>`.
  Verify by reading pi source whether `auth.json` rewrites preserve unknown fields;
  record the answer in the introspection doc. Render top-up URL when
  `is_available` is false.
- Fixtures: the ten listed in the introspection doc §5 (redacted real responses).

### Step 1 — done (2026-09-25, commit `bbff6a3`)

- `scripts/llm_usage.py`: `jwt_claims()` (local base64url decode), `codex()` returns
  `account{email,name,plan,account_id[:6]}`, `windows` (+`additional_rate_limits` by
  `limit_name`), `allowed`, `limit_reached`, `reached_type`, `upsell` (title only),
  `models{slug:{available,available_at,credits_would_enable}}`, `credits{balance,
  has_credits,unlimited,overage_limit_reached}`, `reset_credits`, `topup_url`.
  `deepseek()` returns `label`, `label_source` (`env|auth.json|key`), `topup_url`.
  Render split per provider (`anthropic_lines` unchanged in output, `codex_lines`,
  `deepseek_lines`). `codex()`/`deepseek()` are stdlib-only, no module state —
  Step 2 can copy them verbatim (they depend on `get_json`, `numeric`, `boolean`,
  `text`, `jwt_claims`, `quota_window`, `deepseek_key`, `deepseek_label` and the two
  `*_TOPUP_URL` constants).
- Open question #3 answered in the introspection doc: pi 0.87.1 merges `auth.json`
  per provider (`auth-storage.js:389`), so `deepseek.label` survives OAuth refreshes;
  only `/login deepseek` replaces it.
- Verified by name: `python3 -m unittest tests.unit.test_llm_usage -v` (22 ok),
  `make test-unit` (46 ok), `bin/llm-usage --refresh` (live: codex
  `gs@… (pro)  LIMIT REACHED`, astra row, top-up line; deepseek `key …<last4>
  EXHAUSTED`, −0.12 USD, top-up URL, label hint), `bin/llm-usage --refresh --json`.
- Not verified: the Codex top-up URL (`chatgpt.com/codex/settings/usage`) and
  `platform.deepseek.com/top_up` are still hard-coded and unclicked (open questions
  #2 and #4). `additional_rate_limits` rendering is fixture-only (live value `null`).
- Side effect: `bin/llm-usage` and `tests/unit/test_llm_usage.py` were untracked in
  the main checkout; this commit tracks them.

## Step 2 — proxy becomes the quota oracle

`bin/claude-token-proxy` + `tests/unit/test_claude_token_proxy.py`.

- Move the codex/deepseek adapters into the proxy (or import `llm_usage.py`; decide
  by keeping the proxy stdlib-only and single-file — copy, do not import).
  `/_usage` gains `providers: {anthropic, openai-codex, deepseek}` with the same
  shapes `llm_usage.py` renders today, cached 60 s, refreshed on the existing
  `USAGE_INTERVAL` thread. Reader then has ONE source.
- `config/llm-proxy/routes.json` — the equivalence table (decision 5). Tracked.
- `GET /_route?model=<claude-model>` — pure: returns
  `[{provider, model, routable, reason, quota_left, reset_at}]` ranked
  Codex → DeepSeek per the table; Anthropic pool first via `routing_preview()`.
  Never mutates state.

### Step 2 — done (2026-09-25, commit `5066d32`)

- `config/llm-proxy/routes.json` (decision 5, tracked). `route_key()` matches exact →
  longest row prefixing the model (`claude-opus-5-5-20260901`) → nearest row the model
  prefixes (`claude-fable-5` → `claude-fable-5-1`). Re-read on mtime change; a bad file
  keeps the last good table and sets `routes_error`. `CC_PROXY_ROUTES` overrides the path,
  which is otherwise resolved through the `~/.local/bin` symlink to `$DOTFILES/config/…`.
- `/_usage` is schema 2: `tokens`/`routing` unchanged, plus
  `providers.{anthropic,openai-codex,deepseek}`. `anthropic` = `{status, kind, tokens,
  routing, checked_at}`; the other two are the `codex()`/`deepseek()` dicts copied into
  the proxy, polled on the watcher every `USAGE_INTERVAL` (first poll off-thread at
  startup so listening is not delayed), cached in `PROVIDER_STATE`, `checked_at` per
  provider, any failure → `{status: unavailable, reason}` (HTTP code or exception class
  only — never a body or message).
- `GET /_route?model=` → `{model, route, candidates[], first_routable, generated_at}`.
  Anthropic candidate comes from `rank_pool(model)` (the `routing_preview()` dry run,
  refactored to take the real model so per-scope cooldowns count; never touches
  `LAST_PICK`), reasons `cooldown|exhausted|no token`. Codex: `exhausted` (window ≥
  100 % or `allowed:false`), `model unavailable` (per `model_usage`, `reset_at` =
  `available_at`), else routable; DeepSeek: `unavailable` (`is_available:false`),
  `balance below floor` (`CC_PROXY_DEEPSEEK_MIN_BALANCE`, default 1.0), else routable.
  Unpolled/failed provider → `reason: "unknown"`. Unknown model → 404 JSON listing the
  known rows. `POST`/`PUT` on any `/_*` path → 405; local endpoints are never forwarded.
- Labels (decision 6): Codex `account{email,plan}` from JWT claims (live `wham/usage`
  values win); DeepSeek `DEEPSEEK_ACCOUNT_LABEL` → `auth.json.label` → `key …last4`.
- Verified by name: `python3 -m unittest tests.unit.test_claude_token_proxy -v` (42 ok:
  24 existing + 18 new), `make test-unit` (42 ok in the worktree; 68 on master with
  Step 1's suite), `systemctl --user restart claude-token-proxy.service && curl
  …/_route?model=claude-opus-5-5` (live, redacted below), `llm-usage --refresh` (renders
  unchanged; the reader still uses its own adapters — switching it to `providers.*` is a
  later step). Live `/_usage` + `/_route` bodies were grepped against every token in
  `~/cctoken` and `auth.json`: clean.

  ```json
  {"model": "claude-opus-5-5", "route": "claude-opus-5-5", "candidates": [
    {"provider": "anthropic", "model": "claude-opus-5-5", "routable": true, "reason": null,
     "quota_left_percent": 12.0, "reset_at": "2026-09-30T06:00:00+00:00", "account": "82a2…"},
    {"provider": "openai-codex", "model": "gpt-6-luna", "routable": false, "reason": "exhausted",
     "quota_left_percent": 0.0, "reset_at": "2026-09-30T14:38:22+00:00", "checked_at": 1790325858},
    {"provider": "deepseek", "model": "deepseek-v4-pro", "routable": false, "reason": "unavailable",
     "balance": -0.12, "currency": "USD", "min_balance": 1.0, "checked_at": 1790325859}],
   "first_routable": {"provider": "anthropic", …}}
  ```

- Open items:
  - The adapters were copied before Step 1 landed. Field names agree, but Step 1's
    final `codex()` also returns `account.name`, `account.account_id[:6]`, `upsell`,
    `reset_credits`, `topup_url` and `additional_rate_limits` windows, and `deepseek()`
    returns `label_source` and `topup_url`. Sync the proxy copies (small diff) before the
    reader switches to `providers.*` as its single source.
  - Codex routability ignores `credits` (a Pro account at 100 % with credits could still
    serve); revisit with Step 4 if "running on credits" should count as routable.
  - Anthropic `reset_at` when nothing is routable is the earliest of cooldown deadlines
    and over-threshold bucket resets — good enough for "next reset X", not per-account.
  - The main `master` checkout had ~150 lines of uncommitted extra tests in
    `tests/unit/test_claude_token_proxy.py` (pick-policy/opaque-429 cases); they were
    stashed around the fast-forward and restored, still uncommitted, still green.

## Step 3 — DeepSeek Anthropic-passthrough for non-pi clients (decision 4)

`bin/claude-token-proxy`.

- Off by default; `CC_PROXY_DEEPSEEK_FALLBACK=1` enables; `CC_PROXY_DEEPSEEK_MIN_BALANCE`
  (default `1.0`) floor read from the cached `/user/balance`.
- Fires only when `pick()` returns None (hard unavailability), never on pressure.
- Upstream `api.deepseek.com/anthropic`, `x-api-key` from the DeepSeek credential,
  model rewritten per `routes.json`, request body otherwise untouched. Strip
  `anthropic-beta`/`cache_control`? — test against the live endpoint and record which
  fields DeepSeek rejects.
- Log line + `routing.fallback = {provider, model, since}` in `/_usage`; `llm-usage`
  renders `Claude Code → deepseek-v4-pro (anthropic pool exhausted until …)`.
- Tests: unit with a fake upstream; one manual live check before enabling.

### Step 3 — done (2026-09-25, commit `04d864e`)

- `bin/claude-token-proxy`: `CC_PROXY_DEEPSEEK_FALLBACK=1` (default `0`) enables
  `Handler._deepseek_fallback()`, reached only when `pick()` returns `None` in the
  request loop. `fallback_target()` gates on the `deepseek` entry of `routes.json`
  (`route_key()` prefix match), a resolvable DeepSeek key (`deepseek_key()`, same as
  the poller) and `deepseek_candidate()` being routable on the *cached* balance
  (`CC_PROXY_DEEPSEEK_MIN_BALANCE`, default 1.0, reused from Step 2; `is_available`
  false → not routable). `deepseek_upstream()` forwards the same method/body/query to
  `api.deepseek.com` with `/anthropic` prefixed to the path, `x-api-key` set, and
  `Authorization`/`x-api-key`/`Host` dropped; `rewrite_model()` only replaces `model`.
  Whatever DeepSeek returns (402 included) streams back as-is through the existing
  `_stream()` path — no Anthropic retry. A DeepSeek network error is a 502 with the
  unavailable message appended.
- Surfacing: log line `POST /v1/messages -> deepseek <model> (fallback: anthropic pool
  exhausted) model=<claude-model>`; `/_usage` `routing.fallback =
  {provider, model, for_model, since, requests, reason}` during an episode, `null`
  otherwise (the episode ends when a real token is picked, or when `/_usage` sees
  `rank_pool()` would pick one); `routing.deepseek_fallback = {enabled, min_balance,
  requests_total, by_model}` always; `/_route` deepseek candidate gains
  `proxy_passthrough`. Counters persist under `_deepseek_fallback` in `usage.json`
  (token rows unchanged; the fallback is never attributed to an OAuth account).
- What DeepSeek rejects (probed live with the negative-balance key, 2026-09-25): the
  bare `/v1/messages` path is a **404** — the `/anthropic` prefix is mandatory (the
  brief's "path unchanged" was wrong on that point). `anthropic-beta` (the full
  Claude Code OAuth list), `anthropic-version`, `x-app`,
  `anthropic-dangerous-direct-browser-access`, `user-agent: claude-cli/*` and a
  `?beta=true` query are all accepted up to the billing gate (402, not 400); the docs
  list `anthropic-beta`/`anthropic-version`/`cache_control` as ignored and `thinking`
  as supported (`budget_tokens` ignored), so nothing but `Authorization` is
  stripped. The 402 body is OpenAI-shaped (`{"error":{"message":"Insufficient
  Balance …","type":"unknown_error"}}`, no top-level `type: "error"`); it is relayed
  verbatim.
- Verified by name: `python3 -m unittest tests.unit.test_claude_token_proxy -v`
  (61 ok, 9 new in `DeepseekPassthroughTests` — feature off, forward with rewritten
  model + `x-api-key` and no bearer, SSE relay + counting, balance below floor /
  unavailable / unpolled, no deepseek route, healthy pool never fires, 402 as-is
  without Anthropic retry, episode clears, counters survive restart), `make test-unit`
  (83 ok), `systemctl --user restart claude-token-proxy.service && sleep 6 &&
  llm-usage --refresh` (feature off in the unit; unchanged behaviour).
- **Live check pending a top-up.** Balance was still −0.12 USD, so the forward was
  exercised only on a scratch instance (port 8799, all tokens forced down,
  `CC_PROXY_DEEPSEEK_FALLBACK=1`): the gate correctly refused (`deepseek fallback
  not taken for claude-sonnet-5: deepseek unavailable`) and the client got the
  unchanged 503. The wire path itself was proven with a direct 402 probe, not via the
  proxy. Nothing was topped up; the feature is not enabled in the service.
- Note for Step 4: with the passthrough on, a pi request during an exhaustion episode
  is also served by DeepSeek *before* pi's extension sees an "unavailable" error, so
  pi would show the Claude model id while DeepSeek answers. The extension can detect
  this from `/_usage` `routing.fallback` or `/_route` `proxy_passthrough`; nothing in
  `/_route` had to change for Step 4.

## Step 4 — pi extension: notify-only failover (decisions 2, 3)

New pi extension under `config/pi/extensions/` (check `docs/research/pi-unified-providers-and-dotfiles.md`
for where extensions live in this repo).

- On `after_provider_response` with an Anthropic-pool "unavailable" error (the proxy's
  error type), ask `GET /_route?model=<current>`; take the first `routable` entry; call
  `pi.setModel()`; print one line in the session:
  `↪ switched to <provider>/<model>: anthropic pool exhausted until <reset>`.
- Remember the original model; on each subsequent turn poll `/_route` (cheap, cached)
  and switch back with the mirror message when the pool recovers.
- No confirmation prompt (notify-only). No deny-list (none requested).
- Test: drive the extension against a stub proxy in `tests/unit/`.

### Step 4 — done (2026-09-25, commit `d7d9e32`)

- `config/pi/extensions/llm-failover.ts` (pi 0.87.1). Hooks actually used, after
  reading `dist/core/extensions/types.d.ts` and `pi-ai/dist/api/anthropic-messages.js`:
  - **Trigger is `turn_end`, not `after_provider_response`.** The Anthropic SDK throws
    on a non-2xx before pi calls `onResponse`, so `after_provider_response` (status +
    headers only) never fires for the proxy's 503. The error is only visible as
    `message.errorMessage` = `503 {"type":"error","error":{"type":"overloaded_error",
    "message":"Claude subscription request unavailable: no OAuth account can serve …"}}`.
    Match is the substring `no OAuth account can serve` (`isPoolExhausted()`), never a
    generic 5xx. `agent_end` is a backstop with a `WeakSet` dedupe on the message.
  - `pi.setModel(model: Model)` takes a catalog object, not `(provider, id)`; resolved
    via `ctx.modelRegistry.find(provider, id)`. A `false` return (no auth) falls through
    to the next routable candidate. pi's own auto-retry (3 attempts, 2 s backoff) then
    re-sends on the new model because `prepareRequest` reads `agent.state.model`.
  - `turn_start` polls `/_route?model=<original>` at most every 60 s while switched;
    switch back only after two consecutive routable polls ≥ 60 s apart.
  - `model_select` (source ≠ ours) = manual pick → tracking stops.
  - `/failover status|on|off`. Notify via `ctx.ui.notify` when `ctx.hasUI`,
    `console.log` in print mode, `console.error` otherwise. Lines carry
    provider/model/reason only; the proxy payload is never printed.
  - `/_route` fetch: loopback origin from `PI_ANTHROPIC_PROXY_URL` / `CC_PROXY_PORT`,
    3 s `AbortController` timeout, any failure → treated as "oracle unreachable".
- Loader: `scripts/pi_setup.py` (still untracked in the main checkout) links
  `config/pi/extensions/*` → `~/.pi/agent/extensions/`. Until that lands,
  `bin/pi-claude-sub` passes `-e config/pi/extensions/llm-failover.ts`, guarded by
  `[ ! -e ~/.pi/agent/extensions/llm-failover.ts ]` so it never loads twice.
- Tests: `tests/unit/test_llm_failover.mjs` (10 cases: trigger match, codex → switch,
  setModel fallthrough, none routable → one line + no repeat, two-poll recovery,
  one-poll/flap → no switch back, `/failover off`, non-anthropic ignored + manual pick,
  `fetchRoute` timeout/bad answers, origin parsing).
- Verified by name: `node --test --experimental-strip-types tests/unit/test_llm_failover.mjs`
  (10 ok), `make test-unit` (74 ok), `pi -e config/pi/extensions/llm-failover.ts -p
  "reply with OK"` (loads; plain pi then 400s on direct Anthropic as expected),
  `bin/pi-claude-sub --model anthropic/claude-haiku-4-5 -p "/failover status"` (live
  ranking from `:8788`). Live trigger against a stub (scratch
  `pi-scratch/llm-step4/stub-proxy.py`: `/_status`, 503 on `POST /v1/messages` with the
  real `unavailable_message()` text, canned `/_route`):
  ```bash
  STUB_PORT=8799 python3 "$(pi-scratch dir llm-step4)/stub-proxy.py" &
  DOTFILES=$PWD PI_ANTHROPIC_PROXY_URL=http://127.0.0.1:8799 PI_CLAUDE_SUB_PROXY=1 \
    bin/pi-claude-sub -e config/pi/extensions/llm-failover.ts \
    --model anthropic/claude-haiku-4-5 -p "reply with exactly: OK"
  # → "↪ switched to openai-codex/gpt-6-luna: anthropic pool exhausted (next reset in 117h 07m)"
  #   then pi retried on Codex (really exhausted today → "Codex error: The usage limit has been reached")
  STUB_CODEX=0 … # → one "✗ no provider routable — anthropic exhausted, codex exhausted,
                 #   deepseek unavailable" across pi's 4 attempts, 503 propagated
  ```
- Not verified live: switch-back (needs a real exhaustion + recovery; unit-tested only)
  and the `↪` line inside the TUI (print mode only). Not changed: `bin/claude-token-proxy`,
  `~/.pi/agent/*`. `/_route` had everything needed; nothing to ask of Step 3.

## Step 5 — done (2026-09-25, commits `a5f0a41`, `cc3a583`)

**Verdict on `scripts/pi_setup.py`: replaced with a small symlink step.** Ground truth:
`origin/research/wire-pi-into-dotfiles` == `origin/master` (no commits of its own); the
wire-pi work exists only as untracked/modified files in the master checkout. `pi_setup.py`
(186 lines) does much more than asked: links `@earendil-works/pi-ai` into
`config/pi/node_modules` and `~/.pi/agent/node_modules`, links *every* file under
`config/pi/{extensions,lib,skills}` plus `dotfiles-local/config/pi/skills`, seeds
`settings.json`/`models.json`, checks `upstreams.json`. The skills it would link have
diverged from `~/.pi/agent/skills/` (browse-shop, deepseek, delegate, ralph-loop,
web-research, website-screenshot all differ), and `anthropic-subscription.ts` is a
global Anthropic provider override that reroutes plain `pi`'s Anthropic calls through
the proxy — that changes how Anthropic sessions authenticate, i.e. decision #1 territory.
Its unit tests do run against temp dirs only (the "Installed 1 resources … Rollback"
lines in `make test-unit` are from `tempfile` paths, not `~/.pi/agent`).

- `a5f0a41` — `bin/pi-link-extensions`: explicit allowlist (`goal.ts`, `llm-usage.ts`,
  `llm-failover.ts`) symlinked from `config/pi/extensions/` into
  `$PI_CODING_AGENT_DIR/extensions/` (default `~/.pi/agent/extensions`). `--check`
  (exit 1 iff pending), `--remove`, prunes dangling links it owns, refuses to overwrite
  a diverged local copy (identical copies are replaced — the old `goal.ts` copy was
  byte-identical), never touches `auth/settings/models.json`. `scripts/install.sh` runs
  it when `pi` is on PATH. `config/pi/extensions/{goal,llm-usage}.ts` now tracked.
  `llm-usage.ts` resolves `bin/llm-usage` via `realpathSync(__filename)`, so links (not
  copies) are required.
- `cc3a583` — `bin/pi-claude-sub` Anthropic-only guard (from the uncommitted hunk, minus
  `PI_DOTFILES_LEGACY_CLAUDE_PID`, which only served the unlanded provider override) +
  `tests/unit/test_pi_claude_sub.py` (fake pi binary, proxy off).
- Gates by name: `make test-unit` → **93 ok** in the worktree; `python3 -m unittest
  tests.unit.test_pi_link_extensions tests.unit.test_pi_claude_sub` (5 + 3 ok);
  `bash -n` + shellcheck clean. Live after `bin/pi-link-extensions`:
  `pi --model gpt-6-luna --no-session -p "/usage"` → llm-usage table, rc 0, no
  extension error; `pi --no-session -p "/failover status"` → live ranking from `:8788`.
  ```
  ~/.pi/agent/extensions/goal.ts         -> $DOTFILES/config/pi/extensions/goal.ts
  ~/.pi/agent/extensions/llm-failover.ts -> $DOTFILES/config/pi/extensions/llm-failover.ts
  ~/.pi/agent/extensions/llm-usage.ts    -> $DOTFILES/config/pi/extensions/llm-usage.ts
  ```
- (B) `test_pi_provider_integration.py` (untracked, master checkout only): the failure is
  pi resolving `anthropic/claude-haiku-4-5` to openrouter under the provider override,
  not a missing key per se. Edited in place (still untracked) to
  `skipUnless(PI_PROVIDER_INTEGRATION=1)` with a named reason → master checkout
  `make test-unit` = 89 ok, 1 skipped.
- Stays untracked, on purpose: `scripts/pi_setup.py`, `bin/pi-setup`,
  `tests/unit/test_pi_setup.py`, `tests/unit/test_pi_provider_integration.py`,
  `tests/unit/test_pi_route.mjs`, `tests/e2e/pi-unified-tmux.py`,
  `config/pi/extensions/anthropic-subscription.ts`, `config/pi/lib/`, `config/pi/skills/`,
  `config/pi/{models,settings}.example.json`, `config/pi/upstreams.json`, and the
  `.gitignore`/`claude-usage`/`waybar-claude-usage`/`install.sh` wire-pi hunks. Landing
  the provider override / skills sync is a separate decision (decision #1) — if wanted,
  the natural next step is to reconcile `~/.pi/agent/skills` vs `config/pi/skills` and
  add the skills to `pi-link-extensions`' model, not to resurrect `pi_setup.py` wholesale.

## Verification gates (every step)

```bash
make test-unit
python3 -m unittest tests.unit.test_llm_usage tests.unit.test_claude_token_proxy
systemctl --user restart claude-token-proxy.service && llm-usage --refresh
```

## Not doing

- Wire-format translation Anthropic ⇄ OpenAI in the proxy (decision 2).
- Codex multi-account pooling (earlier operator decision).
- Reading DeepSeek's private dashboard API.
- Any identity cloaking beyond what exists today (decision 1).

## Orchestrator follow-up — done (2026-09-25)

- `ad02886` — pi opts out of the DeepSeek passthrough: `config/pi/anthropic-token-proxy.ts`
  sends `x-cc-proxy-fallback: none`; the proxy returns the normal unavailable error so
  `llm-failover.ts` switches natively (decision #3 stays notify-only). Claude Code keeps
  the passthrough. Test: `test_client_opt_out_header_keeps_the_unavailable_message`.
- next commit — proxy codex adapter at parity with `llm_usage.py`; `/_route` counts a
  Codex account on purchased credits as routable (`on_credits: true`) unless the model
  is blocked or `overage_limit_reached`. Test: `test_codex_credits_keep_it_routable_after_window_spent`.
- Gates: `python3 -m unittest tests.unit.test_claude_token_proxy` (64 ok), live
  `pi-claude-sub --model claude-haiku-4-5 -p` through the proxy → OK, `/_usage`
  `providers.openai-codex.account` carries email/name/plan, `llm-usage --refresh` renders.
- Pre-existing red, not from this work: untracked `tests/unit/test_pi_provider_integration.py`
  needs an OpenRouter key.

## Remaining manual items

1. Top up DeepSeek, then run Step 3's live check (`CC_PROXY_DEEPSEEK_FALLBACK=1` on a
   scratch port) and record the headers DeepSeek rejects.
2. Switch-back path of `llm-failover.ts` is live-untested (needs a real pool recovery).
3. ~~Auto-loading `config/pi/extensions/*.ts` for plain `pi`~~ — done in Step 5
   (`bin/pi-link-extensions`). In the master checkout `git pull` will conflict on
   `bin/pi-claude-sub` and `scripts/install.sh` (uncommitted wire-pi hunks); take the
   committed side, the guard is already landed.
4. Verify the two top-up URLs (Codex, DeepSeek) once each is used for real.
