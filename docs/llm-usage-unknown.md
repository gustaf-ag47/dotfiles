# Why a quota reading can be `?`

`llm-usage --refresh` refreshes its report; it does not manufacture a fresh provider
quota observation. The local Anthropic proxy obtains quota from two distinct sources:

1. `GET /api/oauth/usage` when the OAuth token has the required scope.
2. Response-header observations from actual model requests, including rate-limit
   responses. Fable uses the separate `7d_oi` / `seven_day_overage_included` bucket.

An inference token can be valid for chat but receive HTTP 403 from the quota endpoint
because it lacks `user:profile`. The proxy records this and does not repeatedly retry
the denied endpoint until the token file changes. No environment variable can add an
OAuth scope to an already-issued credential.

An Opus/Sonnet response can update the base/5-hour buckets without supplying a Fable
reading. Expired header windows are invalidated. Neither the base usage nor an old
Fable exhaustion reading proves the current Fable balance. Unknown is not exhausted,
not zero usage, and not unlimited capacity.

## Investigation result (2026-10-03)

For the account requested by the operator, the live proxy exposed:

- a valid inference token, with a scope-denied quota endpoint;
- base and 5-hour observations, but null Fable utilization/reset;
- an older rate-limited Fable request in retained logs, followed by successful Opus
  traffic without a new Fable bucket observation.

This explains the question marks without a new inference probe or changing credentials.
Account-identifying evidence stays in the operator's private state, not this document.

## Reporting corrections

- The Fable window remains visible even when unavailable, with an `unknown_reason`
  in both the raw and normalized JSON report and an explanation in terminal output.
- The route table annotates missing Fable readings instead of a bare question mark.
- A passed reset displays `?% left — window reset; awaiting fresh reading`, not an
  invented `~100% left`.
- A genuinely observed `0% used` remains distinct from missing data: its normalized
  remaining percentage is 100, not null.

These are reporting changes, not modifications to token selection, cooldowns, model
routes, account plans or spending policy.

## Getting a real reading

Normal, authorized Fable traffic can supply a new Fable-specific response header.
Alternatively, use the provider's own usage page or an authorized login flow that
actually grants quota-reading scope, if available. `--refresh` alone cannot overcome
a scope denial. The reporter never logs in, upgrades scopes, consumes inference
quota just to populate a meter, or treats an unknown reading as a known allowance.

Regression checks: `python3 -m unittest tests.unit.test_anthropic_usage_freshness tests.unit.test_llm_usage -v`.
