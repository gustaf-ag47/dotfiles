# Plan: LLM routing from 8/10 to 10/10

Status: proposed 2026-09-28. Owner: operator. Builds on the A–D routing tasks
(`docs/handover/routing-{A,B,C,D}-*.md`) and the unified-`pi` change (`13805a5`, `9f67ccb`).

## 0. What "10/10" means — the objective, in numbers

"Maximally utilise every account across every provider" decomposes into four measurable
properties. The system is 10/10 when all four hold for a rolling 4-week window, as
reported by the proxy's own telemetry (task D) — not by feel.

| # | Property | Metric | Target |
|---|---|---|---|
| **P1 No starvation** | No request fails for quota while *any* provider that could serve that model class has headroom. | `starved_requests` = requests that ended in the "no OAuth account can serve" 503 or a Codex/DeepSeek refusal **while** `/_route` had a routable candidate at that moment. | **0 / week** |
| **P2 No waste** | No perishable window resets with headroom that demand could have used. | `weekly_waste_percent` per window (D's forecast at reset time, then measured). | **< 5 %** on every 7d/7d_oi window, Anthropic **and** Codex |
| **P3 No self-inflicted stalls** | A session never stops because *one* account's 5h window is spent while others are idle. | `avoidable_5h_stalls` = 5h quota-429s on account X while another eligible account had 5h headroom ≥ 30 %. | **0 / week** |
| **P4 Cheapest adequate tier** | Non-interactive work never consumes opus/fable-class quota when a lower tier is acceptable. | share of delegate/loop tokens billed to `7d_oi` (fable) or opus buckets. | **< 10 %** of delegate/loop tokens |

Guard-rails that must not regress while chasing these: prompt-cache hit rate for a
continuing session (≥ 80 % of a session's requests hit cache), and "no silent provider
change": every cross-provider move prints one line and is logged (`routing.log`).

## 1. Where we are (after A–D merge) and the gap per property

| Property | Today (est.) | Why not 100 % |
|---|---|---|
| P1 | ~95 % | Failover is still partly reactive; Codex has one account; DeepSeek balance is 0; loops don't wait for resets, they die. |
| P2 | ~70 % | Codex week routinely expires unused (fill-first until A lands). Even with A, the ×1.5 sticky band and the `< 0.98` threshold leave 2–15 % on the table by design. Weekends: quota resets while nothing runs. |
| P3 | ~60 % | B fixes concurrent-session spread; nothing yet *sizes* the fleet to the 5h capacity, and single heavy sessions still burn one account's 5h alone. |
| P4 | ~40 % | Delegates default to `gpt-6-luna` (good), but ralph loops and interactive sub-agents still take opus/fable by default, and `routes.json` is like-for-like only. |

Overall today ≈ 8/10 on P1, well below on P2–P4. The remaining 20 % is *policy and
scheduling*, not plumbing.

## 2. Principles (decisions that shape every task below)

1. **One EDF across all perishable quota.** Every subscription window — Anthropic 5h/7d/7d_oi
   per account, Codex 5h/7d per account — is a perishable resource scored the same way
   (`headroom / seconds_to_reset`). Money (DeepSeek) is not perishable and is never chosen on
   pressure; it is chosen by *task class* (§4) or as last resort.
2. **Session affinity beats global stickiness; task class beats model name.** The unit of
   routing is (session, task class), not (request, model).
3. **Proactive, at turn boundaries, with a stated reason.** Never mid-turn, never silent.
4. **Measure before tuning.** No constant (`PICK_TOLERANCE`, threshold, band) changes without
   D's forecast showing the effect for one week.
5. **Plumbing stays put.** The proxy stays Anthropic-wire only; pi does other providers
   natively; the proxy is the oracle. (Decision 1–2 of `generic-llm-proxy.md`.)

## 3. Work plan — phases with acceptance criteria

### Phase 0 — Land and verify A–D (in flight)
- Merge B → A → D → C onto `feat/pi-wait-for-quota-reset`; full gates; restart proxy.
- Verify live: `llm-usage` shows `preferred`, per-window forecast, `routing.recent`.
- **Exit:** one week of D telemetry captured (baseline for §0 metrics).

### Phase 1 — Close P1 (no starvation)

| Task | Change | Acceptance |
|---|---|---|
| **E1 Wait-for-quota primitive** | `bin/llm-wait` — blocks until a predicate on `/_usage` holds (`--until 'anthropic.base.left>=20 or codex.left>=20'`, `--max 6h`). Loops/delegates call it before starting and on the 503 path instead of dying (pi already does this interactively via `llm-failover.ts` decision 4). | A loop started at 100 % exhaustion resumes by itself after the first reset; test with `force_cooldown`. |
| **E2 DeepSeek funded + gated** | Run `scripts/deepseek-topup-wizard.sh` (~$10). Keep passthrough off for Claude Code; pi reaches DeepSeek via the extension. Add a monthly spend cap in the oracle (`CC_PROXY_DEEPSEEK_MONTHLY_CAP`, default $20): above it, DeepSeek is "unavailable (cap)". | `/_route` shows DeepSeek routable; cap flips it off in a unit test. |
| **E3 Second Codex account (if one exists)** | pi holds one `openai-codex` credential. Add `codex-accounts.json` (label → auth blob, gitignored) and a `codex-pool.ts` extension that registers **N** providers `openai-codex-<label>` sharing the Codex implementation, so `/_route` can rank Codex accounts by pressure exactly like Anthropic tokens. No proxy in the Codex wire path. | Two Codex accounts appear in `llm-usage`, the oracle prefers the one with higher pressure, switching is a normal `setModel`. |
| **E4 Starvation counter** | Proxy counts P1 violations (`routing.starved`) — a 503/refusal issued while `route_payload()` had `first_routable`. | Metric exists; is 0 in a week with E1–E2 in place. |

### Phase 2 — Close P2 (no waste)

| Task | Change | Acceptance |
|---|---|---|
| **F1 Reset-aware scheduling** | `bin/llm-schedule` (or a `--when` flag on `delegate.sh`/ralph `loop.sh`): defer non-urgent batch work to the next reset of the window with the most *forecast waste* (D). A systemd user timer (`llm-schedule.timer`) drains a small queue (`~/.local/share/llm-schedule/queue/*.sh`) when a window is fresh. | Queued job starts within 5 min of the chosen reset; `weekly_waste_percent` on that window drops the following week. |
| **F2 End-of-window sweep** | In the oracle, when a window is < 12 h from reset and forecast `waste`, temporarily widen its account's preference (multiply pressure by `SWEEP_BOOST`, default 2) so live work drains it. Hard stop at the burst limit. | Unit test: boosted account wins the pick inside the sweep window; D shows waste falling. |
| **F3 Codex forecast + waste on the same footing** | D samples Codex at every poll; the oracle's `preferred` uses `min(p7d, p5h)` for Codex too when a 5h window is reported. | Codex `weekly_waste_percent` reported; A's proactive switch fires on it. |
| **F4 Tune the band from data** | After two weeks of D: pick `PICK_TOLERANCE` and `ROTATE_THRESHOLD` that minimise waste subject to cache-hit ≥ 80 %. Record the numbers and the evidence in this doc. | Documented decision with before/after telemetry. |

### Phase 3 — Close P3 (5h stalls)

| Task | Change | Acceptance |
|---|---|---|
| **G1 Fleet sizing advice** | `llm-usage --capacity`: from 5h headroom and burn rates across accounts, print "N more heavy sessions are safe for the next H hours". `delegate.sh` reads it and warns (not blocks) when spawning past N. | Advice matches observed stalls in a synthetic test; no P3 stall in a week with the fleet sized by it. |
| **G2 Session split on 5h pressure** | Within a session, when its account's 5h pressure drops below the pool's best by > band **and** the session is at a natural boundary (compaction, new task file), move it — B's affinity plus a "reason=5h" move. | `routing.log` shows `reason=5h` moves; P3 metric 0. |
| **G3 Burst ramp** | teamclaude-style ramp after a move: cap concurrent requests to the new account for 60 s. (< 40 lines, was deferred by B.) | No 429 burst storm in a spread test with 6 concurrent sessions. |

### Phase 4 — Close P4 (cheapest adequate tier)

| Task | Change | Acceptance |
|---|---|---|
| **H1 Task classes** | `config/llm-proxy/classes.json`: `interactive` (fable/opus → astra/luna), `build` (sonnet → sol/luna), `mechanical` (haiku → flash/deepseek-flash), `research` (sonnet → sol). Each maps to an ordered provider/model list. | File exists; `/_route?class=build` ranks by class. |
| **H2 Defaults by entry point** | `delegate.sh --class` (default `build`), ralph `loop.sh` `RALPH_CLASS` (default `build`, `mechanical` for lint/format loops), interactive `pi` default stays `interactive`. `anthropic-pool.ts` sends `x-cc-proxy-class` so the proxy can enforce a per-class bucket ceiling (e.g. `build` may not use `7d_oi` above 70 % used). | P4 metric < 10 % after one week. |
| **H3 Escalation** | A class may escalate one tier on explicit signal only: the goal extension's evaluator failing twice, or `/model` by the human. Logged. | Escalations appear in `routing.log` with reason. |

### Phase 5 — Hygiene and guard-rails
- **I1** Remove `claude-token-refresh` probing from shell startup (`config/claude-code/env.sh`) — it spends quota to duplicate the proxy's job.
- **I2** Alerts: waybar/notify when `first_exhaust < 2h` or `weekly_waste_percent > 30` or `starved_requests > 0`.
- **I3** Weekly report: `llm-usage --week` prints the four §0 metrics; paste into this doc's log for four weeks.
- **I4** Academy fleet: retire the vendored wrapper (`docs/handover/2026-09-27-retire-pi-claude-sub.md` in the academy repo) so VMs get the same routing.

## 4. Task classes — the policy table (H1, draft)

| Class | Who uses it | Anthropic | Codex | DeepSeek | Bucket ceiling |
|---|---|---|---|---|---|
| interactive | the human's pi | fable-5 → opus-5-5 | astra → luna | v4-pro (last resort) | none |
| build | delegates, ralph BUILD | sonnet-5 → opus-5-5 | luna → sol | v4-pro | `7d_oi` off; opus only if sonnet exhausted |
| research | research/recon agents | sonnet-5 | sol | v4-pro | as build |
| mechanical | lint/format/bulk edits, doc drafts | haiku-4-5 | luna | **flash first** | subscription only if DeepSeek unavailable |

## 5. Sequencing and effort

```
Phase 0  (now)      merge A–D, baseline week                    parent
Phase 1  week 1     E1, E2, E4  (E3 only if 2nd Codex sub)      2 delegates
Phase 2  week 1–2   F1, F2, F3; F4 after 2 weeks of data        2 delegates
Phase 3  week 2     G1, G2, G3                                  1 delegate
Phase 4  week 2–3   H1, H2, H3                                  1 delegate (+ parent for defaults)
Phase 5  ongoing    I1–I4                                       parent
```

Roughly 8 delegate briefs of the size of A–D, plus one week of measurement between
Phase 2 and F4. Every task ships with unit tests, a second-instance live check, and a
report, per the A–D pattern; the parent owns merges.

## 6. Risks and how each is bounded

- **Cache thrash from more switching** (A, F2, G2): every move is at a turn boundary and
  logged; F4's cache-hit ≥ 80 % constraint is a hard stop on tuning.
- **Quality drift from tiering** (H): classes only lower the tier for non-interactive entry
  points; escalation exists; the human's session is never downgraded automatically.
- **ToS/billing surprises**: no new cloaking; Codex identity stays honest; DeepSeek capped.
- **Complexity creep in a stdlib proxy**: each phase adds pure functions with tests; the wire
  path is untouched after Phase 0.
- **Measuring the wrong thing**: §0 metrics are computed from the proxy's own logs, and
  I3 makes them visible weekly. If a metric cannot be computed, the task is not done.

## 7. Definition of done for the whole plan

Four consecutive weekly reports (I3) with P1 = 0, P2 < 5 % on every window, P3 = 0,
P4 < 10 %, cache-hit ≥ 80 %, and no unexplained entries in `routing.log`.

## Log

- 2026-09-28 — `llm-usage --week --json` first live sample: P1 starved requests 49 (visible event rows, including concurrent traffic; not a durable accumulator), P2 current projected waste Anthropic 7d ~64.0%, 7d_oi ~59.0%, Codex primary ~0.0%; P3 avoidable stalls 0 observed (sample-matched approximation), P4 n/a (no non-interactive class events), cache-hit 96.5%. Snapshot is live and can change as the proxy log grows; forecasts are projections, not reconstructed reset-time measurements; see `docs/handover/routing-I-hygiene-report.md`.
- 2026-09-28 — plan written. Baseline (llm-usage): gs@ 7d 7 % / fable 1 % left with 1d 22h
  to reset; gustaf.silver 72/68 %; antropic 64/59 %; Codex 100 % left, 5d to reset (P2
  failure in progress); DeepSeek −0.12 USD (P1 backstop absent).
