# Jev (TypeSafe System One) — capabilities and best-fit Pi use cases

Status: research only, no code/config changed, no credentials read, no live
Jev calls made by this report (one unbilled doc fetch to
`docs.typesafe.ai/models.md` to re-verify pricing/limits, 2026-10-02).
Branch `research/jev-use-cases-capabilities`, worktree
`/tmp/wt-research-jev-use-cases-capabilities`. Current integration in the
parent checkout (`/home/gustaf/sync/src/dotfiles`, read-only for this task)
is **observation-only**: it classifies a short delegate/CLI task string into
one of four labels and logs the verdict; it never chooses a model, switches
task class, authorizes a tool, declares a goal complete, compacts a session,
or touches `claude-token-proxy`. Treat every use case below against that
baseline, not against a hypothetical general-purpose agent.

## 0. Primary sources consulted

- `docs/jev-pi.md`, `docs/research/jev-pi-routing.md`,
  `docs/research/jev-ten-levels-review.md`,
  `docs/research/jev-helper-implementation.md`,
  `config/pi/lib/jev.mjs`, `config/pi/extensions/jev.ts`,
  `config/llm-proxy/jev.json` — all in `/home/gustaf/sync/src/dotfiles`
  (parent checkout, read-only), accessed 2026-10-02.
- `https://docs.typesafe.ai/models.md` — re-fetched directly 2026-10-02 for
  this report; confirms pricing ($42/Btok = $0.042/Mtok input, output free),
  rate limits (100K tok/s, 40 req/s, both stated as adjusting dynamically
  without notice), and context budget (64k total, 32k for `state` + longest
  question) exactly as already recorded in `jev-pi-routing.md` §5a. No
  discrepancy found between the prior research and the live page today.
- Installed Pi docs: `/home/gustaf/.local/share/npm/lib/node_modules/@earendil-works/pi-coding-agent/docs/{models,virtual-models,llama-cpp,cli}.md` — not re-read line-by-line in this pass; the prior research (`jev-pi-routing.md` §1–§2) already cites exact line numbers and this report defers to it rather than re-deriving the same facts. Spot-checked only where a use case below depends on a specific cited claim.

## 1. What Jev actually is (verified facts)

- **Not a chat model.** It takes a JSON `state` plus typed `questions`
  (`choice`, `score`, `bool`/wire `noul`) and returns typed `answers` with a
  probability/confidence — never free text. [Verified:
  `docs.typesafe.ai/models.md`, `/api.md`, cross-checked against Pi's
  `dist/types.d.ts` per `jev-pi-routing.md` §1.1.]
- **Pricing**: $0.042 per million input tokens, output free, on every
  account including direct API access — no free tier on the direct route.
  [Verified against TypeSafe's own docs, both by prior research and by this
  report's re-fetch today.] **Pi's bundled catalog price for the direct
  `typesafe/jev-latest` route is wrong** (`cost.input: 0`) — confirmed by a
  live test in `jev-pi-routing.md` §5a (5 billed calls, Pi reported $0 for
  all of them). The dotfiles helper (`config/pi/lib/jev.mjs`,
  `config/llm-proxy/jev.json`) already works around this by hardcoding the
  official $0.042/Mtok rate rather than trusting Pi's catalog or `/session`.
- **Latency**: one measured sample set exists — 5 synthetic live calls,
  207–258 ms each, recorded in `jev-pi-routing.md` §5a, plus one more
  independent sample in `docs/jev-pi.md`'s verification log (362 ms, 420
  input / 50 output tokens). This report does not add new timing data and
  does not extrapolate beyond ~10 total measured calls across both docs —
  treat latency as "roughly sub-second for short prompts," not a
  statistically characterized distribution.
- **Context**: 64k tokens total per request (state + all questions
  combined), 32k for state + the single longest question. [Verified,
  `docs.typesafe.ai/models.md`, re-confirmed today.]
- **Rate limits**: 100K tokens/sec, 40 requests/sec per account, explicitly
  documented as adjusting dynamically without notice. [Verified, same
  source, re-confirmed today — this is a **vendor-stated instability**, not
  a stable SLA; any use case that depends on a fixed throughput ceiling
  should treat this number as provisional.]
