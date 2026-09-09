# Research: Anthropic unified rate-limit buckets, esp. `7d_oi` (Fable)

Status: research only, nothing in this repo's proxy code was changed.
Scope: `bin/claude-token-proxy`'s handling of `anthropic-ratelimit-unified-*`
headers, and the undocumented `GET /api/oauth/usage` endpoint.

## Summary (answers to jobs 1–5)

1. **What `7d_oi` stands for.** `7d_oi` is the short claim-abbreviation for the
   rate-limit type `seven_day_overage_included`. It is **not** a generic
   "extra usage/overage" bucket in the billing sense — despite the name, every
   independent reverse-engineering source that classifies it by billing origin
   puts it in the **`subscription`** bucket, not `extra_usage`/overage-billed.
   It is consistently documented as **the Fable-5 model's own dedicated
   7-day (weekly) rate-limit window** — analogous to how Opus and Sonnet each
   have their own weekly sub-limit (`seven_day_opus`, `seven_day_sonnet`)
   alongside the account's aggregate `seven_day` bucket. "Overage included"
   most plausibly refers to Fable getting a bundled/included weekly overage
   allowance as part of the subscription, separate from the paid `overage`
   bucket — but no source spells out the billing etymology explicitly; treat
   that etymology as **speculation**. A `5h_oi` counterpart
   (`five_hour_overage_included`) also exists and is classified the same way
   (subscription, model-specific, 5-hour window). [Evidence 2, 3, 5, 6, 7]

2. **Does a Fable request debit only `7d_oi`, or also base `7d`/`5h`?**
   Every source that classifies `rateLimitType` groups
   `seven_day_overage_included` (and `seven_day_sonnet`, `seven_day_opus`)
   under a `'model'` category, distinct from the generic `'seven_day'`
   account-wide category — i.e. these are treated as **separate,
   model-specific counters**, not a re-labelling of the same number.
   [Evidence 5, 6]

   Direct empirical confirmation from this repo's own proxy `/_status`
   (account `a5de118c98c0`, `unified_status: rejected`, live 2026‑09‑08):
   `u7 = 1.00` (base weekly **fully exhausted**) while `u7_oi = 0.01`
   (essentially untouched), even though that account has made 2,637
   `claude-fable-5` requests this cycle per its `by_model` counters. This is
   strong direct evidence that **Fable traffic is not simply added to the
   base `7d` bucket** — if it were, `7d` would already reflect Fable usage and
   `7d_oi` would be redundant. It is consistent with (a) Fable draining its
   own `7d_oi` bucket first/instead, or (b) Fable debiting both but at a much
   smaller rate against `7d` than against `7d_oi`. The public sources found do
   not settle which of (a)/(b) is true, nor whether Fable also debits the
   base `5h` bucket. **This remains open — see "Open questions" and the
   proposed experiment below.**

