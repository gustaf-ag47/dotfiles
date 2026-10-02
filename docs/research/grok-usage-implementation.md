# Grok (`grok-build`) quota in `llm-usage` and the proxy oracle

Status: implemented 2026-10-02 on branch `feat/grok-usage`, worktree
`/home/gustaf/.cache/grok-research/worktrees/usage`. Scope per
`docs/handover/implement-grok-usage.md`: `scripts/llm_usage.py`,
`bin/claude-token-proxy`, new tests. Does **not** touch `routes.json`,
`classes.json`, the Pi extension, or any shared/existing test file. Grok is not
added to automatic routing; it is read-only quota observation only.

## What this adds

- `scripts/llm_usage.py`: a `grok-build` adapter (`grok_build(auth)`), wired into
  `ADAPTERS`, `REPORT_SOURCES`, `normalize_provider`, and `RENDERERS`, so
  `llm-usage`, `llm-usage --json`, and `llm-usage --waybar` all show Grok Build CLI
  quota next to Anthropic/Codex/DeepSeek.
- `bin/claude-token-proxy`: the same adapter (duplicated, stdlib-only, per the
  file's existing "Copied from scripts/llm_usage.py" convention) registered in
  `PROVIDER_ADAPTERS`/`PROVIDER_SOURCES`/`PROVIDER_CONFIDENCE`/`PROVIDER_STATE`, so
  `GET /_usage` exposes `providers["grok-build"]` on the proxy's existing 5-minute
  poll cadence. **Not** added to `routes.json`, the route table, or any pick/ranking
  logic — it is observation-only, exactly like asked.
- `tests/unit/test_grok_usage.py`, `tests/unit/test_proxy_grok.py`: offline, mocked,
  no real credential file or network access (see "Test isolation" below).

## Credential source: Pi's `auth.json`, not `~/.grok/auth.json`

The adapter reads `auth["grok-build"]` from Pi's own `~/.pi/agent/auth.json` (the
file `scripts/llm_usage.py` already loads for every other adapter), shaped exactly
like the existing `openai-codex` credential: `{"type": "oauth", "access": <JWT>,
"expires": <ms-epoch>}`. Docs confirmation: `custom-provider.md` — "Pi stores
returned credentials in `~/.pi/agent/auth.json`" for any registered OAuth provider,
and the sibling task (`implement-grok-pi-auth.md`) registers Pi's own native OAuth
provider under the id `grok-build`.

This was a deliberate change from an earlier draft that read `~/.grok/auth.json`
directly (the file the official `grok` CLI and the community `demi` adapter use).
That draft was reverted after it broke the established test-isolation contract:
**every** existing adapter in this file is gated behind the single `auth` parameter,
and `tests/unit/test_claude_token_proxy.py::ProviderAdapterTests` mocks
`read_auth()`/`auth` to control what credentials a test run can see. A `~/.grok`-reading
adapter bypasses that seam entirely — verified live during this work: an *unrelated*,
already-existing proxy test (`test_failing_upstream_degrades_to_unavailable_without_leaking`)
started reading this very machine's real `~/.grok/auth.json` and printing a real email
address (`gs@gustafsilver.se`) into `refresh_providers()`'s log line, purely as a side
effect of `~/.grok` existing on the dev box — with zero intent from the test author.
Routing everything through Pi's `auth.json` instead restores full isolation: any test
that doesn't explicitly hand the adapter a `grok-build` credential gets a clean
`{"status": "unavailable", "reason": "Log in to grok-build in Pi."}`, matching Codex's
and DeepSeek's behavior, with no disk access outside the already-audited path.

Consequence: until Pi's native `grok-build` OAuth provider (sibling work) is merged
and a user has logged in via `/login`, this adapter reports `unavailable` — by
design, not a bug. It will start working the moment Pi writes a `grok-build` OAuth
credential into `auth.json`, with no further code change needed here.

## Endpoint: `cli-chat-proxy.grok.com`, confirmed live, unofficial

Per `docs/research/grok-oauth-pi-community.md`, Grok Build CLI quota is **not**
`api.x.ai` — it is `https://cli-chat-proxy.grok.com/v1`, the Grok Build CLI's own
private backend, reverse-engineered by the community `@demicodes/provider-grok-build`
package (`/home/gustaf/.cache/grok-research/demi/package/dist/index.mjs`,
`createGrokBuildQuota`/`mapGrokQuotaProbe`). This is not documented or sanctioned by
xAI; treat it as liable to change without notice, same caveat as that research file.

**Live-verified 2026-10-02** from this host, using the real `~/.grok/auth.json`
session (`grok login` already completed per `PROOF.md`), with the exact headers
proven live by the sibling's Pi integration (`X-XAI-Token-Auth: xai-grok-cli`,
`x-grok-client-identifier: pi`, `x-grok-client-version: 1.0.46`):

- `GET /v1/user?include=subscription` → HTTP 200. Confirmed fields used by this
  adapter: `email` (string), `subscriptionTier` (string or **null** — this account's
  tier was null, i.e. no active paid tier was observed).
