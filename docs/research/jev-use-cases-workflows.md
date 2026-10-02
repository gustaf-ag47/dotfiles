# Best Jev use cases for concrete Pi workflows in this stack

Status: documentation-only research. No code changed, no Jev calls made by
this agent, no secrets read. Evidence base: the parent checkout at
`/home/gustaf/sync/src/dotfiles` (read-only for this worktree; the cited
files do not exist in `research/jev-use-cases-workflows`'s own tree, which
branched before this pilot was committed there — see "Checkout note" below),
plus the installed Pi 0.99.1 docs at
`/home/gustaf/.local/share/npm/lib/node_modules/@earendil-works/pi-coding-agent`.
Primary prior research, read in full and treated as evidence rather than
re-derived: `docs/jev-pi.md`, `docs/research/jev-pi-routing.md` (includes a
real, bounded, authorized 5-call live test against `typesafe/jev-latest`),
`docs/research/jev-ten-levels-review.md` (review of disler/ten-levels-of-jev
cross-checked against TypeSafe's own docs). All three are in the parent
checkout; none are duplicated here beyond short quotes needed for ranking.

## Checkout note (read this before trusting any path below)

This worktree (`research/jev-use-cases-workflows`) was created from
`origin/master` at a point *before* the Jev pilot (`docs/jev-pi.md`,
`config/pi/lib/jev.mjs`, `config/pi/extensions/jev.ts`,
`docs/research/jev-pi-routing.md`, `docs/research/jev-ten-levels-review.md`)
was committed to the parent's working tree. `git log --oneline -5` here shows
HEAD at `c61270a fix(pi): preserve delegate watcher executable bits (#19)`,
and `find . -iname '*jev*'` in this worktree returns nothing but this brief.
The parent's checkout (`/home/gustaf/sync/src/dotfiles`, branch `master`,
dirty with unrelated unstaged changes plus several untracked
`docs/handover/*.md` files) does have all of the above, uncommitted. **Every
file:line citation below was read from the parent checkout, not from this
worktree**, since the brief's scope fence makes the parent checkout
read-only for this agent ("report fixes, do not apply them"). This is a
structural blocker for independent verification by a third party reading
only this worktree's git history — flagging it rather than silently citing
paths that don't resolve here.

## 1. What Jev actually is here (recap, not re-derivation)

- Jev (`typesafe-system-one` API) is a narrow **classifier**, not a chat
  model: it takes a `state` object plus typed `questions` (`choice`, `score`,
  `bool`/wire `noul`) and returns typed `answers` with a probability or
  confidence — never free text. Confirmed in installed Pi docs
  (`docs/models.md`, `docs/cli.md:164`: "codemode... call classifier models
  such as TypeSafe's Jev through `models.classify()`") and by a real 5-call
  live test (`jev-pi-routing.md` §5a): 207–258 ms latency per call, clean
  `stopReason: "stop"`, well-formed `usage`.
- Three real Pi seams: `models.classify()` from a `codemode` script (off by
  default, needs `defaultTools: ["+codemode"]`, 4-concurrent-call cap per
  script — `docs/cli.md:145-178`); `ctx.modelRegistry.classify()` from any
  extension; `route()` on a registered virtual model (`docs/virtual-models.md`).
  Pi ships exactly one worked example, `examples/extensions/jev-router.ts`
  (confirmed present at
  `$PID/examples/extensions/jev-router.ts`, `$PID` = installed package root).
- **This repo's pilot (`config/pi/lib/jev.mjs`, `config/pi/extensions/jev.ts`)
  is deliberately observation-only**: `applied` is hardcoded `false` on every
  return value; no automatic turn hook; only `/jev classify <text>` (explicit
  user command) or the delegate launcher's one-shot `--task` observation
  (`config/pi/skills/delegate/scripts/delegate.sh`, per `jev-pi.md`) ever
  calls it. Nothing here authorizes or implies a change to that boundary —
  this report's recommendations are themselves next candidates to pilot the
  same way, not a request to flip anything to "apply."
- Real, measured pricing gap: Pi's bundled catalog lists the direct
  `typesafe/jev-latest` route at `cost.input: 0`; TypeSafe's own docs
  (`docs.typesafe.ai`, fetched directly in `jev-pi-routing.md` §5a) say
  $0.042/Mtok input, output free. `/session`'s dollar figure for this route
  is not trustworthy; `config/pi/lib/jev.mjs` already works around this by
  computing `estimated_cost_usd` from `usage.input` × the official rate
  (`cost_source: "published-rate"`), not from Pi's catalog — a concrete
  correctness point worth preserving in any future integration.

## 2. Candidate workflows, found by reading the actual extensions/skills

Surveyed: `config/pi/extensions/{jev,goal,llm-failover,anthropic-pool,
anthropic-subscription,llm-usage}.ts`, `config/pi/skills/{delegate,
ralph-loop}/SKILL.md`, `config/pi/skills/delegate/scripts/delegate.sh`,
`bin/claude-token-proxy`, `config/llm-proxy/{classes,routes}.json`.

### A. Task-class selection for `delegate.sh` / `RALPH_CLASS`

- **What**: classify a delegation brief's one-line `--task` text into
  `interactive | build | research | mechanical` (the exact categories
  `config/llm-proxy/classes.json` already uses) to *suggest* `PI_LLM_CLASS`
  instead of `delegate.sh`'s current static default (`build`,
  `delegate.sh:35` per `jev-pi-routing.md` §3) or Ralph's static
  `RALPH_CLASS` default.
