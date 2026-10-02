# Review: disler/ten-levels-of-jev

Source: https://github.com/disler/ten-levels-of-jev, local read-only clone at
`/home/gustaf/.cache/jev-research/ten-levels-of-jev`, commit
`777adaf47d37ae0553220d35b2f15b3a3a063305` (pin this commit in any permalink
below — the repo may move). Accessed 2026-10-02. No paid calls, no
credentials, no code executed from the repo. Cross-checked against
`https://docs.typesafe.ai/{models,confidence,api,model-jaggedness/jev-1.13}.md`
(fetched directly, same date) and our own measured evidence in
`docs/research/jev-pi-routing.md` §5a (207–258 ms latency, 5 synthetic live
calls, official $0.042/Mtok input price vs. Pi's bundled catalog's incorrect
$0 for the direct `typesafe` route).

This is a **demo/teaching lab** (a Vue "lab" UI plus a `pi`-based agent
sandbox), not a production library — the README says so itself ("Your
numbers will move a little from run to run") and ships a candid "Where it can
still fail" section. The review below treats it as such: good pedagogy,
several design choices we'd tighten before touching real repos or real
quota, and one or two claims worth independently verifying rather than
reusing.

## Where we agree

- **The core framing (levels 1–5: code calls Jev; 6–10: Jev inside the
  agent, as hooks then as tools) matches our own §3 routing map.** Their
  level 5 "intent/model router" and our proposed use of Jev to pick
  `PI_LLM_CLASS` (`jev-pi-routing.md` §3.1) are the same idea, independently
  arrived at. Agreement, not just citation.
- **Confidence-gated decisions (level 4) are the right pattern and match
  official docs exactly**: `(n·peak − 1)/(n − 1)` for `choice`, a bare
  probability with no separate `confidence` for `bool`/`noul`
  ([`docs.typesafe.ai/confidence.md`](https://docs.typesafe.ai/confidence.md)).
  Their three-tier design (floor → ask a human, ceiling → act without
  confirmation, middle → confirm) is a sound, reusable pattern we did not
  have in our own report.
- **`core/client.ts`'s cost handling is strictly better than Pi's bundled
  catalog.** It never assumes a price: `resultCost()` trusts
  `response.usage.cost` only if the wire response actually reports one,
  else falls back to caller-supplied `pricing` ("estimated"), else returns
  `{ amount: null, source: "unknown" }` — never a silent `$0`
  (`src/core/client.ts:260-268`). Our own live test confirmed TypeSafe's
  wire response has **no `cost` field at all** (`usage: { input_tokens,
  output_tokens }` only, matching `docs.typesafe.ai/api.md`), so this
  library's "unknown unless proven" default is the correct posture — and it
  is a direct, concrete rebuke of Pi 0.99.1's catalog entry, which hardcodes
  `cost.input: 0` for the direct route and therefore *always* reports $0,
  never "unknown." We're updating our own recommendation (§5a of
  `jev-pi-routing.md`) to flag this explicitly: treat Pi's `/session` dollar
  figure for `typesafe/jev-latest` as untrustworthy, compute from
  `usage.input_tokens` and the official rate instead.
- **Level 9's cost story (`$0.00049` to judge two files vs. `$0.091` to read
  them at an expensive model's input price, "187x") is internally
  consistent with official per-token pricing** ($0.042/Mtok input, free
  output) applied to the 9,089 tokens they report. We did not re-derive it
  independently (would need the comparison model's own price, not supplied
  in the quoted figure), but the arithmetic direction is correct: a
  narrow-schema decision call is much cheaper than paying full input price
  for an entire file on every turn until compaction.
- **The "Where it can still fail" section is honest and we'd cite it
  directly rather than paraphrase it**: Level 6 option B was bypassed in a
  live run (agent wrote the blocked file via a bash heredoc instead of the
  gated write tool) until the block notice was changed to explicitly forbid
  working around it — which the README itself says "is an instruction, not
  a control." This is the single most important sentence in the repo for
  our purposes: **a Jev-gated hook is advisory to a cooperative agent, not
  a security boundary**, exactly the caveat our own `jev-pi-routing.md` §3
  draws around `claude-token-proxy`'s hard gates. Their guidance — load all
  three gates together and still treat the combination "as one signal among
  several" — is the right level of trust.
- **Official docs independently confirm a risk the repo only hints at**:
  [`docs.typesafe.ai/model-jaggedness/jev-1.13.md`](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md)
  §"Adversarial content" states verbatim: *"State is data, and `jev-1.13`
  does not treat it as hostile by default. Content written to adversarially
  steer the model, whether that is an injected instruction, a deliberately
  misleading framing, or text that argues for its own classification, can
  move the answer."* This directly undercuts Level 6 option C (the
  "result screen," which uses Jev itself to detect whether a tool result
  contains a prompt injection aimed at the agent) — the detector is built
  on a model TypeSafe's own docs say is not hardened against exactly that
  attack. Using one unhardened classifier to police content for another
  model is a weaker control than the repo's framing ("the agent still sees
  the file, marked as data") implies.

## Where we'd push back or add caveats

- **`report.ts` logs the full `state` it sent Jev — including raw file
  content — to stderr and to the permanent pi session file, on every call**
  (`extensions/report.ts:41-45`: `report(pi, "jev", { source, state,
  questions, answers, usage, model, ms, ...extra })`, where `report()`
  writes `process.stderr.write("JEV_EVENT " + JSON.stringify(body))` and
  calls `pi.appendEntry(...)`). Level 8/9's entire pitch is "the agent gets
  a typed answer and never the file" — true for the *agent's context
  window*, but false for the session transcript and any log aggregator
  reading stderr. Anyone who treats "Jev never sees/keeps the file" as a
  privacy property for the *operator* (not just the agent) is wrong; the
  file content is written to disk and to a log stream regardless. For our
  stack this matters directly: `claude-token-proxy`'s own design principle
  is "tokens are never logged" (`bin/claude-token-proxy` docstring) — this
  repo's logging-every-Jev-call pattern does not meet that bar and would
  need redaction before reuse.
- **`extensions/report.ts:16` hardcodes `provider: "openrouter"`
  (`new JevClient({ provider: "openrouter" })`) for every level-6–10 agent
  session, regardless of whether a direct `TYPESAFE_API_KEY` is configured.**
  `.env.sample` lists both `TYPESAFE_API_KEY` and `OPENROUTER_API_KEY`, and
  `core/client.ts`'s own `selectProvider()` would prefer `typesafe` first if
  asked to auto-select — but the agent-harness levels never ask it to;
  they're pinned to OpenRouter. This is a real inconsistency worth noting
  if someone adopts this code: levels 1–5 (the "from code" lab) can use
  either provider, but levels 6–10 (the agent-integrated half — the half
  most relevant to a Pi-based stack like ours) always pay OpenRouter's
  markup/routing, never the direct TypeSafe price, with no visible flag to
  change it short of editing the extension.
- **Level 9's path containment is lexical, not realpath-based, and does not
  exclude dotfiles/secrets by name.** `prune.ts`'s `pruneFiles()`
  (`src/levels/level09/prune.ts:38-52`) checks `relative(cwd, full)` for a
  leading `..` to reject "outside the repo," and `readFileState()`
  (`src/levels/level08/read-state.ts:29-43`) calls `stat`/`readFile` on the
  resolved path — both of which **follow symlinks** in Node by default. A
  symlink placed inside the watched tree whose target resolves outside it
  (e.g. `ln -s /etc/passwd sandbox/notes.txt`) passes the "outside the
  repo" check (the symlink's own path is inside `cwd`) and then has its
  *target's* content read and sent to Jev as `state`. Nothing in `prune.ts`
  or `read-state.ts` calls `realpath`/`lstat` to detect or refuse a
  symlink before reading through it. Separately, the only file-type
  filtering is a fixed binary/lock-file extension list
  (`\.(png|jpe?g|gif|...|lock)$`) — there is no `.env`/credentials/dotfile
  exclusion, so a `.env` sitting in a globbed directory would be read,
  trimmed, and sent to Jev as `state` like any other text file unless the
  caller's glob pattern happens to avoid it. (Level 6's *write* gate does
  separately classify content for secrets before writing — that is a
  different code path and does not protect level 8/9 *reads*.) Concurrency
  of 16 in-flight calls (`askFiles(..., opts.concurrency ?? 16)`) amplifies
  this: a recursive glob over an unfamiliar tree can fan out to many
  external reads in parallel before a human notices. Any port of this
  pattern into our stack needs an explicit path-realpath check plus a
  secret/dotfile denylist before file content is allowed into a `state`
  field headed to a fourth-party provider.