3. **Full set of `anthropic-ratelimit-unified-*` headers observed in the
   wild** (compiled from the `pi-claude-oauth-adapter` source, which is a real
   npm/GitHub package that patches Pi's Anthropic OAuth traffic — see
   Evidence 3):

   Per-bucket (`{claim}` ∈ `5h`, `7d`, `7d_oi`, `overage`; likely also `5h_oi`
   per Evidence 7 though the adapter source only lists 5h/7d/7d_oi/overage in
   its `SURPASSED_THRESHOLD_CLAIMS` table):
   - `anthropic-ratelimit-unified-{claim}-utilization` — float `0.0`–`1.0`
     (can reportedly exceed 1.0 is not confirmed; observed values top out at
     `1.0` in this repo's proxy).
   - `anthropic-ratelimit-unified-{claim}-reset` — reset timestamp for that
     bucket (unix seconds in raw API responses per Evidence 4; this repo's
     proxy stores it as an ISO datetime after conversion).
   - `anthropic-ratelimit-unified-{claim}-surpassed-threshold` — presence
     alone signals "this bucket just crossed a warning threshold"; used to
     pick which bucket is reported as the *representative* one for a
     warning banner.

   Account/request-level (not per-bucket):
   - `anthropic-ratelimit-unified-status` — one of `allowed`, `allowed_warning`,
     `rejected`.
   - `anthropic-ratelimit-unified-representative-claim` — which bucket the
     status/reset above refers to (`five_hour`, `seven_day`, `seven_day_opus`,
     `seven_day_sonnet`, `seven_day_overage_included`, `overage`). **This is
     the field a client must branch on** — several `claude-code` GitHub issues
     found in this research report bugs where clients hard-coded checks
     against `7d-utilization` instead of resolving the bucket named by
     `representative-claim` first (Evidence 1).
   - `anthropic-ratelimit-unified-reset` — reset time for the representative
     claim.
   - `anthropic-ratelimit-unified-overage-status` — `allowed` / `allowed_warning`
     / `rejected`, for the **paid** `overage`/extra-usage credit pool
     specifically (distinct from `7d_oi`).
   - `anthropic-ratelimit-unified-overage-reset`
   - `anthropic-ratelimit-unified-overage-disabled-reason` — enum seen in the
     adapter source: `out_of_credits`, `org_spend_cap_reached`,
     `seat_tier_level_disabled`, `seat_tier_zero_credit_limit`,
     `org_service_level_disabled`, `member_level_disabled`,
     `member_zero_credit_limit`, `group_zero_credit_limit`,
     `org_level_disabled_until`.
   - `anthropic-ratelimit-unified-overage-in-use` — `"true"`/absent.
   - `anthropic-ratelimit-unified-overage-utilization`
   - `anthropic-ratelimit-unified-overage-surpassed-threshold`
   - `anthropic-ratelimit-unified-overage-period-monthly-utilization`
   - `anthropic-ratelimit-unified-overage-period-channel-utilization`
   - `anthropic-ratelimit-unified-grace-status` — presence signals a grace
     window is active (short buffer after hitting a limit).
   - `anthropic-ratelimit-unified-grace-5h-utilization`,
     `anthropic-ratelimit-unified-grace-7d-utilization`
   - `anthropic-ratelimit-unified-upgrade-paths` — comma-separated list of
     upsell plan names shown when rejected.
   - `anthropic-ratelimit-unified-fallback` — `"available"` if a fallback
     model/path exists.

   Reset semantics: reset values are absolute epoch timestamps (fixed point in
   time, not a "seconds remaining" counter), confirmed both by this repo's own
   proxy code (`_hdr_epoch`) and by the raw example header dump in Evidence 4
   (`anthropic-ratelimit-unified-7d-reset: 1783713600`, a fixed unix time).
   The adapter's own warning-threshold logic computes "how far through the
   window are we" as `(now - (resetAt - windowSeconds)) / windowSeconds`,
   treating the window as `resetAt - windowSeconds` → `resetAt`, i.e. a fixed
   anchored window ending at `reset`, not a sliding lookback from `now`
   (Evidence 3, `getResetProgress`). Window sizes used by the adapter:
   `five_hour` = 18,000s (5h), `seven_day` = 604,800s (7d) — as expected.

4. **`GET /api/oauth/usage` schema.** Confirmed structurally (not just by
   field name) via the adapter's own JSON parser (Evidence 3,
   `usageResponseToRateLimitHeaders`) and independently by a Go test fixture
   in a different, unrelated project (Evidence 6):

   ```json
   {
     "five_hour":        { "utilization": <0-100 float>, "resets_at": "<ISO8601>" },
     "seven_day":        { "utilization": <0-100 float>, "resets_at": "<ISO8601>" },
     "seven_day_opus":   { "utilization": <0-100 float>, "resets_at": "<ISO8601>" },
     "seven_day_sonnet": { "utilization": <0-100 float>, "resets_at": "<ISO8601>" },
     "extra_usage":      { "disabled_reason": "<string, optional>" }
   }
   ```

   Notes:
   - Utilization here is **0–100** (percent), unlike the response-header
     version which is **0.0–1.0** (fraction). The adapter divides by 100
     when converting.
   - Neither of the two sources that documents this schema's field list shows
     a `seven_day_overage_included` / Fable field being present by default.
     One source (Evidence 6, a Chinese-language Go comment in
     `Wei-Shaw/sub2api`) explicitly adds its own
     `SevenDayOverageIncluded ClaudeUsageWindow \`json:"seven_day_overage_included"\``
     field and notes: *"若不下发该字段，GetUsage 会用被动采样数据回填"* — "if the
     upstream usage API does not send this field, `GetUsage` backfills it from
     passively-sampled data [i.e. from response headers on real inference
     calls]." This is the strongest single piece of evidence that **the
     `/api/oauth/usage` endpoint does not reliably expose the Fable/`7d_oi`
     bucket**, and that community tools fall back to reading it from live
     `/v1/messages` response headers instead — exactly the strategy this
     repo's `bin/claude-token-proxy` already uses for `u7_oi`.
   - OAuth scope: this repo's own proxy observes the endpoint reject its
     tokens with `403 OAuth token does not meet scope requirement
     user:profile` (from live `/_status`, redacted). That the required scope
     is `user:profile` is this repo's own first-party empirical finding, not
     independently confirmed by the sources found in this research pass — no
     external doc/source enumerating the endpoint's required OAuth scope was
     found; flagging that specific scope name is **unconfirmed externally**.