- **Input example**: `"Rename a local variable from x to count"` →
  **output example**: `mechanical`, confidence 0.98 — this exact pair was
  measured live (`jev-pi.md` "Verification on this host", 362 ms,
  $0.00001764).
- **Abstention/fallback**: already designed in `jev.mjs` — low confidence
  (< `minConfidence`, default 0.6) → `status: "abstained"`, falls back to
  the caller's existing default; missing key/timeout/budget-exhausted →
  `status: "skipped"`; `applied` is always `false`. This is the right
  fallback shape for a first opt-in: suggest, never silently switch.
- **Deterministic alternative**: a human already writes `--task`, so a
  human can just as easily type `--class mechanical` — the marginal value
  is saving that one flag for delegations where the human forgot or is
  unsure. Keyword heuristics ("rename", "lint", "fix typo" → mechanical)
  would catch the clearest cases (like the measured example) at zero cost
  and zero added latency, and would not need a fourth-party network call.
  Jev's advantage is covering the fuzzier middle (the live test's
  `"Look into why it's slow sometimes and maybe fix it if it's easy"` →
  `build` at confidence 0.44 — split 58/42 against `research`) where a
  keyword list has nothing to match on.
- **Frequency**: every `delegate.sh` invocation and every Ralph loop
  iteration — this is the most frequent single touchpoint in the stack.