- **Level 6's bash gate has a confidence gap, not just a bypass gap.**
  `gateBash()` (`src/levels/level06/bash-gate.ts:40-47`) blocks only when
  `effect.choice === "irreversible"` **and** `effect.confidence >= 0.6`, or
  when `destructive_intent.noul >= 0.7`. A command Jev picks as
  `irreversible` but with *low* confidence (e.g. 0.4) and a
  `destructive_intent` just under 0.7 is **allowed to run**, with no
  "ask a human" middle tier the way level 4's `confidence.ts` (floor 0.5 /
  ceiling 0.9) has. Level 4 and level 6 ship inconsistent confidence
  postures for the same kind of decision (is this command safe?) — level 4
  is the better pattern and level 6 should arguably reuse it rather than a
  bare block/allow.
- **Level 7's "should I compact" is advisory to the agent, not a snapshot
  mechanism, and that is the correct scope — but the specific signals can
  misfire in a way that costs context, not safety.** A false `false` on
  `mid_operation` (agent judged as "a clean point" while it is actually
  mid-way through a half-applied multi-file edit) would let a compaction
  proceed and discard state the next step needs; the repo's own three-tier
  design (notice/recommend/request, never silent auto-compact) bounds the
  blast radius to "the agent or user still decides," which is the right
  mitigation — but it depends entirely on who's driving (a human watching
  the lab UI vs. an unattended loop that auto-accepts "request" tier). We
  did not find, and the README does not claim, any mechanism that verifies
  the chosen cut point actually preserves what the next step needs; it is
  a probability-weighted guess, same caveat as every other level.