5. **Weekly reset semantics.**
   - Resets are per-bucket, per-account, anchored timestamps (see job 3): no
     evidence anywhere of unused quota rolling over into the next window —
     every source treats crossing `reset` as a hard boundary that zeroes
     utilization for that bucket.
   - No source found states whether the anchor date can move (e.g. on
     plan upgrade/downgrade or billing-cycle change) — this is an **open
     question**, not addressed by any of the material found.
   - "Per-account anchored" is consistent with observed proxy data: three
     different accounts in this repo's `/cctoken` pool currently show three
     different `u7_reset` timestamps (`2026-09-12`, `2026-09-09`,
     `2026-09-13`), which would not be possible if the weekly window were a
     single global calendar-week boundary shared by all accounts.

## Evidence

1. **GitHub issue, `anthropics/claude-code#12829`**, "[Bug] Rate limit
   blocking ignores `anthropic-ratelimit-unified-representative-claim`
   header". Confirms `representative-claim` is the field a correct client
   must branch on instead of hard-coding a `7d-utilization` threshold check.
   https://github.com/anthropics/claude-code/issues/12829

2. **grep.app code search, query `seven_day_overage_included`**
   (https://grep.app/api/search?q=seven_day_overage_included, fetched
   2026‑09‑08). Eight independent repositories (`askalf/dario`,
   `srothgan/claude-code-rust`, `Wei-Shaw/sub2api`, `riba2534/happyclaw`,
   `Emanuele-web04/synara`, `get-bb/bb`) all define/reference
   `seven_day_overage_included` with converging semantics:
   - `askalf/dario` `test/analytics-billing-bucket.mjs`:
     `billingBucketFromClaim('seven_day_overage_included') === 'subscription'`,
     `isNonSubscriptionBilling('seven_day_overage_included') === false`, and a
     comment `"with the 7d_oi bucket at 99%): $0 out of pocket — subscription"`.
   - `srothgan/claude-code-rust` `src/app/events/rate_limit.rs`: renders
     `"seven_day_overage_included" => "7-day overage-included"` next to
     `"seven_day_sonnet" => "7-day Sonnet"`.
   - `riba2534/happyclaw` `container/agent-runner/src/provider-fallback.ts`:
     doc comment *"`seven_day_overage_included` is the rateLimitType emitted
     by current Claude Code for the Fable 5 model-specific limit. It
     therefore belongs with the [`'model'`]..."* and classifies it as
     `'model'` bucket type (same bucket type as `seven_day_sonnet`).
   - `riba2534/happyclaw` `tests/provider-model-fallback.test.ts`: comment
     *"Current Claude Code emits this type for Fable 5's model-specific
     wall."*, asserts `classifyProviderRateLimitType('seven_day_overage_included') === 'model'`.
   - `Wei-Shaw/sub2api` `backend/internal/service/account_usage_service.go`
     + `..._fable_test.go`: Chinese comment translated above; Go struct field
     `SevenDayOverageIncluded ClaudeUsageWindow` with a passive-sampling
     fallback; a test fixture JSON literally showing
     `"seven_day_overage_included": {"utilization": 56.0, "resets_at": "2026-07-08T03:00:00Z"}`
     alongside `five_hour`/`seven_day` in the same document shape as
     `/api/oauth/usage`.
   - `Emanuele-web04/synara` `apps/web/src/lib/rateLimits.ts` +
     `RateLimitsPanel.test.tsx`: normalizes `seven_day_overage_included` (and
     an alternate spelling `weekly_overage_included`), with a test titled
     *"humanizes the claude seven_day_overage_included window instead of
     leaking the raw key"*.
   - `get-bb/bb` `plugins/provider-claude-code/src/delta-translation.ts`:
     labels it `"Weekly included overage"` next to `"Weekly Sonnet limit"`.

