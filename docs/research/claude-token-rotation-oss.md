# OSS survey: Claude multi-account/token rotation proxies

Research only, no code changed. Scope: prior art for redesigning
`bin/claude-token-proxy`'s selection policy from "lowest 7d utilization" to
earliest-deadline-first (EDF) with headroom margin and model-aware buckets.

## Summary and recommendation

**The exact redesign we're planning has already shipped, independently, in at
least three OSS projects**, under three different names for the same idea:

- **teamclaude** calls it `expiryRouting` — a *pressure* score per account per
  bucket: `headroom / seconds_until_reset`, selecting from the top-pressure
  band within a `tolerance` ratio.
- **claude-rotate** calls it `consume-first` — burn the account whose weekly
  window resets soonest, with a `consume_first_margin_s` guard so it only
  switches proactively when the gain is large enough.
- **claude-swap** calls it `--strategy consume-first` too (claude-rotate says
  it borrowed the name from claude-swap) — "keeps you on the account whose
  weekly window resets soonest... so perishable weekly quota isn't wasted."

All three also already do **per-model/bucket-aware routing** for exactly the
case we flagged (`claude-fable-*` on a separate bucket): teamclaude tracks
Fable/Sonnet on their own weekly buckets and takes "the higher of that
family's bucket and the shared weekly one" for eligibility; claude-swap has
`--model Fable` to fold a per-model weekly window into switch decisions;
claude-rotate's config table doesn't call this out explicitly but inherits it
from teamclaude by their own admission.

**Recommendation: borrow the policy math, don't adopt a project wholesale.**
Our proxy is intentionally small (stdlib-only Python, ~900 lines, one file,
already handles mid-stream failover and a `7d_oi` bucket). teamclaude is the
most sophisticated engine in the field but is Node.js, single-machine, and
architecturally heavier (TUI, MITM proxy, Codex pooling) than what we need.
claude-rotate is closest in spirit (small, one file, explicit stress-tested
herd-safety) but its own multi-device server model is a feature we don't need
(single account holder, one box).

Three concrete ideas worth porting into `bin/claude-token-proxy`, in priority
order:

1. **Pressure-ratio selection, not raw "soonest reset."** teamclaude's
   `headroom / seconds_until_reset` is the right formula — a soon-reset
   account with near-zero headroom left should *not* outrank a
   later-reset account still holding real quota. A pure "earliest deadline"
   rule without the headroom numerator is the naive version and is exactly
   what teamclaude's docs warn against ("a soon reset alone does not favour a
   nearly-drained account"). Use pressure, not raw reset-time, as the sort key.
2. **A margin/tolerance band, not a strict switch.** Every project independently
   converged on hysteresis: teamclaude's `tolerance` ratio band + `distributeSessions`,
   claude-rotate's `consume_first_margin_s` (only switch proactively if the
   candidate's reset is materially sooner), claude-swap's cooldown + hysteresis
   margin. Do the same — our current single hard `ROTATE_THRESHOLD` (0.98) with
   no margin will ping-pong once EDF makes the "best" token change more
   frequently near quota exhaustion.