- **Cost comparisons in the README ($3,500 vs. $525 vs. $16.80 per million
  calls; the 187x file-read figure) are per-call, single-request
  counterfactuals.** They do not account for prompt caching (several of the
  "expensive SOTA model" comparisons would be materially cheaper with
  cache-hit pricing on a repeated file or system prompt), nor for the fact
  that our own stack's primary cost lever is **subscription quota
  (Anthropic OAuth pool, ChatGPT/Codex plan, DeepSeek balance via
  `claude-token-proxy`), not metered per-token billing** — see
  `jev-pi-routing.md` §4's "Quota vs inference spend" row. A Jev call is
  cheap in absolute metered-dollar terms, but it is **a new, separate
  metered spend on a provider our stack does not otherwise pay at all**,
  not a discount against quota we're already consuming. The repo's cost
  framing is correct for "should I call an LLM at all for this decision,"
  and not directly comparable to "does this reduce my Anthropic/Codex/
  DeepSeek quota pressure" (it does, indirectly, only to the extent it
  avoids a chat-model turn that would otherwise have consumed that quota).

## Demo vs. production — our classification

| Level | Demo-quality as shipped | Production-ready for our stack, with changes noted |
|---|---|---|
| 1–3 (single decisions, choice, scoring) | Yes, directly | Yes — closest to drop-in; thin wrappers around `classify()`, no agent integration risk |
| 4 (confidence gating) | Yes | Yes — best pattern in the repo; reuse the three-tier floor/ceiling design everywhere, including level 6 |
| 5 (intent/model routing) | Yes | **Our best candidate**, matches our own §3.1/§3.2 proposal (choosing `PI_LLM_CLASS` or a virtual-model tier). Needs the OpenRouter-pinning and cost-ledger issues above fixed first |
| 6 (guardrail hooks) | Yes, and candid about its own limits | **Not a security boundary** — their own README says so. Usable as a soft nudge/second opinion only, never the sole gate, and needs level 4's confidence floor merged in |
| 7 (should-compact) | Yes | Plausible for us (matches our speculative §3 item on compaction advice), but unverified beyond the demo; would need real-session testing before trusting the cut-point choice |
| 8–9 (cheap file reads, files at scale) | Yes | **Our other best candidate** (candidate-file triage), but only after: realpath/symlink check, a secrets/dotfile denylist, and moving the `report()` logging out of a plaintext/stderr side channel |
| 10 (agentic Jev) | Yes, explicitly experimental ("the agent decides") | Not recommended yet for us — least predictable cost/behavior, and the README itself frames it as the most exploratory level |

This matches the brief's hunch: task classification/routing (4–5) and
file-candidate triage (8–9) are the strongest fits for our stack;
compaction advice (7) is plausible but unverified; none of the levels,
including 6, should be read as a security boundary.

## Verified offline (no network, synthetic fixtures only)

An offline probe (`~/.cache/jev-research/offline-review-probe.mjs`, synthetic
files, no network calls, run in parallel by the parent during this review)
reproduces four of the findings above directly against the cloned source,
rather than by inspection alone:

