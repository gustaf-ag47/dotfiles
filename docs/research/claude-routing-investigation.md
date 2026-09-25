# Claude subscription routing investigation — 2026-09-10

Investigation driven through `tmux send-keys` in window `claude-routing-debug` (pane `%845`). Initial investigation made no service or code changes; the subsequently requested fix is recorded below.

## Finding

Routing to the token **labelled** `gs@gustafsilver.se` works. Both default Opus 4.8 and explicit Opus 5 minimal pi requests returned `ROUTING_OK`; proxy logs recorded HTTP 200 on fingerprint `82a293204226` at 10:05:50 and 10:06:54 UTC. Labels come from comments in `~/cctoken`, not verified account identity from Anthropic.

Recent logs show intermittent HTTP 429 on the same token, followed by attempted failover to the other two exhausted accounts and a final no-token-pickable error. This is not simply pi bypassing the proxy.

## Account snapshot

| Label | Shared weekly used | Five-hour used | Fable/overage weekly used | State |
|---|---:|---:|---:|---|
| work-account | 100% | 0% | 101% | Cooling until Sep 12, 02:00 UTC (approximately) |
| gs@gustafsilver.se | 64% | 72% | 100% | Available between 429s |
| antropic@gustafsilver.se | 100% | 0% | 1% | Cooling until Sep 13, 10:00 UTC (approximately) |

These are retained response-header observations, not complete live quota readings. All three tokens receive HTTP 403 from the detailed usage endpoint because they lack `user:profile`; this does **not** mean inference authentication is invalid.

## Confirmed proxy defect

`bin/claude-token-proxy:722`: `pick()` initially excludes tokens in cooldown, but its final fallback ignores `cooldown_until` and selects one anyway. A synthetic test against the actual function with one valid token cooling for another 60 seconds selected that token:

```text
Cooldown regression: FAIL: pick() selected an account with 60s cooldown remaining
```

This explains attempts against the two accounts whose reset times are days away. It also defeats backoff on the remaining account once all tokens are cooling. The startup guard in `bin/pi-claude-sub:76` counts only genuinely available tokens, so startup and request-time selection apply inconsistent policies.

A direct one-output-token Opus 4.8 request with the gs-labelled credential also returned:

```text
HTTP 429
Rate-limit headers: {}
Error: {'type': 'rate_limit_error', 'message': 'Error'}
429 classification: burst; burst pause: None
```

With no Retry-After or quota headers, `classify_429()` defaults to burst, but `burst_pause_seconds()` refuses to wait; the handler applies a default 60-second cooldown and fails over. The fallback can immediately bypass that cooldown.

The opaque upstream response does not establish whether the original 429 is a per-minute rate limit, a model-specific restriction, or another upstream limit. Adjacent successful requests and remaining shared quota make a temporary limit plausible, but not proven. Historical logs omit model and 429 response details, preventing a definitive classification of earlier failures.

## Roles of the three tools

- `bin/pi-claude-sub`: loads identity and proxy extensions, supplies placeholder auth, and selects Opus 4.8 by default. Does not pin an email address.
- `config/pi/anthropic-token-proxy.ts`: redirects Anthropic requests to localhost:8788.
- `bin/claude-token-proxy`: replaces Authorization with its selected token. Default selection is reset-time-weighted headroom with stickiness, not necessarily the lowest utilization (some comments are outdated).
- `bin/claude-usage`: prints the tooltip from `bin/waybar-claude-usage`; reporting only, no routing changes. Header-based quota cannot explain every 429. Its re-authentication recommendation concerns detailed reporting, not the demonstrated inference failures.

## Reproduction

Successful end-to-end probe (small real subscription usage):

```bash
pi-claude-sub --no-session --no-tools --no-skills --no-context-files \
  --no-extensions --thinking off -p 'Reply exactly ROUTING_OK'
```

Repeat with `--model claude-opus-5` for the second successful probe. Explicit wrapper `-e` extensions still load with extension discovery disabled.

## Fix applied and verified

Removed the cooldown-bypassing fallback from `pick()`. Tokens whose upstream cooldown has not expired now remain ineligible in both pressure and legacy headroom modes. If none remain, the existing handler returns HTTP 503 with account cooldown details. Over-threshold observations remain a ranking preference, not a permanent ban.

Added regression coverage for all accounts cooling, exact cooldown expiry, exclusion plus cooldown, over-threshold eligibility, and the real handler's opaque-429 failover path. Before the fix, the suite reported four failures, including two upstream calls instead of one. After the fix, all 28 tests pass. `git diff --check` passes.

Restarted the user service through the investigation tmux window. The live status endpoint showed gs available and both exhausted accounts cooling. The original pi probe returned `ROUTING_OK`, exit 0, with HTTP 200 on the gs-labelled token at 10:12:39 UTC.

No credential changes. The upstream origin of intermittent 429s is still not established; this fix prevents the confirmed cooldown bypass rather than promising to eliminate upstream rate limits.

## Follow-up: model-scoped cooldown fix (12:19 CEST)

The user's actual left-pane session started on Fable 5. A Fable retry at 10:14:36 UTC created an account-global cooldown until September 16; switching to Opus at 10:15 did not escape it. The initial Opus-only probe missed this sequence.

Added model-scoped cooldowns based on explicitly identified upstream quota claims (Fable included-overage, Opus, Sonnet). Shared/unknown/burst limits remain account-wide. Selection combines the shared deadline with the requested model family's deadline; successful traffic must not clear another model's cooldown. Seed probes use the same cooldown assignment. Status exposes `model_cooldowns` and `available_by_model`; `claude-usage` displays the scoped deadlines.

Regression coverage now includes the actual handler's Fable-429 → Opus-200 sequence, cooldown expiry, preservation across other-model success, shared/unknown/burst classification, per-bucket rejection, and snapshot reporting. All **34 tests pass**, along with shell syntax and diff checks.

Restarted the proxy at 10:19:49 UTC. Live sequence:

- 10:19:51: gs, `claude-fable-5`, HTTP 429, `cooldown_scope=fable`.
- 10:20:07: same gs token, `claude-opus-5`, HTTP 200; probe printed `ROUTING_OK`.
- Status: Fable availability 0; Opus/Sonnet/Haiku availability 1. gs has no shared cooldown, with only its Fable deadline retained until September 16.

The existing Pi session can retry on Opus without restarting. Fable is still unavailable in the current pool. No credentials were changed or quota limits bypassed.

## Recommended next changes (remaining beyond the cooldown fixes)

1. Regression-test and remove selection of still-cooling tokens; return a retryable error with earliest eligible retry time instead.
2. Implement bounded backoff for opaque 429s, without probing weekly-exhausted accounts or prematurely invalidating credentials.
3. Log model, 429 classification, sanitized error type, and Retry-After; never tokens, prompts, or auth headers.
4. Make cooldown model/bucket-aware where upstream evidence supports it; currently it is account-global despite model-aware weekly scoring.
5. Clarify reporting freshness and distinguish reporting-scope errors from inference failures.

Do not promise an upstream-429 fix from the cooldown change alone. It fixes the confirmed retry defect; the original limit still needs sanitized instrumentation during a failing workload.