3. **Distinguish quota-429 (rotate) from rate-429 (pace, don't rotate).**
   All three projects treat a per-minute burst 429 differently from a spent
   weekly/session bucket: pace/retry the *same* account (keep the warm prompt
   cache) instead of rotating on it. Our `FAILOVER_STATUSES = {401, 403, 429,
   529}` currently treats every 429 as a failover trigger — worth checking
   whether we already distinguish `anthropic-ratelimit-*-status: rejected`
   (quota) from a bare rate-limit 429, since teamclaude/claude-rotate both
   independently identified this as important (rotating on a burst just moves
   the burst and discards the cache).

A fourth idea, lower priority but cheap: teamclaude's **storm ramp** (cap
concurrency to 1 immediately after a switch, ramp up over ~30s) directly
targets the hot-spotting failure mode named in the brief (#84 in their
tracker: "N in-flight requests fail over at the same instant, spend a big
chunk of the fresh account's quota, instantly throttle it, cascade down the
fleet"). claude-rotate solves the same problem differently — a single lock
serializes the *decision* so only one switch happens for an arbitrarily large
herd, then every request gets exactly one retry onto the survivor (tested to
300 concurrent / 100 in-flight, see their stress suite). Our proxy is
single-account-holder / low-concurrency (one dev's `claude` sessions), so this
is a "nice to have, not urgent" — worth a look if we ever run several parallel
agent sessions against the proxy at once.

## Per-project table

| Project | ⭐ (2026-09) | Lang | Type | Selection policy | Failover | Last push |
|---|---|---|---|---|---|---|
| [KarpelesLab/teamclaude](https://github.com/KarpelesLab/teamclaude) | 296 | JS (Node, 0 deps) | local proxy | priority tiers, then soonest-reset governing bucket; opt-in `expiryRouting` pressure = headroom/seconds-to-reset within a tolerance band | quota-429 rotates; rate-429 paces same account (1 hop max on rate-429/5xx); storm ramp after switch | 2026-09-08 (today) |
| [doxaras/claude-rotate](https://github.com/doxaras/claude-rotate) | 26 | Python (FastAPI) | multi-device server proxy | `consume-first` (default): soonest weekly reset among usable accounts, `consume_first_margin_s` guards proactive switches; `least-used` alt strategy | quota-429 rotates; burst-429 paces; `hold_max_s` holds requests when all spent; single-lock switch decision (herd-safe, load-tested) | 2026-09-04 |
| [realiti4/claude-swap](https://github.com/realiti4/claude-swap) | 2,383 | Python | **credential switcher**, not a proxy | `best` (most quota left, default) or `--strategy consume-first` (soonest weekly reset); threshold + cooldown + hysteresis margin | quarantines dead-refresh-token accounts; fails safe on usage-check errors | 2026-09-08 (today) |
| [Wei-Shaw/claude-relay-service](https://github.com/Wei-Shaw/claude-relay-service) | 12,594 | JS (Node, Redis) | relay **platform** (multi-tenant) | account pool, admin UI | full retry/health-check platform | 2026-09-06 |
| [VictorMinemu/CC-Router](https://github.com/VictorMinemu/CC-Router) | 30 | TypeScript | local proxy | blind round-robin, no quota telemetry | none noted | 2026-08-31 |
| [Symbioose/claude-account-switcher](https://github.com/Symbioose/claude-account-switcher) | 53 | Python | macOS menu-bar switcher | live usage, switch at limit | manual-first tool | 2026-05-19 |
| [razzant/claudexor](https://github.com/razzant/claudexor) | 433 | TypeScript | multi-harness control plane (Codex/Claude/Cursor/OpenCode) | opt-in policy rotates a spent account out on typed vendor limits | part of a much larger product (races, budgets, gates) | 2026-09-07 |
| our `bin/claude-token-proxy` | (private) | Python stdlib | local proxy | lowest 7d utilization (today); EDF redesign proposed | 401/403/429/529 → same-request failover to next-best token | n/a |

Note on `claude-relay-service`: it is explicitly built for 拼车/"carpooling" —
pooling subscription accounts across *multiple people* to split cost. That's a
different (and more clearly ToS-violating) use case than our single-owner
multi-account rotation; excluded from deep comparison for that reason, not
because it's inactive (it's the most-starred and most active project found).

## Details

### 1. teamclaude — selection policy, failover, reset-awareness

Source: [README](https://github.com/KarpelesLab/teamclaude),
[docs/routing.md](https://github.com/KarpelesLab/teamclaude/blob/master/docs/routing.md)
(fetched 2026-09-08; repo pushed same day, i.e. actively developed right now).

- Default rotation: stays on current account until `switchThreshold` (0.98).
  When it does switch: lowest `priority` first, then among equal priority the
  account whose **governing weekly bucket resets soonest**. A model with its
  own weekly bucket (Fable, Sonnet) is ranked by *that* bucket, not the shared
  one.
- **`expiryRouting` (opt-in, "provisional" per their own docs, tracked in
  [#176](https://github.com/KarpelesLab/teamclaude/issues/176))**: computes a
  *pressure* score per account per model = headroom in the governing weekly
  bucket ÷ seconds until it resets. High pressure = ample quota about to
  expire → spend it first. This is explicitly EDF-with-headroom, matching what
  our brief proposes. Selection draws from the **top pressure band** — accounts
  within `tolerance` (ratio ≥ 1) of the best pressure — not a strict single
  winner, so it doesn't hot-spot one account.
- **Two kinds of 429 are handled differently, deliberately:**
  - *Quota rejection* (`unified-*-status: rejected`) → rotate immediately.
  - *Rate-limit 429* (per-minute throttle) → does **not** rotate. Pauses the
    account, retries in place (absorbing short `retry-after`s inline), only
    surfaces to the client on long waits. Rationale given verbatim: "Rotating
    on a rate-limit 429 would just move the burst to the next account and
    throw away the first account's prompt cache."
  - A rate-429 or 5xx still gets **one** failover hop (not a full walk of the
    fleet) — reasoning: if the second account is also rate-limited, the limit
    is almost certainly IP-scoped (all accounts share egress), so continuing
    to rotate proves nothing and burns cold-cache cost each hop.
- **Hot-spotting mitigation (storm ramp)**: after a switch, concurrency onto
  the new account starts at 1 and ramps by `stepConc` every `stepMs` (default
  +1/250ms) for `windowMs` (default 30s), fail-open. Directly named after
  their own incident, [#84](https://github.com/KarpelesLab/teamclaude/issues/84):
  "every in-flight request fails over to the next account at the same
  instant... can spend a big chunk of the fresh account's quota... cascading
  down the fleet."
- **Sticky sessions / prompt-cache affinity**: `distributeSessions` routes each
  *new* Claude Code session (tracked by `x-claude-code-session-id`) to the
  least-loaded eligible account and pins it there **per weekly-bucket**, not
  globally — a session using both Fable and Opus can pin to two different
  accounts, one per bucket, each keeping its own cache. Draining (not
  snapping) on config change so in-flight sessions don't all thrash caches
  at once.
- Also notable: MITM forward proxy catches hardcoded `api.anthropic.com`
  endpoints that ignore `ANTHROPIC_BASE_URL`; refreshes OAuth tokens before
  expiry and writes back to config; per-model `routes` table with glob
  matching and exclusive account pinning.

### 2. Other rotation policies confirmed independently

Both **claude-rotate** and **claude-swap** arrived at "burn the
soonest-resetting account first" under the name `consume-first`, without
(per claude-rotate's own README) being the same codebase — claude-rotate
explicitly credits claude-swap for the name/idea and teamclaude for the
burst-pacing and hold-until-reset ideas, i.e. this is **three separate
implementations converging on the same policy**, which is reasonably strong
validation that EDF-with-headroom is the right direction.

claude-rotate's config (from its README) spells out the guard rails precisely:
`switch_threshold` (0.8, 5h), `switch_threshold_7d` (0.98, weekly),
`switch_cooldown_s` (300s min between voluntary switches — hard limits ignore
it), `switch_margin` (0.05 hysteresis — a threshold switch needs a candidate
this much better), `consume_first_margin_s` (3600s — proactive switch only if
the candidate's weekly reset is at least this much sooner).

claude-swap's `cswap auto` has the same shape from the other side (credential
swap, not proxy): a cooldown (5 min) plus hysteresis margin so a proactive
switch needs to clear the margin, "so two accounts hovering at the line never
ping-pong."

### 3. Reset-time-aware (EDF) selection and the hot-spotting problem — answered

Yes — see above. All three approaches to hot-spotting differ but share the
same diagnosis (everyone stampedes to the newly-preferred account the instant
it becomes "best"):

- teamclaude: post-switch concurrency ramp (soft rate limit on the new
  account, self-tunes by watching the first request or two).
- claude-rotate: single lock around the *switch decision itself* — an
  arbitrarily large herd produces exactly one switch and one retry per
  request, load-tested to 300 concurrent / 100 in-flight
  ([their stress suite](https://github.com/doxaras/claude-rotate) claims
  ~3,500 req/s proxy overhead ceiling, mocked upstream).
- claude-swap: N/A directly (it swaps local credentials, not concurrent
  request routing) but its hysteresis+cooldown prevents *thrashing* between
  two close accounts, a related but distinct failure mode.
- teamclaude's `tolerance` band on `expiryRouting` pressure is itself a
  hot-spotting mitigation: instead of a single "best" account, a *band* of
  near-best accounts share the load (interacting with `distributeSessions`).

Our proxy's use case (one developer, `claude` CLI sessions, not a many-device
fleet) makes claude-rotate's herd-safety less directly relevant than
teamclaude's storm ramp — but neither is currently implemented in
`bin/claude-token-proxy`, and it's worth a look if parallel agent sessions
(pi delegate sub-agents, multiple `claude` windows) become common against one
proxy instance.

### 4. Other mechanisms worth stealing

- **Sticky sessions / prompt-cache affinity** — teamclaude's per-bucket session
  pinning (above) is the most developed version found. Nothing else surveyed
  does this; worth considering if/when we run multiple concurrent Claude Code
  sessions through the same proxy instance (currently N/A for a single
  developer machine, but relevant if the proxy is ever shared across
  windows/panes with independent conversations).
- **Request cost estimation** — claude-rotate's analytics panel has a
  cost-equivalent $ column per device/model/account "what the usage would
  cost at API list prices (incl. cache read 0.1×)". Not policy-relevant but
  cheap and useful for `/_status`.
- **Per-model routing** — teamclaude's `routes` table (glob match on model id
  → exclusive account subset) is more general than what we need (we're not
  pinning specific accounts to specific models, just the auto-detected
  bucket), but the "eligibility takes the higher of family-bucket-utilization
  and shared-weekly-utilization" rule is a real subtlety worth adopting if we
  add explicit `7d_oi` (Fable) eligibility logic — an account past its shared
  weekly cap should be ineligible for Fable too, not just accounts past
  their Fable-specific cap.
- **Health probing / token healing** — our proxy already does this
  (`CC_PROXY_REVALIDATE_INTERVAL`, park-and-reprobe on 401/403). teamclaude
  does the same (quota-rejection cooldown, auto re-admission after 5 min) and
  adds an explicit `oauth_not_allowed_for_organization` structured-error
  distinction we don't currently special-case (worth checking whether our
  401/403 handling can tell "org disabled OAuth" from "bad/expired token").
- **Token refresh handling** — teamclaude refreshes OAuth tokens proactively
  (before 5-minute expiry) and persists back to config; claude-rotate
  sidesteps the whole problem by using `claude setup-token`'s ~1-year token
  instead of the short-lived session OAuth token. Our proxy currently reads
  `sk-ant-oat...` tokens from `~/cctoken` (comparable to claude-rotate's
  approach) rather than doing live refresh — worth noting as a deliberate
  simplicity trade-off already made, not a gap.

## Method notes

- Web search engines (Ecosia/Brave via the web-research skill) were rate
  limited/blocked for most of this session (`ecosia: HTTP 403`,
  `brave: HTTP 429` on repeated retries with backoff up to 60s). One early
  query succeeded via Brave before the block. Switched to `gh` (authenticated
  GitHub CLI, already logged in as `gustaf-ag47`) for both code search
  (`gh search code`, `gh api search/repositories`) and direct repo/README
  fetches (`gh api repos/<repo>/readme`) — this ended up being a *better*
  primary source than search-engine snippets for this task (READMEs are the
  ground truth; several projects, especially claude-rotate, have written
  their own "comparison with similar projects" sections that were
  cross-checked against independently-pulled star counts and push dates
  rather than taken at face value).
- All star counts and push dates in the table above were independently
  verified via `gh api repos/<org>/<repo>` on 2026-09-08, not copied from
  claude-rotate's own comparison table (though they closely agree with it).
- Not deep-dived, time-boxed: `ccrotate`, `claude-rotator`, `cc-relay-proxy`
  (≤7 ⭐ each per claude-rotate's own table — too small to be independent
  confirmation of anything); `razzant/claudexor` (433 ⭐, real project, but
  scope is a much larger multi-harness control plane, not a focused
  quota-rotation proxy — skimmed README only); `Praxis Relay` and
  `CLIProxyAPI`, cited by claudexor as prior art but not fetched directly.