- `readFileState("../outside.txt", cwd)` is **accepted** — confirms the
  lexical-only containment gap carries into level 8's single-file read path
  too, not just level 9's glob path noted above.
- `pruneFiles()` **keeps** both a symlink pointing outside the pruned root
  and a `.env` file in its filtered output — confirms the symlink-escape and
  missing-secrets-denylist findings above with an actual pass/fail run
  against this repo's code, not just a code reading.
- `gateBash({ effect: irreversible @ 0.4, destructive_intent: 0.6 })`
  returns `{ block: false }` — confirms the confidence-gap finding above
  with the exact boundary values (just under both the 0.6 irreversible and
  0.7 destructive thresholds) rather than an inferred range.
- `decideModel(fast, confidence 0)` returns `{ model: "fast" }` — confirms
  model-router has no abstention path: a zero-confidence answer is treated
  identically to a certain one, with nothing in `decideModel()`'s signature
  or return type to distinguish them.

These are measured reproductions against the actual cloned code (offline,
synthetic inputs, no credentials, no network), not just static reading, and
they match this review's independent code-level analysis above exactly.

## Minimal opt-in implementation sequence, tied to our actual files

Builds directly on `docs/research/jev-pi-routing.md` §5 (unchanged
recommendation, still observe-only, still no routing mutation) with the
fixes this review surfaces folded in:

1. **Keep §5's bounded, observe-only `delegate.sh`-class classification
   experiment as step one** — no change from the prior report.
2. **When/if that graduates past observation, borrow level 4's confidence
   tiers, not level 6's binary gate.** Any future escalation decision (e.g.
   whether to auto-set `PI_LLM_CLASS_ESCALATE=1`, read in
   `anthropic-pool.ts:120`) should use a floor/ceiling pattern, never a
   single block/allow threshold.
3. **If file-candidate triage (levels 8–9 pattern) is ever explored against
   real repo content — not in scope for this review's budget, and not
   something we'd greenlight without a separate pass — it must add, before
   any file content leaves the machine**: (a) a `fs.realpath`/`lstat`
   check that rejects any path whose resolved target escapes the intended
   root, not just a lexical `..` check; (b) a denylist for `.env`,
   `.pi/agent/auth.json`, `cctoken`, and anything else our own
   `config/git/ignore`/pre-commit secret patterns already treat as
   sensitive; (c) no `report()`-style full-`state`-to-stderr logging —
   log only the question id, the answer, and a redacted/length-only
   description of what was sent, matching `claude-token-proxy`'s existing
   "tokens are never logged" bar.
4. **Any Jev cost accounting we eventually build must not trust a client's
   catalog-default price.** Follow `core/client.ts`'s own pattern: trust a
   wire-reported `usage.cost` if present (it currently is not, per our
   live test), else compute from `usage.input_tokens` and a value we
   hardcode from the official $0.042/Mtok page ourselves, else mark cost
   `unknown` — never default to `$0`.
5. **Do not adopt Level 6 as a security control at any point.** If a
   bash/write gate is ever wired into our Pi extensions, it sits next to
   `claude-token-proxy`'s existing server-side gates as one more soft
   signal, with the same "this block is final, do not route around it"
   notice this repo had to add after an agent bypassed it — and still
   backstopped by a deterministic denylist for the handful of commands
   that must never run unconfirmed, the way level 4's `confidence.ts`
   backstops judgment with a hard floor.

## Sources

- https://github.com/disler/ten-levels-of-jev @ `777adaf47d37ae0553220d35b2f15b3a3a063305`
  — `README.md`; `apps/ten-levels/src/core/client.ts`; `apps/ten-levels/src/core/types.ts`;
  `apps/ten-levels/src/levels/level04/confidence.ts`;
  `apps/ten-levels/src/levels/level05/model-router.ts`;
  `apps/ten-levels/src/levels/level06/{bash-gate,write-gate}.ts`;
  `apps/ten-levels/src/levels/level07/should-compact.ts`;
  `apps/ten-levels/src/levels/level08/read-state.ts`;
  `apps/ten-levels/src/levels/level09/{ask-files,prune}.ts`;
  `apps/ten-levels/extensions/report.ts`.
- https://docs.typesafe.ai/models.md, /api.md, /confidence.md,
  /model-jaggedness/jev-1.13.md — fetched directly 2026-10-02, no search
  engine, no credentials.
- `docs/research/jev-pi-routing.md` (this worktree) §3–§5a — our own prior
  routing map, comparison framework, and measured live-test evidence,
  cited throughout rather than restated.