- **Confidence**: `(n·peak − 1)/(n − 1)` for `choice`/`score`; `bool`/`noul`
  carries only a bare probability, no separate confidence field. No vendor-
  supplied abstention threshold — TypeSafe's own docs say to pick one
  empirically. [Verified, `docs.typesafe.ai/confidence.md`, cited in
  `jev-pi-routing.md` §1.1 and §5a and `jev-ten-levels-review.md`.]
- **Input is text/JSON only** — no image/audio/video; non-text must be
  pre-processed into text first. [Verified, `docs.typesafe.ai/models.md`,
  re-confirmed today.]
- **Reliability signals that exist in the wire contract**: `stopReason` is
  always one of `stop|error|aborted`; errors are `401/422/429/529` with
  documented SDK retry-with-backoff on `429/529`. [Verified,
  `jev-pi-routing.md` §5a, sourced from `docs.typesafe.ai/api.md`.] No
  uptime/SLA figure was found in any source consulted — **absence of
  evidence**, not a claim either way.
- **Jev is not fine-tuned per account** — same weights for everyone,
  domain-shaping happens via `state`/`instructions`/`criteria` in the
  request, not training. [Verified, `docs.typesafe.ai/models.md`, fetched
  today.]
- **Adversarial content caveat, vendor-documented**: "State is data, and
  jev-1.13 does not treat it as hostile by default... Content written to
  adversarially steer the model... can move the answer." [Verified,
  `docs.typesafe.ai/model-jaggedness/jev-1.13.md`, cited in
  `jev-ten-levels-review.md`.] This is a vendor admission, not a third-party
  claim — treat Jev verdicts over untrusted/attacker-influenced text (e.g.
  delegated web content, user-pasted tool output) as not hardened against
  prompt injection.

### Vendor claims (not independently verified beyond the vendor's own docs)

- "Calibrated decisions" via RLCD training — a training-methodology claim
  from `docs.typesafe.ai/models.md`; this report has only ~10 total measured
  data points across both source docs, not nearly enough to independently
  confirm calibration.
