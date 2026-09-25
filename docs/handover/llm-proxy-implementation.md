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
