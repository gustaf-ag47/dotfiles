# Jev use-case evaluation and ROI — skeptical review

Status: research only, no code changed, no live Jev calls, no credentials
read. Written from a read-only checkout of the shared parent repo at
`/home/gustaf/sync/src/dotfiles` (local `master`, 24 commits ahead of
`origin/master` at review time) plus this worktree's own
`docs/handover/jev-use-cases-evaluation.md` brief. All file:line and doc
citations below were opened and read during this review, not recalled from
memory. Scratch dir `$HOME/.cache/jev-use-cases/evaluation` was not needed —
no intermediate artifacts were produced.

Sibling reports (not read in depth, not duplicated here by design, per the
brief's "own only your report" constraint):
`docs/research/jev-use-cases-capabilities.md` (capability verification) and
`docs/research/jev-use-cases-workflows.md` (workflow discovery) on their own
branches. This report assumes their factual base (Jev's wire contract,
pricing, latency) matches the evidence already in
`docs/jev-pi.md`, `docs/research/jev-pi-routing.md`, and
`docs/research/jev-ten-levels-review.md`, all read in full for this review,
and focuses on **net ROI and go/no-go gates**, not re-deriving capability
facts.

## 1. What already exists (don't re-pilot what's running)

The repo already ships a **shadow-mode** classifier pilot:
`config/pi/lib/jev.mjs` (one shared helper), `bin/jev-classify` (CLI),
`config/pi/extensions/jev.ts` (`/jev` command), wired into
`config/pi/skills/delegate/scripts/delegate.sh:249-253` as a fire-and-forget
observation after every delegate dispatch. It classifies task text into
`interactive|build|research|mechanical` and **never sets `PI_LLM_CLASS`**
(`jev.mjs` top comment: "Never applies a classification result to anything
(`applied` is always false...)"). `scripts/llm_usage.py` surfaces its local
ledger (calls, cache hits, abstentions, estimated cost) separately from
provider quota. One measured live data point exists
(`docs/jev-pi.md` "Verification on this host"): a mechanical rename,
confidence 0.98, 362 ms, ~$0.0000176. A second, five-call authorized live
test (`docs/research/jev-pi-routing.md` §5a) measured 207–258 ms latency per
call and confirmed Pi 0.99.1's bundled catalog **under-reports** this
provider's cost as `$0` when TypeSafe's own published rate is
$0.042/Mtok input, free output — any ROI math below uses the **published
rate**, not Pi's catalog, per that finding.

This means candidate #1 below is not a green-field proposal — it's "should
we flip `applied` from always-false to sometimes-true," which is a much
smaller, better-evidenced step than building a new integration from scratch.

## 2. Skeptical framing: does the inference call beat the alternative?

For every candidate, the real question is not "can Jev do this" but "is
there already a deterministic rule, an existing Pi mechanism, or human
judgment doing this job at zero marginal cost and zero added latency, and
would Jev's probabilistic answer actually be *better*, not just
*additional*?" Three places in the existing codebase already settle this
question against Jev, and are cited as negative evidence, not hypotheses:

- **`bin/llm-schedule`** already does deterministic usage-window
  arithmetic against real `/_usage` data (`jev-pi-routing.md` §3, point 4:
  "there is no gap here that calibration-poor probability output would
  improve, and doing so would add a dependency on an external paid service
  to a component whose entire purpose is avoiding paid fallback"). Confirmed
  correct by my own read of the same reasoning — scheduling is a **known**
  arithmetic problem, not a classification problem.
- **`bin/claude-token-proxy`**'s hard gates (`class_eligible()`, `pick()`,
  per-class ceilings — `claude-token-proxy:1386-1451`) are explicitly
  server-side and must stay that way; a classifier can only ever choose
  *which* class/model string to request, never bypass the proxy's own
  quota arithmetic. Any candidate that would let Jev's output reach the
  proxy as anything other than a class *label* is out of scope by
  construction.
- **`docs/compaction.md:29-41`**: Pi already auto-compacts on a
  deterministic context-token threshold, with a `session_before_compact`
  hook extensions can use to cancel or supply a custom summary
  (`docs/compaction.md:298`). This directly undercuts the "should-compact
  advisory" idea borrowed from `ten-levels-of-jev` level 7
  (`jev-ten-levels-review.md`'s own table lists it "plausible... but
  unverified beyond the demo"): the *when* is already deterministic and
  working; the only thing a classifier could add is *cut-point quality*,
  which the same review found **no verification mechanism for** ("does not
  verify the chosen cut point actually preserves what the next step
  needs"). I therefore reject this as a go-forward candidate below — see §5.

## 3. Candidates considered, ranked

Scoring is qualitative (High/Med/Low), grounded in the measured 207–362 ms
latency and ~$0.00002–0.00007/call figures already in evidence, not invented
benchmarks. "Net value" discounts for cases where a deterministic rule
already captures most of the win.

| # | Candidate | Net latency cost | Net $ cost | User value if it works | Failure risk | Measurability | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | Promote delegate/Ralph task-class suggestion from observe to advisory-then-act (`PI_LLM_CLASS`) | Low — one call per launch, already async/discarded, 5 s outer timeout already enforced (`delegate.sh:253`) | Low — sub-cent/call at published rate; capped by existing `budget.maxCostPerDayUsd=0.05`/day | Med-High — could reduce "wrong class picked a too-expensive or too-cheap Anthropic tier" without a human remembering `--class` | Med — misrouting `interactive`→`mechanical` lets an unattended loop proceed without a human it needed; asymmetric cost | High — ledger + human-chosen class already loggable side by side; this is a **labeled comparison problem**, cleanest of all candidates | **Pilot first** |
| 2 | File-candidate triage before an expensive model reads/edits many files (ten-levels levels 8–9 pattern; no current repo workflow does this today) | Low per file (~200 ms), but **fans out** — a batch of N files is N calls unless batched into one `state`/multi-question request | Low per call, **but is new spend on a path that currently costs $0** (no triage step exists; today's cost is either "read everything" on existing quota, or a human/glob picks files) | Med-High *if* a real many-file workflow exists that currently reads everything; **unverified whether one does** — this report did not find a current repo site doing unfiltered multi-file reads at scale (that's the workflows sibling's job to confirm) | Med — ten-levels review's own finding: lexical (non-realpath) containment + no secret/dotfile denylist in the reference implementation lets a symlink or `.env` leak file content to a fourth party; must be fixed before any live test | Med — needs a recall/precision benchmark against a deterministic glob/grep baseline, not just agreement | **Design benchmark now, pilot only after a concrete fan-out site is confirmed by the workflows report** |
| 3 | Ralph loop stall/no-progress advisory (new finding, not in prior Jev docs) | Low — one call per iteration boundary, off the critical path of the iteration itself | Low | Med — `ralph/llm-utilization/loop.sh:53-62` has **zero semantic stall detection**: it burns iterations until `MAX` (default 20) or a hard timeout: there is no check for "the plan checklist hasn't changed in 3 iterations," so an unattended loop can spend up to `MAX` iterations making no real progress before a human notices | Low-Med — advisory-only (log/notify), never auto-aborts the loop, so a false positive only costs a wasted glance, not a stopped build | High — "did unchecked-task count decrease between iteration i and i+1" is a **fully deterministic** signal already available from `grep -c '^- \[ \]' $PLAN` before vs after each `run_once` — this is the central skeptical finding: a classifier is not needed here at all | **Reject as an inference use; adopt the deterministic version instead** |
| 4 | Bash/write guardrail / irreversible-command second opinion (ten-levels level 6) | Low | Low | Low in this stack specifically — `ten-levels-of-jev`'s own README says this is bypassable by a cooperative-but-undirected agent and "is an instruction, not a control" (`jev-ten-levels-review.md` "Where we agree"); this stack's actual hard boundary is `claude-token-proxy`'s server-side gates plus Pi's own tool-permission/approval prompts, which are already deterministic and already in the critical path | High if mistaken for a security boundary — the single most dangerous failure mode of any Jev candidate is someone *trusting* it as a gate | Low — "did it block the right things" is confoundable with "did the human already have to approve the tool call anyway" | **Do not build** |
| 5 | Result-content prompt-injection screening (ten-levels level 6 option C) | Low | Low | Low — TypeSafe's own docs (quoted in `jev-ten-levels-review.md`) state `jev-1.13` "does not treat state as hostile by default" and adversarial content "can move the answer" — using one unhardened classifier to police content for another model is a weaker control than it looks | High — false sense of security | Low | **Do not build** |
| 6 | Should-compact cut-point advisory (ten-levels level 7) | Low | Low | Low-Med — the *when* is already solved deterministically (`docs/compaction.md:29`); only the *cut-point quality* is unsolved, and no verification method exists for that in the reference implementation or in Pi's own hook contract | Med — a bad cut point silently drops state the next step needs, and nothing catches that except a human downstream | Low — "was the cut point good" has no automatic signal | **Do not build now; revisit only if `session_before_compact` cut-point quality becomes a measured pain point** |
| 7 | `llm-schedule`/`llm-wait` queue annotation | — | — | None found | — | — | **Already correctly rejected in `jev-pi-routing.md` §3; re-confirmed, not re-piloting** |

## 4. Assumptions made explicit (no invented numbers)

- Latency and cost figures are the two real measurements already in the repo
  (`docs/jev-pi.md`, `docs/research/jev-pi-routing.md` §5a: 207–362 ms,
  ~$0.000018–0.00007 per call on 300–420 input tokens). I did not run new
  calls. Any benchmark design below projects from these, not from a larger
  sample — treat per-call cost/latency as directionally right, not
  statistically characterized (n=6 total live calls exist across all prior
  research).
- I assume the delegate/Ralph task-class ledger (`events.jsonl` under
  `$XDG_STATE_HOME/jev/`) already has real observe-mode entries accumulating
  from normal use since the pilot shipped — I did not read that ledger (it's
  host-local state, outside this worktree, and the brief bars secret/state
  reads beyond what's needed for a docs review); the shadow pilot/promotion
  gate design in §5.1 depends on it existing and should be checked before
  starting.
- I assume (per `jev-ten-levels-review.md`'s own explicit framing) that
  TypeSafe's probabilities are a usable *relative* signal, not a
  statistically calibrated one — no candidate below should gate an
  irreversible action on a raw confidence threshold without an abstain path,
  consistent with the repo's own `minConfidence: 0.6` config default.
- Candidate #2 (file triage) is included because its *shape* (cheap judge
  before expensive read) is the strongest theoretical ROI pattern in the
  ten-levels source material, but I found **no concrete site in this repo**
  today where an expensive model reads an unfiltered batch of files chosen
  by something other than a human or a targeted `grep`/`fd` call — I did not
  exhaustively search for one (that's the workflows sibling's remit); treat
  §5.2 as a benchmark design to run *if* such a site is confirmed, not a
  recommendation to go build one speculatively.

## 5. Benchmark + shadow-pilot design for the top three

Scope per the brief: offline/synthetic benchmark + shadow-mode pilot
design, with example data, baseline, abstention/fallback, privacy
constraints, and measurable promotion/stop gates. No executable code is
provided — this is a design, consistent with the "research only" scope.

### 5.1 Candidate #1 — task-class suggestion (highest priority)

**Baseline**: today's static default (`--class build` in `delegate.sh:35`,
`RALPH_CLASS=build` in `loop.sh:6`) or an explicit human `--class` flag.

**Offline synthetic set** (compact, representative — mirrors
`classes.json`'s four categories and reuses the already-measured live
examples from `jev-pi-routing.md` §5a so results are comparable to prior
evidence):

| id | task text | expected human class | notes |
|---|---|---|---|
| t1 | "Rename variable `x` to `count` in utils.py" | mechanical | measured live: confidence 1.0 |
| t2 | "Fix a typo in README.md" | mechanical | clear |
| t3 | "Add a retry with exponential backoff around one HTTP call" | build | measured live: score 0.84 toward Standard |
| t4 | "Investigate why the nightly build intermittently fails" | research | no code change expected |
| t5 | "Decide whether to migrate auth to OAuth — need your tradeoffs input before I start" | interactive | explicit ask for back-and-forth |
| t6 | "Look into why it's slow sometimes and maybe fix it if it's easy" | ambiguous (build/research) | measured live: confidence 0.44, split 0.58/0.42 — deliberately kept as a *known-hard* case, not excluded |
| t7 | "Update 40 call sites to use the new logger signature" | mechanical-leaning but judgment-heavy (bulk edit, risk of missed site) | tests whether Jev conflates "repetitive" with "mechanical=no-judgment" |
| t8 | "Delete the deprecated `/v1/legacy` endpoint and its tests" | build or interactive (destructive, may need sign-off) | tests whether Jev's class choice is blind to destructiveness, which it is not designed to assess |

**Abstention/fallback**: already implemented — `minConfidence: 0.6` in
`config/llm-proxy/jev.json`; below threshold, `classifyTask()` returns
`status:"abstained"` and callers must keep the static default. This is not
new design work, just confirming the existing gate is the one to keep.

**Privacy constraint**: only the `--task` string is sent (already
documented in `docs/jev-pi.md` "Privacy, latency, and accounting"); a
promotion decision must re-confirm no real delegate task titles in the
sampled ledger contain secrets/customer data before widening scope, per
`jev-pi-routing.md` §5.3's own evaluation criterion.

**Shadow-mode pilot**: already running (observe mode, `applied` always
false). The next step is not a new pilot but a **scored replay**: pull N≥30
real `events.jsonl` entries (metadata-only, no raw task text per the
ledger's own privacy contract) paired with the `--class` actually used for
that dispatch (available in delegate's own invocation records, not the
Jev ledger) and compute agreement.

**Promotion gate** (all must hold): (a) agreement rate with human-chosen
class materially above the static-default base rate on the same N≥30
sample (the static default's own "accuracy" is whatever fraction of real
dispatches were already `build` — compute this first, it may be high,
which would make Jev's bar high too); (b) zero `interactive`-expected tasks
misclassified as `mechanical` or `build` in the sample (asymmetric-risk
check — this is the one failure mode that could let an unattended loop
proceed without a needed human); (c) no privacy-sensitive content observed
in the reviewed sample; (d) added latency stays in the 200–400 ms band
already measured, not materially worse at larger scale/concurrency.

**Stop gate**: any single `interactive`-should-be case misrouted downward
in a live (non-shadow) trial; daily cost (computed at the **published**
$0.042/Mtok rate, not Pi's catalog `$0`) exceeding the configured
`maxCostPerDayUsd`; `config_invalid`/`config_malformed` abstention rate
spiking (signals a broken deploy, not a model problem).

### 5.2 Candidate #2 — file-candidate triage (second priority, conditional)

**Precondition before running this at all**: confirm a concrete repo site
with unfiltered multi-file reads by an expensive model (this report did not
find one with certainty — see §4). If none exists, do not build; this
section is a ready design, not a recommendation to create the workflow.

**Baseline**: existing deterministic filters already in use elsewhere in
this stack's tooling family — extension/lockfile denylist patterns (same
shape as `ten-levels-of-jev`'s own
`\.(png|jpe?g|gif|...|lock)$` filter, flagged in
`jev-ten-levels-review.md` as *insufficient alone*) plus a targeted
`grep`/`fd` on the symbol/string actually being changed.

**Offline synthetic set**:

| id | file | signal | expected deterministic (grep) result | expected Jev value-add |
|---|---|---|---|---|
| f1 | `config/pi/lib/jev.mjs` | diff touches `classifyTask` | matches targeted grep for "classifyTask" | none — grep already finds it |
| f2 | `package-lock.json` | large generated diff | excluded by extension/lockfile denylist | none — already filtered for $0 |
| f3 | `README.md` | unrelated section edited in same commit | grep for the symbol misses it (no code) | could flag "low relevance" where grep found nothing to exclude it either — tests genuine disambiguation value |
| f4 | `tests/unit/test_jev.mjs` | tests the changed module, no direct string match to the specific renamed symbol | grep (symbol-name only) may miss it | potential real value-add: semantic "this tests the changed module" judgment |
| f5 | a symlink inside the watched tree pointing outside the repo (e.g., to a local secrets file) | — | lexical path check passes (ten-levels finding) | **must be blocked by a realpath/lstat check before Jev ever sees its content** — this is a go/no-go precondition, not a benchmark row to "pass" |

**Abstention/fallback**: unknown/low-confidence → include the file (fail
open toward more human/model review, never fail closed toward silently
skipping a file that might matter) — the inverse of #1's fail-closed
posture, because the cost of a false "skip" here is a missed edit, not an
unattended destructive action.

**Privacy constraint (hard precondition, not a tunable)**: realpath/lstat
symlink check and a `.env`/dotfile/credentials-pattern denylist must exist
and be tested *before* any file content (even truncated) is sent to a
fourth party — directly adopting `jev-ten-levels-review.md`'s finding that
the reference implementation lacks both.

**Promotion gate**: recall of actually-relevant files (per a hand-labeled
sample) at or above the deterministic grep baseline, at lower total $ cost
than reading every candidate file's full content with the expensive model;
zero instances of secret/denylisted content observed leaving the box in a
bounded live trial (≤20 calls, mirroring the §5a precedent's own bound).

**Stop gate**: any denylist/symlink bypass found in testing; recall below
the deterministic baseline (means Jev is actively worse than `grep`, not
just unnecessary).

### 5.3 Candidate #3 — Ralph stall advisory: deterministic recommendation, not a Jev pilot

Per §3 row 3, this is resolved **without Jev**. The actionable recommendation
is a plain shell check in `ralph/llm-utilization/loop.sh`'s existing
`for ((i=1; i<=MAX; i++))` loop: capture
`grep -cE '^- \[ \] [A-Z0-9_-]+:' "$PLAN"` before and after each `run_once`
call, and log/notify (never auto-abort, matching this stack's existing
"notify, human decides" pattern used by `anthropic-pool.ts`/`llm-failover.ts`)
when N consecutive iterations show no decrease. This is cited here, instead
of in §3 only, because the brief asked for a benchmark design for the "top
three" — and the top three honestly includes this negative result: the
correct "pilot" for this candidate is a one-line deterministic counter, not
a classifier integration, and it costs nothing to add.

## 6. What to try first, and what not to build

**Try first**: candidate #1 (task-class suggestion), because it is already
instrumented end-to-end in shadow mode, has the cleanest baseline (the
existing static default), the cleanest measurability (labeled comparison
against a real human choice already on record), and the smallest blast
radius if wrong (observe-only until the promotion gate in §5.1 is met).
Concretely: run the scored-replay comparison in §5.1 against real
`events.jsonl` + delegate invocation records before writing any new code.

**Design but don't build yet**: candidate #2 (file triage) — valuable
*shape*, unconfirmed *site* in this repo, and a hard privacy precondition
(realpath/denylist) that doesn't exist in the only reference implementation
reviewed. Wait for the workflows sibling report (or direct investigation)
to confirm a concrete fan-out read site before spending implementation
effort.

**Do not build**:
- Bash/write guardrail as a security control (candidate #4) — the source
  material itself says it isn't one, and this stack already has a better,
  deterministic one (`claude-token-proxy` server-side gates + Pi tool
  approval).
- Prompt-injection/result screening (candidate #5) — TypeSafe's own docs
  say the classifier isn't hardened against the exact attack it would be
  asked to detect.
- Should-compact cut-point advisory (candidate #6) — the triggering
  decision is already deterministic and working; the cut-point-quality
  problem it could theoretically help with has no verification method in
  any source reviewed.
- `llm-schedule`/`llm-wait` queue annotation (candidate #7) — already
  correctly rejected in prior research; re-confirmed here, not revisited.
- Ralph stall detection via Jev (candidate #3, as a *classifier* use) — the
  signal is fully deterministic; use a shell counter instead (see §5.3).

## 7. Uncertainties to flag to the parent

- Whether real `events.jsonl` entries have accumulated since the shadow
  pilot shipped, and in what volume — needed before §5.1's scored replay can
  actually run; not checked here (host-local state, out of this review's
  read scope).
- Whether any repo site matches candidate #2's precondition (unfiltered
  multi-file read by an expensive model) — not confirmed either way in this
  review; recommend checking the workflows sibling's findings before
  deciding on §5.2.
- Pi 0.99.1's cost-ledger gap for the extension-call path
  (`ctx.modelRegistry.classify()` outside `codemode`) — flagged as
  unverified in `jev-pi-routing.md` §6 and still unresolved as of this
  review; matters if candidate #1 is ever promoted to use the extension
  seam instead of the CLI seam it uses today.
- This review did not independently re-verify TypeSafe's published pricing
  page or re-run any live classify calls; all cost/latency figures are
  carried forward from the two prior authorized live tests already in the
  repo, not re-measured.

## Sources

Repository (parent checkout, read 2026-10-02): `docs/jev-pi.md`,
`docs/research/jev-pi-routing.md`, `docs/research/jev-ten-levels-review.md`,
`docs/research/jev-helper-implementation.md`,
`docs/research/jev-accounting-implementation.md`, `config/pi/lib/jev.mjs`,
`config/pi/extensions/jev.ts`, `config/pi/skills/delegate/scripts/delegate.sh`,
`ralph/llm-utilization/loop.sh`, `bin/claude-token-proxy` (line ranges per
`jev-pi-routing.md`'s own citations, cross-checked), `config/llm-proxy/jev.json`
contract as implemented in `jev.mjs`. Installed Pi docs (read in full for the
sections cited):
`/home/gustaf/.local/share/npm/lib/node_modules/@earendil-works/pi-coding-agent/docs/models.md`
("Use classifier models"),
`.../docs/virtual-models.md` ("Route requests", "Keep routing state"),
`.../docs/llama-cpp.md` ("Classification"),
`.../docs/compaction.md` (auto-compaction trigger and
`session_before_compact` hook).
