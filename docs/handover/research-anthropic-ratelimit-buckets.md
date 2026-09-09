# Research brief: Anthropic unified rate-limit buckets (esp. `7d_oi` / Fable)

## Context

We run a local quota-aware OAuth rotation proxy (`bin/claude-token-proxy` in this
repo) in front of `api.anthropic.com` for three Claude subscription accounts
(tokens in `~/cctoken`). It routes each request to the token with the most weekly
headroom, read live from response headers:

- `anthropic-ratelimit-unified-5h-utilization` / `-reset` / `-status`
- `anthropic-ratelimit-unified-7d-utilization` / `-reset`
- `anthropic-ratelimit-unified-7d_oi-utilization` / `-reset`

We plan to make token selection **model-aware**: requests for `claude-fable-*`
models appear to be metered against the separate `7d_oi` bucket (observed: an
account with `7d=1.0` exhausted still shows `7d_oi=0.01`). Before changing the
routing we need to understand the semantics. This is research only — do NOT
modify any code.

## Job (numbered, checkable)

1. Find what `7d_oi` stands for and which requests debit it. Hypotheses to
   confirm/refute: "overage included", Fable-specific weekly bucket, extra-usage
   bucket. Sources: Anthropic docs/release notes, Claude Code changelog/issues
   (github.com/anthropics/claude-code), community reverse-engineering (GitHub
   code search for `7d_oi`, `unified-7d_oi`, blog posts, HN, Reddit).
2. Determine whether a Fable-model request debits ONLY `7d_oi` or ALSO the base
   `7d` bucket (and the `5h` bucket). Cite evidence.
3. Document the full set of `anthropic-ratelimit-unified-*` headers known in the
   wild (names, value ranges, reset semantics: fixed anchor vs rolling window).
4. Document the undocumented `GET /api/oauth/usage` endpoint schema for
   subscription OAuth tokens (fields like `seven_day`, `five_hour`,
   `seven_day_opus`, `seven_day_sonnet`, `limits[]`) — does it have a Fable/oi
   bucket? Which OAuth scope does it need?
5. Note anything on how the weekly reset works: does unused quota roll over
   (no), is the reset per-account anchored, can the anchor move.

## Constraints

- Use the web-research skill: /home/gud1/.pi/agent/skills/web-research/SKILL.md
  (read it first; it fetches real pages from multiple engines).
- You may read repo files (esp. `bin/claude-token-proxy`,
  `bin/waybar-claude-usage`) for context. Do NOT edit any file except your
  findings file. Do NOT commit; the parent commits.
- Do NOT print, log, or copy token values from `~/cctoken` — actually, do not
  read `~/cctoken` at all. You may `curl http://127.0.0.1:8788/_status` (local
  proxy, redacted fingerprints only) to see live header values.
- Every claim needs a URL citation; mark speculation clearly as speculation.

## Where to record findings

Write `docs/research/anthropic-ratelimit-buckets.md` in this repo (create the
dir). Structure: Summary (answers to jobs 1–5), then Evidence with citations,
then Open questions. Do not commit.

## Cost guidance

Budget roughly 30–45 min of research. If the public record is genuinely thin on
`7d_oi` (plausible — it may be brand new), say so explicitly in the findings and
propose a cheap empirical experiment the parent could run against its own
accounts instead of burning more search time.

## Parent

Report is picked up by the parent session that spawned you (see the delegation
notice you received). When done, just finish your turn; the watcher notifies
the parent.