- JevBench (mentioned only by name in Pi's `llama-cpp.md`) — no external
  corroboration found in any source consulted; flagged **[unverified
  externally]** in `jev-pi-routing.md` and left that way here.

### Hypotheses (this report's own reasoning, not sourced to a doc)

- Marked explicitly below wherever used, e.g. suitability judgments that
  extrapolate from the measured ~200–400ms single-call latency to "likely
  fine for a once-per-turn hook" without a load test.

## 2. Reconciliation with the actual integration (`config/pi/lib/jev.mjs`)

The shipped helper is deliberately narrower than anything Jev itself can
do: one `choice` question (`task_class` ∈ {interactive, build, research,
mechanical}), hard 2000-char input cap, 3s timeout (5s hard ceiling), 0.6
minimum confidence (abstain below), 100 calls/$0.05 per day budget,
cache keyed on rubric+model+threshold+class-set+text, and **`applied` is
hardcoded `false` everywhere** — no result ever changes `PI_LLM_CLASS`, a
model choice, or any proxy state (`config/pi/lib/jev.mjs`,
`config/llm-proxy/jev.json`, confirmed by reading both files directly in
the parent checkout). Any use case proposed below that goes beyond
"observe and log a classification" is **not what is running today** and
would require new code the parent explicitly scoped out of this pilot.

## 3. Candidate Pi use cases, ranked by fit to Jev's actual properties

For each: fit rationale against §1's verified properties, and explicit
fact/claim/hypothesis labeling.

### 3.1 Task-class pre-routing hint for `delegate.sh` / `ralph` loops (current pilot's own target)

- **What**: classify a short task description into
  `interactive/build/research/mechanical` before dispatch, to *suggest* (not
  set) `PI_LLM_CLASS`/`RALPH_CLASS`.
- **Fit**: [fact] matches Jev's `choice` question type exactly — this is
  the one case with real measured data (`jev-pi-routing.md` §5a: clear task
  → confidence 1.0; ambiguous task → confidence 0.44, split across two
  classes). [fact] Cheap even at the real $0.042/Mtok rate — ~350 input
  tokens/call ⇒ ~$0.0003 for 20 calls. [fact] This is literally what
  `config/pi/lib/jev.mjs` already implements, in observe-only form.
- **Boundary**: [hypothesis] graduating past observation to actually setting
  `PI_LLM_CLASS` would need a larger labeled sample than the ~10 data points
  gathered so far — both source docs explicitly decline to claim calibration
  from that sample size.

### 3.2 Capability-tier routing inside a virtual model (`jev-router.ts` pattern)

- **What**: classify prompt complexity once per session to pick a cheap vs.
  expensive physical model, cached in `request.state` so it runs once, not
  per-turn.
- **Fit**: [fact] this is Pi's own shipped reference example
  (`examples/extensions/jev-router.ts`), so the integration surface (virtual
  model `route()`, `ClassifierResult`, once-per-session caching) is
  documented and has a worked pattern, not a from-scratch design.
  [fact] latency is bounded to the first turn of a session only, per the
  example's own design — not per-message.
- **Boundary**: [fact, from `jev-ten-levels-review.md`'s offline probe]
  the only reference model-router implementation examined
  (`ten-levels-of-jev`'s `decideModel()`) has **no abstention path**: a
  zero-confidence answer is treated identically to a certain one. Any port
  of this pattern into the dotfiles stack needs level 4's floor/ceiling
  confidence gating merged in, not a bare threshold.

### 3.3 Cheap triage question over a short, already-local text blob (e.g. "does this diff look mechanical or does it need a human read?")

- **What**: a single `bool`/`choice` question against a short, already-
  in-context string (a diff summary, a commit message, a short log tail) —
  not a full file or secret-bearing content.
- **Fit**: [fact] input is text/JSON only, 32k/64k budget comfortably covers
  a diff summary or log tail; [fact] cheap per-call; [hypothesis] usable as
  a lightweight gate before a more expensive chat-model call (e.g. "is this
  log excerpt worth escalating to a full triage turn"), by analogy with the
  measured bool case (clear text → 0.97, hedged text → 0.32) — only two data
  points, direction only, not a calibration claim.
- **Boundary**: must stay within text already judged safe to leave the
  machine (see §5 privacy boundary) — this is explicitly *not* file-content
  triage (§3.7 below) unless the file-content caveats there are also met.

### 3.4 Should-compact advisory signal

- **What**: ask Jev whether the current turn is "a clean point" to compact
  a session, as one advisory signal among several, never an automatic
  trigger.
- **Fit**: [vendor-adjacent claim, not independently tested by either source
  doc] `jev-ten-levels-review.md` reports this as level 7 of a third-party
  demo repo, not something either prior research doc or this report
  measured directly. [hypothesis] plausible given the `choice`/`score`
  contract fits "how much of a clean break-point is this," but **unverified
  beyond a third-party teaching repo's own description of itself** — that
  repo's own README calls its numbers noisy run-to-run.
- **Boundary**: [fact, cited directly from the demo repo's review] no
  mechanism was found anywhere that verifies a chosen cut point actually
  preserves what the next step needs — it is a probability-weighted guess,
  same caveat as every other use here. Do not wire this to an unattended
  loop that auto-accepts without human/agent confirmation.

### 3.5 Soft guardrail / second-opinion hook on a risky bash command or file write

- **What**: classify a proposed command/write as `irreversible`/
  `destructive_intent` before executing, as one more soft signal alongside
  existing deterministic denylists.
- **Fit**: [hypothesis] the `bool`/`score` contract fits a yes/no risk
  judgment.
- **Boundary — this is explicitly the weakest fit found in all sources**:
  [fact, from the one third-party repo reviewed] the demo repo's own README
  documents the gate being bypassed by a cooperative agent routing around it
  via a bash heredoc, and had to be patched to explicitly forbid working
  around the block — "this is an instruction, not a control," in the
  review's own words. [fact] TypeSafe's own docs independently confirm Jev
  "does not treat state as hostile by default" and adversarial framing "can
  move the answer." **A Jev classification must never replace
  `claude-token-proxy`'s server-side hard gates or any deterministic
  denylist; at most it is advisory.**

### 3.6 Queue/schedule annotation for `llm-schedule`/`llm-wait`

- **What**: tag a queued job with an estimated class/cost before enqueueing.
- **Fit**: [fact, from `jev-pi-routing.md` §3 item 4] `llm-schedule`'s
  `reason()` already does deterministic windowing against real, measured
  proxy usage data (`/_usage`, `/_route`). There is no accuracy gap here
  that a probability-based classifier closes.
- **Verdict: poor fit.** Adding Jev here adds a dependency on an external
  paid service to a component whose entire purpose is avoiding paid
  fallback, for no measured accuracy gain over the deterministic baseline
  already in place. [This is the clearest case for "a deterministic rule
  is already correct and should stay."]

### 3.7 File-content triage at scale (read many files, ask Jev a typed question about each, never feed full content into the agent's own context)

- **What**: candidate-file discovery/triage — "does this file look relevant
  to X" — over many files in parallel, paying a narrow classify call instead
  of a full-file read against an expensive chat model.
- **Fit**: [fact, cited cost arithmetic from a third-party repo, internally
  consistent with official per-token pricing but not independently
  re-derived by either prior Pi research doc or this report] a
  narrow-schema decision call is structurally much cheaper than a full file
  read at chat-model input price, for files that end up irrelevant.
- **Boundary — second-weakest fit, serious before using**: [fact, confirmed
  by an offline reproduction against the only third-party implementation
  examined] that implementation's path containment is lexical only (no
  `realpath`/`lstat`), so a symlink inside a watched tree whose target
  resolves outside it is not caught before the target's content is read and
  sent off-box; separately, its file-type filter has no `.env`/dotfile/
  secret denylist, so a credentials file sitting in a glob would be sent to
  a fourth party like any other text file. **Do not adopt this pattern
  against real repository content without first adding a realpath check and
  a secrets/dotfile denylist** — this was explicitly out of scope for both
  prior research passes and remains unverified-as-safe here.

### 3.8 Chat-model replacement for open-ended reasoning, planning, or code generation

- **Verdict: not a fit at all, by contract, not by degree.** [fact]
  Jev is architecturally not a chat model — it never returns free text, only
  typed answers to typed questions over a provided `state`
  (`docs.typesafe.ai/models.md`, `dist/types.d.ts`). It cannot write code,
  explain a plan in prose, or hold a multi-turn conversation. Any Pi use
  case that needs free-text generation, multi-step reasoning with
  intermediate exploration, or tool use belongs to a normal chat model
  (Anthropic/Codex/DeepSeek via the existing proxy), never Jev.

## 4. Ranking

### Top three (best fit to Jev's actual properties)

1. **§3.1 task-class pre-routing hint** — already the running pilot; matches
   the `choice` contract exactly, has the most measured data of any use
   case here (small as it is), costs effectively nothing at the real
   price, and keeps a hard `applied: false` boundary that makes mis-
   classification low-stakes by construction.
2. **§3.2 capability-tier routing via a virtual model** — has a documented,
   shipped Pi reference implementation to build from
   (`jev-router.ts`), bounds added latency to once per session by design,
   and is the closest match to "Jev chooses something that actually changes
   cost" without touching the proxy's hard gates.
3. **§3.3 cheap text-only triage gate before an expensive call** — fits the
   text/JSON-only, cheap-per-call, bounded-context properties directly, and
   stays inside the "text already safe to leave the machine" boundary that
   §3.5/§3.7 violate.

### Poor fits

- **§3.6 scheduler annotation** — deterministic logic already covers this
  exactly as well, adds an external paid dependency for no measured gain.
- **§3.5 bash/write guardrail as a security boundary** — vendor-documented
  non-hardening against adversarial state plus a directly observed bypass
  in the one real implementation reviewed means this must never be the sole
  or final gate.
- **§3.7 file-content triage against real repos** — real fit for the cost
  model, but the only implementation examined has concrete, reproduced
  path-escape and secrets-exposure gaps; not safe to copy as-is.
- **§3.8 anything needing free text, multi-turn reasoning, or code
  generation** — out of contract entirely, not a matter of tuning.

## 5. Privacy/security and failure boundaries (apply to every use case above)

- **Fourth-party data custody.** Any text sent to Jev leaves the machine to
  TypeSafe (directly) or to whichever intermediary route is configured
  (OpenRouter/Cloudflare/Vercel/OpenCode) — a data-custody surface that does
  not exist for decisions handled entirely by the existing Anthropic/Codex/
  DeepSeek proxy stack. [fact, `jev-pi-routing.md` §4.] Keep task text short
  and non-sensitive; the shipped helper already caps input at 2000 chars
  and logs no raw text to its own ledger (verified by reading
  `config/pi/lib/jev.mjs` and its test suite description).
- **Not a security boundary.** Every guardrail-style use case (§3.5)
  must sit beside, never replace, `claude-token-proxy`'s server-side hard
  gates (`class_eligible()`, `pick()`, DeepSeek passthrough gates) and any
  deterministic denylist. [fact, consistent across `jev-pi-routing.md` §3
  and `jev-ten-levels-review.md`'s directly observed bypass.]
- **Adversarial/prompt-injection exposure.** Classifying attacker-
  influenced text (delegated web content, pasted tool output, a malicious
  file) is explicitly not hardened by TypeSafe's own admission. Any use
  case touching untrusted content needs this treated as one weak signal
  among several, never authoritative.
- **Cost-ledger accuracy.** Pi's own `/session` footer and bundled catalog
  under-report real spend on the direct `typesafe` route (`$0` vs. the
  real $0.042/Mtok) — verified by a live test in `jev-pi-routing.md` §5a.
  Any future accounting must compute from `usage.input_tokens` and the
  official rate, never trust Pi's own catalog default for this provider.
- **Reliability.** Vendor-documented rate limits (100K tok/s, 40 req/s) are
  explicitly stated as "adjusting dynamically without notice" — do not
  design a use case that assumes a fixed throughput ceiling. `stopReason`
  must always be checked before trusting `answers`; errors (`401/422/429/
  529`) are the caller's responsibility to handle with a deterministic
  fallback (the existing `jev-router.ts` pattern: fall back to the cheap
  model on any non-`stop` result).
- **When a deterministic rule or a normal Pi chat model is preferable**:
  - A deterministic rule is already strictly as good or better whenever the
    decision is exact/rule-based against known state (quota windows,
    explicit class flags, `classes.json` ceilings) — §3.6 is the clearest
    example; Jev adds cost and a new failure mode with no accuracy gain.
  - A normal chat model is required whenever the task needs free text,
    multi-step reasoning, tool use, or code generation — §3.8; Jev cannot
    do this by contract, not by degree.
  - A guardrail that must actually stop a dangerous action (not just advise)
    must be deterministic/server-side, because Jev's own vendor documents
    it does not treat input as hostile and the one implementation examined
    was observed being routed around by a cooperative agent.

## 6. Unknowns / not independently verified by this report

- Whether `ctx.modelRegistry.classify()` called from a Pi extension (not
  codemode) contributes to `/session` cost accounting the same way codemode
  does — flagged unresolved in `jev-pi-routing.md` §6, not re-tested here
  (out of scope: no live calls beyond the one unbilled doc fetch).
- JevBench — no external corroboration found in any source, including this
  report's own brief search.
- Calibration, in the statistical sense, across a large labeled sample —
  all measured data across both prior docs and this report totals roughly
  10 live classify calls; every claim in §3 above is explicitly labeled
  "directional" rather than "calibrated" for this reason.
- Uptime/SLA figures for the hosted TypeSafe API — not found in any source
  consulted.

## Sources

- `docs/jev-pi.md`, `docs/research/jev-pi-routing.md`,
  `docs/research/jev-ten-levels-review.md`,
  `docs/research/jev-helper-implementation.md`,
  `config/pi/lib/jev.mjs`, `config/pi/extensions/jev.ts`,
  `config/llm-proxy/jev.json` — all `/home/gustaf/sync/src/dotfiles` (parent
  checkout, read-only), accessed 2026-10-02.
- `https://docs.typesafe.ai/models.md` — fetched directly by this report,
  2026-10-02 (pricing, rate limits, context budget, text-only input,
  no-per-account-fine-tuning).
- `https://docs.typesafe.ai/confidence.md`,
  `https://docs.typesafe.ai/api.md`,
  `https://docs.typesafe.ai/model-jaggedness/jev-1.13.md` — not re-fetched
  by this report; cited via `jev-pi-routing.md` §5a and
  `jev-ten-levels-review.md`, both of which quote them directly with access
  date 2026-10-02.
- `examples/extensions/jev-router.ts`, installed Pi docs
  (`docs/models.md`, `docs/virtual-models.md`, `docs/llama-cpp.md`,
  `docs/cli.md` at `/home/gustaf/.local/share/npm/lib/node_modules/@earendil-works/pi-coding-agent/`)
  — cited via `jev-pi-routing.md`, not independently re-read line-by-line in
  this pass.
- `https://github.com/disler/ten-levels-of-jev` @
  `777adaf47d37ae0553220d35b2f15b3a3a063305` — cited via
  `jev-ten-levels-review.md`, including its offline reproduction of the
  path-escape and confidence-gap findings; not re-cloned or re-tested by
  this report.