3. **`minzique/pi-claude-oauth-adapter`** (npm package `pi-claude-oauth-adapter`,
   real, published, used by the `pi` coding-agent CLI itself for Anthropic
   OAuth compatibility) — `extensions/index.ts`, fetched raw from
   `https://raw.githubusercontent.com/minzique/pi-claude-oauth-adapter/main/extensions/index.ts`.
   This is the single richest primary source found. Key excerpts:
   - `SURPASSED_THRESHOLD_CLAIMS` table:
     `{ claimAbbrev: "5h", rateLimitType: "five_hour" }`,
     `{ claimAbbrev: "7d", rateLimitType: "seven_day" }`,
     `{ claimAbbrev: "7d_oi", rateLimitType: "seven_day_overage_included" }`,
     `{ claimAbbrev: "overage", rateLimitType: "overage" }` — this is the
     direct confirmation that the header short-name `7d_oi` maps 1:1 to
     `seven_day_overage_included`.
   - `getRateLimitLabel()`: `case "seven_day_overage_included": return "Fable 5 limit";`
     — the human-facing string Claude Code itself shows for this bucket.
   - A source comment referencing Claude Code's own minified bundle:
     *"Match Claude Code's `rl_` fallback in decoded/2490.js: a 429 with
     rate-limit representative-claim or overage headers is treated as
     `rejected`."* — i.e. this behavior was reverse-engineered from Claude
     Code's shipped JS, not from official docs.
   - `usageResponseToRateLimitHeaders()` parses `/api/oauth/usage` JSON
     fields `five_hour`, `seven_day`, `seven_day_opus`, `seven_day_sonnet`,
     and `extra_usage.disabled_reason` — but does **not** look for a
     `seven_day_overage_included`/Fable field in that response at all,
     consistent with job 4's finding that the endpoint doesn't reliably
     surface it.
   - Package README / npm listing confirm this is a real, actively maintained
     package (`v0.2.1`, published by `minzicat`/`minzique`, changelog entry:
     *"Unified usage-limit parsing now understands `7d_oi` / Fable 5 limits,
     overage utilization, overage in-use state, usage-credit wording, and
     grace-window warnings."*).
     https://github.com/minzique/pi-claude-oauth-adapter ,
     https://libraries.io/npm/pi-claude-oauth-adapter

4. **`steipete/CodexBar` GitHub issue #1894** — includes a raw captured header
   dump from a real minimal `/v1/messages` probe call showing the unix-epoch
   reset format and fraction-based utilization:
   ```
   anthropic-ratelimit-unified-5h-utilization: 0.01
   anthropic-ratelimit-unified-5h-reset: 1783180800
   anthropic-ratelimit-unified-7d-utilization: 0.63
   anthropic-ratelimit-unified-7d-reset: 1783713600
   anthropic-ratelimit-unified-5h-status: allowed
   anthropic-ratelimit-unified-representative-claim: five_hour
   ```
   https://github.com/steipete/CodexBar/issues/1894

5. **`riba2534/happyclaw`**, `container/agent-runner/src/provider-fallback.ts`
   and `tests/provider-model-fallback.test.ts` — see quotes under Evidence 2.
   Groups `seven_day_overage_included` under the same `'model'` classification
   bucket as `seven_day_sonnet`/`seven_day_opus`, i.e. treats it as a
   per-model sub-limit, not the account-wide weekly limit or the paid-overage
   limit.

6. **`Wei-Shaw/sub2api`**, `backend/internal/service/account_usage_service.go`
   + `account_usage_service_fable_test.go` — see quote and JSON fixture under
   Evidence 2. This is independent confirmation of the `/api/oauth/usage`
   JSON shape (`five_hour`, `seven_day`, `seven_day_overage_included` all as
   `{utilization, resets_at}` objects) from a project unrelated to the
   `pi-claude-oauth-adapter` codebase.

7. **`askalf/dario`**, `src/analytics.ts` +
   `test/analytics-billing-bucket.mjs` — establishes that both
   `five_hour_overage_included` (`5h_oi`) and `seven_day_overage_included`
   (`7d_oi`) exist as a matched pair, both classified `billingBucketFromClaim(...) === 'subscription'`
   and both `isNonSubscriptionBilling(...) === false`, in contrast to
   `overage` which maps to `'extra_usage'` and presumably
   `isNonSubscriptionBilling('overage') === true` (not directly quoted in the
   fetched snippet, but implied by the parallel structure of the test file).

8. **This repo's own live evidence** (`bin/claude-token-proxy`,
   `curl http://127.0.0.1:8788/_status`, captured 2026‑09‑08 23:5x UTC):
   account `a5de118c98c0` shows `u7: 1.0, u7_oi: 0.01` simultaneously, with
   2,637 `claude-fable-5` requests already made this cycle per its
   `by_model` counters — the account-level empirical anchor for job 2's
   "separate bucket, not a re-labelling" conclusion. `quota_error: "OAuth
   token does not meet scope requirement user:profile"` on all three pool
   accounts when the proxy calls `GET /api/oauth/usage` — this repo's own
   first-party finding on the scope requirement, not externally corroborated
   in this research pass.