- `GET /v1/billing?format=credits` → HTTP 200, but the **live schema diverges from
  the community adapter's assumptions**: this account's `config` had no
  `monthlyLimit`, `used`, or `creditUsagePercent` keys at all — only `currentPeriod`
  (`{type, start, end}`), `onDemandCap`/`onDemandUsed`/`prepaidBalance` (each
  `{"val": 0}`), `isUnifiedBillingUser`, `topUpMethod`, `billingPeriodStart/End`.
  "Actual live behavior outranks assumptions in old research" (per the handover) —
  the adapter was built to tolerate this: `grok_clamp_percent`/`grok_ratio_percent`
  both return `None` when their inputs are absent, so the window is reported with
  `used_percent: None` (explicitly unknown), never `0` or `100`. This exact
  redacted/sanitized shape is now a regression test,
  `test_live_observed_billing_schema_without_monthly_fields_is_unknown_not_zero` in
  `tests/unit/test_grok_usage.py`.

**Known gap, intentionally not implemented (budget):** `prepaidBalance`/
`onDemandUsed`/`onDemandCap` are real, meaningful fields this host's live response
actually returned, but they describe a different kind of quota (prepaid wallet /
on-demand overage) than the `monthlyLimit`/`used`/`creditUsagePercent` triplet the
adapter currently maps into the one `weekly`/`monthly` window. Wiring in a second,
correctly-labeled window for prepaid balance is future work — flagged here rather
than guessed at, since misrepresenting a balance as a usage percentage (or vice
versa) would violate "do not invent quota."

No token, raw `/user` or `/billing` response body, or any other account identifier
was logged, committed, or left on disk; the one-time live probe used `curl`-equivalent
Python directly against the real local `~/.grok/auth.json`, written its two response
bodies to temp files under this scratch dir, inspected them with a redaction pass
that blanks every string containing `@` or longer than 30 characters, and then
deleted both files immediately after. No inference call was made at any point.

## Report shape

`grok_build()` returns the same `{"status": "ok"|"unavailable", ...}` shape as the
other adapters:

```jsonc
{"status": "ok", "kind": "subscription quota",
 "account": {"email": "...", "plan": "SuperGrok" /* or null */},
 "windows": [{"name": "weekly" | "monthly" | "on_demand_cap",
              "used_percent": 42 /* or null if unknown */, "used": 42, "limit": 100,
              "unit": "credits", "resets_at": "2099-01-01T00:00:00Z"}],
 "note": "Grok Build CLI OAuth session via the unofficial cli-chat-proxy.grok.com backend ..."}
```

`normalize_provider('grok-build', ...)` projects this into the shared
`llm-usage.v1` report contract at `confidence: "low"` (explicitly lower than
Codex's `"medium"`, since this endpoint is reverse-engineered and has already been
observed to diverge from its only prior documentation). `used_percent: None` always
maps to `state: "unknown"` and `remaining_percent: None` — never a zero or a full
bar — consistent with every other provider in this file.

## Not done / explicitly out of scope here

- No change to `config/llm-proxy/routes.json`, `classes.json`, or any pick/ranking
  function. `grok-build` never becomes a routing candidate; it is read-only
  observation surfaced at `/_usage` only, per the handover's explicit instruction.
- No change to the Pi extension, `/login` flow, or OAuth refresh — that is the
  sibling's `implement-grok-pi-auth.md` work. This adapter only ever *reads*
  whatever credential that work resolves into `auth.json["grok-build"]`.
- Prepaid-balance / on-demand-overage windows (see "Known gap" above).
- Short-window `x-ratelimit-*` header observation (the demi adapter's
  `observeGrokRateLimitHeaders`) — Grok Build CLI responses aren't proxied through
  this codebase's inference path at all, so there is nowhere to observe those
  headers from; only the active `/user`+`/billing` probe applies here.

## Test commands (offline, isolated, no live credentials)

```sh
# This change's own tests
python3 -m unittest tests.unit.test_grok_usage -v
python3 -m unittest tests.unit.test_proxy_grok -v

# Full existing suite, to confirm no regression (run from repo root)
python3 -m unittest discover -s tests/unit -t tests/unit -v
```

All three passed clean at the time of writing (`Ran 203 tests ... OK (skipped=1)`
for the full suite; the skip is pre-existing and unrelated to this change).

Every test mocks `get_json`/`read_auth` and supplies an in-memory `auth` dict; none
read `~/.pi/agent/auth.json` or `~/.grok/auth.json`, make a network call, or write a
real cache file (`ProxyIsolationMixin` redirects `CONTROL_DIR`/`USAGE_STATE_FILE` to
a temp directory for the proxy-side tests).

## Manual verification once Pi's `grok-build` OAuth login exists

```sh
# After `/login` → grok-build in Pi has written a credential to auth.json:
llm-usage --provider grok-build
llm-usage --provider grok-build --json
curl -s http://127.0.0.1:8788/_usage | jq .providers.'"grok-build"'
```