- **Latency sensitivity**: low. `delegate.sh` already does a model-probe
  step before launch (`jev-pi.md`: "once per launch attempt... 5-second
  outer timeout"); one more ~250 ms call is a small fraction of total
  launch time and does not block an interactive turn.
- **Integration effort**: low-medium. The classifier call, cache, budget,
  and ledger already exist and are already wired as an *observer* into
  `delegate.sh` (per `jev-pi.md`). Moving from "observe and log" to
  "suggest a default a human can accept/override" is a UI/prompt change,
  not new plumbing — but it is a real boundary change from today's
  observation-only pilot and would need its own explicit sign-off.
- **Failure consequence if wrong**: bounded. Per `jev-pi-routing.md` §3's
  "hard gates" analysis, a wrong class only picks a different (still
  server-enforced) Anthropic overage ceiling in `claude-token-proxy`
  (`classes.json`'s per-class ceilings, `claude-token-proxy:1386-1396`) — it
  cannot bypass quota, cannot touch DeepSeek/Codex gates, and a human or
  `--class` flag can always override it. Worst case: a task runs under a
  too-generous or too-stingy spend ceiling for one delegation.

### B. Escalation trigger (`PI_LLM_CLASS_ESCALATE`)

- **What**: instead of (or alongside) a human noticing a `mechanical`-class
  job is actually hard, let Jev's `score`-type question flag "this task is
  more complex than its assigned class" and suggest setting
  `PI_LLM_CLASS_ESCALATE=1` for one run. The escalation mechanism itself is
  already a one-step, proxy-enforced lift (`anthropic-pool.ts:120` reads the
  env var; `claude-token-proxy:1377-1384`'s `escalated_class()` lifts
  exactly one class tier) — Jev would only ever be *a* trigger for an
  existing deterministic, bounded mechanism, never a new escalation path.
- **Input/output example**: measured live test's `score_complexity` case —
  `"Add a retry with exponential backoff around one HTTP call."` → score
  0.84 (between Trivial=0 and Standard=1, near Standard), confidence 0.75
  (`jev-pi-routing.md` §5a).
- **Abstention/fallback**: same as A — low confidence means no suggestion,
  task proceeds at its originally assigned class.
- **Deterministic alternative**: `ralph-loop/SKILL.md` already states
  escalation is "opt-in for one run: the human or a goal evaluator may set
  `PI_LLM_CLASS_ESCALATE=1`" — i.e. this hook point already exists and is
  already meant to be driven by a judgment call (human or evaluator), not a
  fixed rule. This is a workflow that *wants* a judgment signal, which is
  Jev's actual strength relative to case A (where a human already has to
  type something anyway).
- **Frequency**: lower than A — only matters on jobs that turn out harder
  than expected, a minority of runs.
- **Latency sensitivity**: low — same reasoning as A; adds one call at loop
  start, not per-iteration (mirrors `jev-router.ts`'s "classify once per
  session" pattern, `jev-pi-routing.md` §2.3).
- **Integration effort**: low — reuses A's wiring, just a different
  question shape and target variable.
- **Failure consequence if wrong**: bounded exactly like A — escalation is
  itself a single, proxy-enforced one-tier lift; Jev can at most trigger an
  already-bounded, already-reversible mechanism, never invent a new one.

### C. Goal-completion pre-check before the expensive evaluator call

- **What**: `config/pi/extensions/goal.ts` currently runs a **full chat
  model** evaluation on every turn against `MAX_TURNS` (default 25) — it
  builds a transcript (`buildTranscript`, char-budgeted at 14,000) and
  calls `ctx.modelRegistry.complete()` (`goal.ts:133`) with a free-text JSON
  prompt (`evaluatorPrompt`, `goal.ts:62-78`) asking `{met, impossible,
  reason}`. This is the heaviest, most frequent LLM call in the pilot's
  radius — potentially once per turn, up to 25 times per goal. A narrow
  Jev `bool` pre-check ("has *any* new evidence appeared since the last
  check that could change the verdict?") could skip the expensive full
  evaluator call on turns where nothing changed.
- **Input/output example (hypothetical, not measured)**: `state: {
  new_tool_results_since_last_check: "<diff>" }`, `bool` question
  "did anything happen that could satisfy or contradict the goal
  condition?" → `probability` near 0 ⇒ skip this turn's full evaluator call.
- **Abstention/fallback**: must fail open to running the full evaluator —
  skipping a real completion-check on a false "nothing changed" is a
  correctness regression (a goal silently never completes, or a user waits
  longer than necessary), so any abstain/low-confidence/error path must
  default to "run the full evaluator," not "skip it."
- **Deterministic alternative is probably better here**: a simple
  deterministic diff ("did the transcript grow since the last check? did a
  new tool result appear?") achieves the same filtering with zero added
  latency, zero cost, and zero new failure mode, and the current code
  already has the raw transcript in hand to do that comparison directly.
  Jev's probabilistic judgment ("could this change the verdict") adds a
  guess on top of information the extension could check exactly. This is a
  weak fit for Jev specifically, even though the underlying motivation
  (skip the expensive call when nothing changed) is sound.
- **Frequency**: high (per-turn, up to `MAX_TURNS`), the opposite of
  cases A/B's per-launch frequency.
- **Latency/cost sensitivity**: **high** — this sits directly in the
  autonomous loop's hot path; adding Jev here means paying its latency
  (200-350 ms measured) *in addition to* the full evaluator call on every
  turn where it doesn't skip, which only pays off if the skip rate is high
  enough to amortize that overhead. Unverified without real usage data.
- **Integration effort**: medium — `goal.ts` would need a second model
  reference (`pickEvaluatorModel`-style lookup for a classifier instead of
  a chat model) and its own abstain-to-full-evaluator fallback logic; no
  existing wiring to reuse, unlike A/B.
- **Failure consequence if wrong**: a false-negative skip (Jev says
  "nothing changed" when something did) delays goal detection by up to
  `MAX_TURNS`; this is contained by the existing turn ceiling and spend
  tracking already in `goal.ts` (`GoalState.turns`, `spendUsd`), but it is a
  real behavior risk a deterministic diff check does not carry at all.

### D. File-candidate triage before an expensive read (levels 8–9 pattern)

- **What**: per `jev-ten-levels-review.md`'s own ranking, "candidate-file
  triage" — classifying many files cheaply ("is this file relevant to X?")
  before paying full-context-window cost to read the ones that matter — is
  one of the two strongest fits in the reviewed reference implementation.
  Nothing in this dotfiles stack implements this today; it is a hypothesis
  carried over from the ten-levels review, not evidence from this repo's
  own code.
- **Input/output example (hypothetical)**: `state: { file_path, first_200_
  chars }`, `bool` "is this file likely relevant to <search goal>?" →
  probability, used to prune a large `rg`/`fd` result set before a
  `read` tool call on each survivor.
- **Abstention/fallback**: treat low confidence as "keep the file" (false
  positives cost a wasted read; false negatives silently hide a relevant
  file — asymmetric, and the safer default is to over-include).
- **Deterministic alternative**: `rg`/`fd` with good patterns, plus
  existing tools (`grep`, path/extension filters) already do most of this
  triage at zero cost; Jev would only add value for triage criteria too
  fuzzy for a pattern (e.g. "relevant to this bug's *symptom*," not just
  a keyword match).
- **Frequency/latency**: potentially very high fan-out (one call per
  candidate file) — the reviewed implementation runs 16 concurrent calls
  (`jev-ten-levels-review.md`), which at real TypeSafe pricing and rate
  limits (100K tok/s, 40 req/s account-wide, per that review's §"Official
  pricing") is a materially different cost/latency profile than cases A–C's
  one-call-per-launch pattern.
- **Integration effort**: high relative to A/B — needs the concurrency cap
  (`codemode`'s own 4-per-script limit, `docs/cli.md:178`, already below
  the reviewed implementation's 16), a path-realpath/symlink check, and a
  secrets/dotfile denylist before any file content is sent to Jev as
  `state` — the review found the reference implementation has none of
  these (`jev-ten-levels-review.md`: lexical-only containment, "a `.env`
  file sitting in a globbed directory would be read ... and sent to Jev").
- **Failure consequence if wrong**: privacy, not correctness — the review's
  most serious finding is that unredacted file content (`.env`, secrets,
  arbitrary repo files) can reach a fourth party (TypeSafe/OpenRouter/etc.)
  through this pattern if implemented the way the reference repo does it.
  This is the highest failure-consequence case evaluated here, by a wide
  margin, and is **not recommended without the mitigations the review
  specifies** (`jev-ten-levels-review.md`'s "Minimal opt-in implementation
  sequence" item 3: realpath check, denylist, no full-state-to-stderr
  logging).

### E. Bash/write guardrail hook (ten-levels level 6)

- **What**: classify a proposed destructive bash command or file write as
  `irreversible`/`destructive_intent` before executing it, as a soft
  second-opinion check layered on top of (never instead of) existing
  deterministic gates.
- **Why rank low**: the reviewed reference implementation's own README
  documents a live bypass (agent wrote a blocked file via a bash heredoc
  instead of the gated tool) and the review's own reproduction confirms a
  **confidence gap**, not just the bypass: `gateBash({irreversible@0.4,
  destructive_intent@0.6})` returns `{block: false}` — a command flagged
  irreversible at just-under-threshold confidence is allowed to run with no
  "ask a human" middle tier (`jev-ten-levels-review.md`, "Verified
  offline" section, reproduced against the cloned source, not just read).
  This repo's own `claude-token-proxy` already enforces hard, deterministic,
  server-side gates (cooldowns, ceilings, balance checks) that cannot be
  overridden by a client-sent value — the review is explicit that "a
  Jev-gated hook is advisory to a cooperative agent, not a security
  boundary," and this stack should not add one that could be mistaken for
  one.

## 3. Ranking (value / frequency / latency sensitivity / integration effort / failure consequence)

| Rank | Case | User value | Frequency | Latency sensitivity | Integration effort | Failure consequence | Deterministic logic would likely beat it? |
|---|---|---|---|---|---|---|---|
| 1 | A — task-class suggestion for `delegate.sh`/`RALPH_CLASS` | Medium-high (saves a flag, catches fuzzy-middle cases a keyword list misses) | Highest in this list (every delegation/loop start) | Low (one-shot, pre-launch, wiring already absorbs a 5s outer timeout) | Low-medium (observer wiring already exists per `jev-pi.md`; this is "promote to suggestion," not "build from scratch") | Bounded — server-side proxy ceilings and human override remain the real gate (`jev-pi-routing.md` §3's hard-gates table) | Partially — a keyword heuristic covers clear cases; Jev's value is specifically the fuzzy middle the live test demonstrated (0.44 confidence split) |
| 2 | B — escalation trigger for `PI_LLM_CLASS_ESCALATE` | Medium (helps a loop self-correct mid-run without a human watching) | Lower than A (minority of runs turn out harder than assigned) | Low (once per loop, not per iteration) | Low (reuses A's wiring, different question/target) | Bounded — escalation is itself a single proxy-enforced tier lift, already designed to be judgment-driven per `ralph-loop/SKILL.md` | No — this is a judgment call by design (the skill doc already names "a goal evaluator" as a valid trigger), the closest fit for Jev in this set |
| 3 | D — file-candidate triage before expensive reads | Potentially high (cheap narrow-schema decision vs. full-context read, per reviewed cost comparisons) but **not evidenced in this repo** — hypothesis only | Could be very high (fan-out per file) | Medium-high (concurrency, rate limits, queuing behavior unverified in this stack) | High (needs realpath/symlink check, secrets denylist, redacted logging — none exist yet per the review) | **High** — unmitigated version leaks file content (including secrets) to a fourth party; only recommended with the review's listed mitigations in place first | Partially — `rg`/`fd` patterns already cover most triage; Jev adds value only for fuzzy relevance judgments |
| 4 | C — goal-completion pre-check to skip the full evaluator | Speculative (motivation is sound: skip expensive per-turn chat-model calls) | High (per-turn, up to `MAX_TURNS`) | **High** — adds latency on the hot path and only pays off with a high, unverified skip rate | Medium (new model lookup + fail-open logic in `goal.ts`) | Moderate — false-negative skip delays goal detection, bounded by existing turn/spend ceilings in `goal.ts` | **Yes, likely** — `goal.ts` already has the transcript in hand; a deterministic "did anything new appear since last check" diff achieves the same filtering with no added cost/latency/failure mode |
| reject | E — bash/write guardrail hook | Low as a *safety* mechanism (the exact framing it would be adopted for) | N/A | N/A | N/A | **Unacceptable if mistaken for a security boundary** — reviewed reference implementation's own documented bypass plus an independently reproduced confidence gap (`block:false` at 0.4/0.6, just under both thresholds) | Yes, unambiguously — this repo's existing deterministic server-side gates in `claude-token-proxy` are the correct mechanism; Jev could at most be an advisory *second opinion* layered on top, never the gate itself |

## 4. Top three recommendation

1. **A — task-class suggestion for delegations and Ralph loops.** Highest
   frequency, lowest integration delta (the observer wiring and
   abstain/fallback behavior already exist per `jev-pi.md`), and the
   failure mode is already bounded by `claude-token-proxy`'s server-side
   ceilings regardless of what Jev suggests. This is the natural next step
   *if and only if* the observation-only boundary is explicitly lifted by
   a human decision — nothing here authorizes that step itself.
2. **B — escalation trigger.** Second-best fit for the same reasons as A,
   plus `ralph-loop/SKILL.md` already names a "goal evaluator" as a valid
   trigger for this exact mechanism — Jev is a plausible implementation of
   that already-designed hook point, not a new concept being bolted on.
3. **D — file-candidate triage, conditionally.** Potentially the highest
   raw value (narrow-schema classification is far cheaper than a full
   context read, per both the live pricing math and the reviewed
   implementation's cost comparisons) but is **not currently evidenced
   anywhere in this repo** and carries the most serious failure mode found
   in this survey (secret/file-content leakage to a fourth party absent
   specific mitigations). Rank it third only on the explicit condition that
   the realpath/symlink check, secrets denylist, and redacted logging from
   `jev-ten-levels-review.md`'s "Minimal opt-in implementation sequence"
   are built first and reviewed independently of the triage feature itself.

**Explicitly rejected**: E (bash/write guardrail) — the one case in this
survey where a wrong/overconfident classification result could plausibly be
read by a future engineer as a security control, and the evidence
(documented bypass, reproduced confidence gap) says it cannot be. If a
soft second-opinion nudge is ever wanted alongside `claude-token-proxy`'s
existing hard gates, it must be labeled and designed as advisory-only from
day one, matching this repo's own `jev.mjs` convention of `applied: false`
everywhere.

**C (goal-completion pre-check) is also not recommended as a Jev use**,
not because the underlying motivation is wrong, but because a deterministic
diff check on the transcript `goal.ts` already holds in memory achieves the
same filtering with none of Jev's added latency, cost, or false-negative
risk.

## 5. Evidence vs. hypothesis, stated plainly

- **Evidence** (measured or directly read from code in the parent checkout):
  §1 entirely; case A's input/output example and confidence numbers; case
  B's score example; all of §2's "Deterministic alternative" and "Failure
  consequence" analysis for A, B, E; the ten-levels review's reproduced
  findings cited in D and E.
- **Hypothesis** (plausible, not evidenced by this repo's own running
  code): case D's applicability to this stack specifically (no file-triage
  code exists here; the pattern is carried over from the external
  ten-levels review); case C's skip-rate assumption (no usage data on how
  often `goal.ts`'s evaluator would find "nothing changed").
- **Observation-only boundary, restated**: every recommendation above is a
  candidate for the *next* pilot step, evaluated the same cautious way the
  existing `jev.mjs`/`jev.ts` pilot was built (observe, log, never apply,
  fail closed on config errors, fail open on abstain). Nothing in this
  report is authorization to change `applied: false` anywhere, wire a
  suggestion into an actual default, or enable `codemode` in any shared
  settings file.

## Limitations

- This worktree could not independently re-verify the cited parent-checkout
  file:line references by running `git log`/`grep` against its own history,
  since the Jev pilot postdates this worktree's branch point (see
  "Checkout note"). Every citation was read directly from
  `/home/gustaf/sync/src/dotfiles` at the time of writing (2026-10-02); a
  future reader of only this worktree cannot `git show` those paths without
  also having that checkout.
- No live Jev calls were made by this agent; all live-test numbers are
  quoted from the prior authorized live test in `jev-pi-routing.md` §5a, not
  reproduced here.
- Case D and case C's recommendations rest partly on an external repo
  review (`jev-ten-levels-review.md`) rather than this stack's own running
  code — flagged as hypothesis in §5, not presented as this repo's measured
  behavior.
- Sibling worktrees (`research/jev-use-cases-capabilities`,
  `research/jev-use-cases-evaluation`) were not read, per the scope fence.