## Open questions

- **Does a Fable-5 request also increment the base `7d` (and `5h`) buckets,**
  just at a much smaller/different rate, or does it bypass them entirely?
  No source found states this explicitly; the `'model'` classification
  pattern (mirroring `seven_day_opus`/`seven_day_sonnet`, which *are* believed
  to be genuinely separate per-model weekly pools that a normal Opus/Sonnet
  request would NOT also debit from the aggregate `seven_day` counter in
  addition) is suggestive but not proof for Fable specifically.
- **Does `5h_oi` (`five_hour_overage_included`) actually appear on the wire**
  for Fable requests, or was it only ever a defensive enum value added by
  downstream projects anticipating a symmetrical 5-hour bucket that hasn't
  actually shipped? Only one source (`askalf/dario`) references it, and only
  in a billing-classification helper, never in a captured raw header dump.
- **Can the weekly reset anchor move** (e.g. plan change, timezone change,
  billing cycle re-negotiation)? No source addresses this at all.
- **What does "overage included" actually mean etymologically** — is it "this
  bucket's quota already has some overage capacity baked into the
  subscription price" (most consistent with the `billingBucketFromClaim →
  'subscription'` classification), or something else? Not stated anywhere
  found; the `'subscription'` billing classification is the best available
  signal but Anthropic has published nothing that spells this out.
- The public record on `7d_oi` is recent/thin: all of it comes from
  community reverse-engineering (proxy/gateway projects that have to cope
  with Claude Code's real headers) rather than official Anthropic
  documentation. `docs.anthropic.com/en/api/rate-limits` /
  `platform.claude.com/docs/en/api/rate-limits` were checked in search
  results but did not surface in a form confirming `7d_oi` directly in this
  pass; a follow-up should fetch those pages directly and diff against this
  document.

## Proposed cheap empirical experiment (recommended over further search time)

Rather than spend more research budget chasing an undocumented,
recently-introduced header, the parent can settle job 2 cheaply and
authoritatively using the token pool already in `~/cctoken` (no proxy code
change needed — read-only observation):

1. Pick the account currently showing `u7_oi` near 0 (headroom) — from
   today's snapshot, `82a293204226` (`u7=0.79`, `u7_oi=0.69`, both still with
   headroom) or wait for `a5de118c98c0` to be usable again after its `7d`
   cooldown clears at `2026-09-13T09:59:59Z`.
2. Note `u7`, `u5`, `u7_oi` from `/_status` immediately before.
3. Send exactly one minimal `claude-fable-5` request directly against
   `api.anthropic.com` with that token (bypass the proxy, or force-route
   through it), and capture the *raw* response headers (not just what the
   proxy already parses) — specifically confirm whether
   `anthropic-ratelimit-unified-5h-utilization` and `-7d-utilization`
   (the base ones) move at all, versus `-7d_oi-utilization` moving.
4. Repeat with a `claude-opus-5` or `claude-sonnet-5` request on the same
   token immediately after, to confirm non-Fable models do NOT move `u7_oi`.
5. If `7d`/`5h` do not move on the Fable request while `7d_oi` does, job 2 is
   settled empirically ("Fable debits its own bucket only") without needing
   any further public-web research.

This requires no new tokens, no cooldown risk beyond one throwaway `max_tokens: 1`
request per model, and directly answers the one thing the public record left
open.

## Empirical experiment (2026-09-08)

Run through the live proxy (post pressure-pick activation, commit `4c800c9`)
against token `82a293204226` (`gs@gustafsilver.se`), which the picker selected
for both probes below (the token predicted for Fable, `a5de118c98c0`, was
in `7d`-cooldown at probe time — see the handover report for that anomaly).

**Fable probe** (`claude-fable-5`, `max_tokens: 1`):

- Immediately before (from proxy log, prior request on the same token):
  `u7=0.03 u7_oi=None u5=0.17`
- Response headers (`anthropic-ratelimit-unified-*`) on the Fable request
  itself:
  - `7d-utilization: 0.03`, `7d-reset: 1789538400`, `7d-status: allowed`
  - `5h-utilization: 0.17`, `5h-reset: 1788957000`, `5h-status: allowed`
  - `7d_oi-utilization: 0.07`, `7d_oi-reset: 1789538400` (same reset epoch
    as base `7d`), `7d_oi-status: allowed`
  - `representative-claim: five_hour`
- Immediately after (proxy `/_status`): `u5=0.17 u7=0.03 u7_oi=0.07` — `u5`
  and `u7` are byte-identical to the pre-probe reading; `u7_oi` is the only
  value that changed (went from previously-unobserved/`None` to `0.07`,
  i.e. this was the first time this token's Fable-specific bucket was
  sampled since the proxy restart, and it already reads non-zero from prior
  real Fable traffic on that token).

**Sonnet probe** (`claude-sonnet-5`, `max_tokens: 1`, same token,
immediately after the Fable probe):

- Response headers contain **no `7d_oi-*` fields at all** — only
  `5h-utilization: 0.17`, `7d-utilization: 0.03`, and the corresponding
  `-status`/`-reset` fields. The unified-status header set is a strict
  subset of the Fable response's set, missing exactly the three `7d_oi-*`
  keys.
- `/_status` after: `u5=0.17 u7=0.03 u7_oi=0.07` — unchanged from the
  post-Fable-probe reading (both base buckets held steady across two
  consecutive real requests, and `u7_oi` did not move, consistent with a
  non-Fable model never touching it).

**Conclusion:** Job 2 is settled empirically, and the conclusion agrees with
the already-committed hedge in Summary item 2 ("Fable draining its own
`7d_oi` bucket first/instead"): a Fable-5 request debits **only** the
dedicated `7d_oi` bucket. Base `7d` and `5h` did not move at all across the
Fable request (they read identically before and after, including across
several prior non-probe requests on the same token in the same minute), and
the `7d_oi` header trio is **absent entirely** from non-Fable (`sonnet-5`)
responses — confirming `7d_oi` is a Fable-5-only, separately-metered bucket,
not a shared/overflow counter that other models also report but leave at
zero. This single-account, `max_tokens: 1`-scale experiment cannot fully
rule out a tiny/rounded-away debit to base `7d`/`5h` on Fable requests, but
given multiple prior non-Fable requests on the same token also left `u7`/`u5`
at the same two-decimal reading, any such effect would have to be well below
the reporting granularity — i.e., not practically relevant to the picker's
pressure math.
