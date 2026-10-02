# Jev classification for Pi quota routing — research

Status: research only, no code changed, no API calls made, no credentials read.
Repo state at time of writing: installed Pi `0.99.1` (same version for
`@earendil-works/pi-coding-agent` and its `@earendil-works/pi-ai` dependency),
worktree branch `research/jev-pi-routing`, checked out from `$DOTFILES` at the
commit visible in `git log` (`3811447 docs(llm): record utilization plan and
research` at HEAD). All source citations below are to files under
`/home/gustaf/.local/share/npm/lib/node_modules/@earendil-works/pi-coding-agent`
(installed package, not the public GitHub repo — no network fetch was needed
or attempted) and to the files in this worktree. Access/read date for all
local files: 2026-10-02.

No web fetch was performed for TypeSafe's own documentation (typesafe.ai) or
JevBench; the installed Pi docs describe the integration in enough depth for
this task, and the brief says not to run classifier requests or spend budget
chasing search engines. Anything attributed to TypeSafe's hosted service that
is not visible in Pi's bundled model catalog or docs is flagged **[unverified
externally]** below.

## 1. Jev's actual contract

### 1.1 What it is, per Pi's docs and bundled catalog

Source: `docs/models.md:105-134`, `docs/llama-cpp.md:89-96`,
`docs/virtual-models.md:112-114`, `examples/extensions/jev-router.ts`.

- Jev is TypeSafe's **classifier** model family. Classifier models "do not
  chat" — they take a JSON `state` object plus a set of typed `questions` and
  return typed `answers`, each with a probability/confidence, never free text.
- Three question types, from `dist/types.d.ts:448-466` in the bundled
  `@earendil-works/pi-ai` package:
  - `choice`: named `criteria` (option → description); answer is `{ choice,
    probabilities: Record<option, number>, confidence }`.
  - `score`: `criteria` is an ordered list of levels; answer is `{ score,
    confidence }` (expected level, not necessarily an integer).
  - `bool`: `criteria: { true, false }`; answer is `{ probability }` (no
    `confidence` field — probability itself is the only signal).
- Result envelope (`ClassifierResult`, `dist/types.d.ts:488-496`): `api`,
  `provider`, `model`, `answers`, `usage?`, `stopReason:
  "stop"|"error"|"aborted"`, `errorMessage?`, `timestamp`. Code must check
  `stopReason === "stop"` before trusting `answers` — `jev-router.ts:76` does
  exactly this (`result.stopReason === "stop" ? result.answers.complexity :
  undefined`).
- Confidence/calibration, from `docs/llama-cpp.md:93`: "Raw label
  probabilities are usually overconfident." This statement is made in the
  llama.cpp-local-classifier section, describing Pi's *own* token-probability
  read-out mechanism (see 1.3), but the same caveat is the only calibration
  guidance Pi's docs give for Jev's hosted probabilities too — there is no
  separate calibration doc for the hosted service. A `temperature` option
  divides logits before normalizing, for local classifiers only.
- No documented confidence threshold or abstention convention is provided by
  Pi; any threshold (e.g. "treat confidence < 0.6 as abstain") is a caller's
  own policy, not something Jev or Pi enforces. `jev-router.ts:78` uses a bare
  `>= 0.5` probability cutoff with no abstain path — if the score is missing
  or `stopReason !== "stop"` it silently falls back to the cheaper model
  (`TERRA`), which is the closest thing to a documented "failure fallback"
  pattern in the source tree.

### 1.2 Providers, model IDs, auth, and current catalog prices

From `docs/models.md:109-113`, cross-checked against the bundled per-provider
catalog JSON (`node_modules/@earendil-works/pi-ai/dist/providers/data/*.json`,
read directly — these are Pi's own shipped price tables, not live API
queries):

| Provider | Model ID(s) | Auth | Catalog `cost` (per docs: "token counts … at the model's catalog price") | contextWindow |
|---|---|---|---|---|
| `typesafe` | `jev-latest` | `TYPESAFE_API_KEY` | input 0, output 0, cacheRead 0, cacheWrite 0 | 64,000 |
| `openrouter` | `typesafe/jev-1.13`, `~typesafe/jev-latest` | `OPENROUTER_API_KEY` or `/login` | input 0.042, output 0 | 32,000 |
| `cloudflare-workers-ai` | `typesafe/jev` | `CLOUDFLARE_API_KEY` + `CLOUDFLARE_ACCOUNT_ID` | input 0, output 0 | 32,000 |
| `vercel-ai-gateway` | `typesafe-ai/jev` | `AI_GATEWAY_API_KEY` | input 0.042, output 0 | 32,000 |
| `opencode` | `jev-1.13` | `OPENCODE_API_KEY` | input 0.042, output 0 | 32,000 |
| `opencode` | `jev-1.13-free` | `OPENCODE_API_KEY` | input 0, output 0 | 32,000 |

Cost units follow Pi's catalog convention for chat models in the same files
(USD per 1M input tokens; `cacheRead`/`cacheWrite` are always 0 here because
classifiers are not documented to support prompt caching). **The $0.042/1M
input figure and the "free" rows are Pi's bundled catalog price table at
0.99.1, not a live TypeSafe or OpenRouter price page — flag as
potentially-stale, re-check before relying on it for budget decisions.**
Direct `typesafe/jev-latest` and the Cloudflare Workers AI route are priced at
$0 in this table; `docs/models.md:134` independently confirms "models without
[a catalog price], such as TypeSafe's direct `jev-latest`, report tokens at no
cost" — i.e. the zero price for the direct route is a documented, not
incidental, fact. **None of these five credentials (`TYPESAFE_API_KEY`,
`OPENROUTER_API_KEY`, `CLOUDFLARE_API_KEY`/`CLOUDFLARE_ACCOUNT_ID`,
`AI_GATEWAY_API_KEY`, `OPENCODE_API_KEY`) exist in this environment** (checked
`env | grep -i "TYPESAFE\|OPENROUTER"`, empty; no secret file names reference
TypeSafe). Any Jev use requires provisioning one of these from scratch; this
research does not recommend which.

### 1.3 Hosted Jev vs local llama.cpp classification

`docs/llama-cpp.md:89-96`: when Pi is paired with a llama.cpp router, every
loaded *chat* model is **also** listed as a classifier model under the same ID
and the `llama-cpp-classify` API — this is not Jev, it is Pi's own
token-probability read-out applied to whatever local chat model is loaded.
Mechanism: each question becomes one chat prompt (state, questions, state
again, then the question with single-token answer labels); Pi reads the
logits of the label tokens as the next token and normalizes them into
probabilities; a `choice` confidence is `(n·peak − 1)/(n − 1)`, a `score`
returns the expected level. This is architecturally distinct from hosted
Jev (a purpose-trained "System One" classifier service — `typesafe-system-one`
/ `cloudflare-workers-ai-system-one` APIs, see `dist/api/system-one-shared.d.ts`)
but exposes an **identical TypeScript contract** (`ClassifierModel`,
`classify()`, `ClassifierResult`), so the same calling code in an extension or
codemode script works against either without change — only the model lookup
(`findOfType("classifier", provider, id)`) differs. This matters for the
dotfiles stack: there is no local llama.cpp router configured here
(`config/pi/` has no `llama-cpp` reference found), so "local classification"
is a theoretical zero-marginal-cost alternative to hosted Jev, not a thing
currently running.

### 1.4 Limits

- Classifier models never appear in `/model`, `--model`, or chat; they are
  only reachable via `codemode` scripts (`models.classify(...)`) or an
  extension's `ctx.modelRegistry.classify()` (`docs/models.md:117,136`).
  `codemode` itself is **off by default** and needs `"defaultTools":
  ["+codemode"]` in settings (`docs/cli.md:148-156`) or an MCP server that
  turns it on. `config/pi/settings.example.json` in this repo has no
  `defaultTools` entry at all, so **codemode is not enabled anywhere in the
  dotfiles Pi config today** — grepped `config/pi/settings.json` (does not
  exist; only `settings.example.json` is checked in) for `codemode`/
  `defaultTools`, no match.
- Codemode scripts are capped at **4 concurrent `classify()` calls per
  script** (`docs/cli.md:178`: "classify(model, context) runs a classifier
  model with the session's credentials, at most four at a time per script").
- A classifier call from a virtual-model `route()` "adds latency before the
  first token of the turn" (`docs/virtual-models.md:112`) — it is a
  synchronous pre-step on the critical path of every routed request unless
  the router special-cases it away (e.g. `jev-router.ts` only classifies once,
  on the first request of a session, then caches the decision in router
  `state`).
- `ClassifierContext.state` must be JSON-serializable (`dist/types.d.ts:467`);
  there is no mention of server-side redaction, so whatever is put in `state`
  is sent to whichever provider serves the chosen Jev model id — see §4
  (prompt privacy).

## 2. Installed Pi's classifier/routing surface — the only three seams

### 2.1 `models.classify()` — codemode script seam

`docs/models.md:117-134`. Available to a `codemode` script, gated behind
`defaultTools: ["+codemode"]`. Lists classifiers with
`models.getAvailableOfType("classifier")` / `models.getModelOfType("classifier",
provider, id)`, then `models.classify(model, { state, questions })`. Usage is
billed into the session's cost ledger: "Pi adds the usage of a script's
classifier calls to the `codemode` tool result, so it counts toward the
session cost in the footer and `/session`." This is the only seam that is
**visible to the end user in `/session` by design**.

### 2.2 `ctx.modelRegistry.classify()` — extension seam

`docs/models.md:136`, `docs/virtual-models.md:112`. Any extension (e.g. a
`turn_start`/`before_provider_headers` hook like `llm-failover.ts` or
`anthropic-pool.ts` already use) can call `ctx.modelRegistry.classify(model,
context, options)` directly, without codemode, and without it necessarily
reaching the session cost ledger the same way (the docs only state the
session-cost attribution for the codemode path — the extension path's
cost/usage accounting is not spelled out in the docs I read; **flag as
unverified**: does `ctx.modelRegistry.classify()` outside codemode also add to
`/session` cost? Not stated either way in `models.md` or `virtual-models.md`).
`options` includes `signal` (abort) per `ClassifierOptions extends
ProviderRequestOptions<...>` (`dist/types.d.ts:221`).

### 2.3 Virtual model `route()` — the routing seam

`docs/virtual-models.md:1-114`. `pi.registerVirtualModel({ provider, id,
thinkingLevels, route(request, ctx) { ... } })` registers a model that
appears in `/model` like any other; its `route()` runs before every request
and returns `{ model, thinkingLevel, state? }` where `model` must be a
*physical* model from `ctx.modelRegistry` (a virtual model cannot route to
another virtual model, `docs/virtual-models.md:86`). `request.reason` is one
of `user | continuation | retry | direct`; `request.previous` / `request.failed`
carry the last successful / last failed dispatch so the router can preserve
prompt cache and thinking signatures across turns. `request.state` round-trips
classifier verdicts or routing phase across requests on the same session
branch, survives compaction and forks (`docs/virtual-models.md:88-103`).
**`jev-router.ts` is the only reference implementation shipped** (examples
directory) and it classifies **once per session** (new session ⇒ no
`request.state` ⇒ call Jev; afterwards reuse the cached `model` in `state`),
specifically to bound the added latency/cost to one call per session rather
than one per turn.

### 2.4 What is *not* a seam

Jev/`codemode`/virtual models are entirely orthogonal to today's
`CC_PROXY_CLASS` task-class mechanism (`x-cc-proxy-class` header, `PI_LLM_CLASS`
env var) described below — nothing in the installed Pi source reads or writes
`PI_LLM_CLASS`, `classes.json`, or `claude-token-proxy`'s `/_route`. Any
integration is something this stack would have to build; Pi ships no
"classifier chooses task class" feature.

## 3. Current routing/data flow, with file:line references

```
pi (interactive)            delegate.sh --class <cls>         ralph loop.sh
  PI_LLM_CLASS=interactive    PI_LLM_CLASS=$CLASS (default        RALPH_CLASS (default build,
  (anthropic-pool.ts:119        build, delegate.sh:35)              mechanical for lint/fmt)
   default fallback)                                                → export PI_LLM_CLASS
        |                              |                                   |
        +------------------------------+-----------------------------------+
                                        |
                          anthropic-pool.ts:119  (CLASS_HEADER = "x-cc-proxy-class")
                          sets x-cc-proxy-class: $PI_LLM_CLASS on every Anthropic-bound
                          request header (before_provider_headers hook)
                                        |
                                        v
                    bin/claude-token-proxy  (local HTTP proxy in front of Anthropic)
                      - reads x-cc-proxy-class (claude-token-proxy:2058)
                      - escalated_class() if x-cc-proxy-class-escalate=1 (:2060,:1377-1384)
                      - class_eligible()/pick() apply a per-class Anthropic
                        "oi" (overage-included) ceiling from classes.json
                        (:1386-1396, :1396-1410)
                      - rank_pool()/route_payload() answer GET /_route?class=
                        (:1451, :1741-1775), used by llm-schedule and by
                        delegate.sh to pick a preferred provider/model
                      - record_request()/add_usage() tag per-class usage
                        buckets (:716-765), exposed via GET /_usage
                                        |
                                        v
                 config/llm-proxy/classes.json  (interactive/build/research/
                 mechanical; each a route list + optional Anthropic ceiling)
                 config/llm-proxy/routes.json   (cross-provider equivalence
                 table: claude-model -> [[provider, model], ...] fallbacks)
```

Where Jev *could* plug in, without breaking any hard gate:

1. **Choosing the task class** (`PI_LLM_CLASS`) instead of a static
   `--class build` default in `delegate.sh:35` or `RALPH_CLASS` in
   `ralph/llm-utilization/loop.sh:7-8`. A classifier call on the task
   prompt (`choice` between `mechanical`/`research`/`build`/`interactive`,
   mirroring `classes.json`'s own categories) could set the env var before
   the child `pi` process starts. This is a **pre-dispatch, one-shot**
   decision — it never touches the proxy's live quota state, so it cannot
   violate a hard gate; worst case it picks a too-expensive or too-cheap
   class for the work.
2. **Choosing capability tier within a class**, analogous to
   `jev-router.ts`'s complexity classification, e.g. inside a `route()` for
   a new `pi/auto`-style virtual model layered *above* the existing
   `anthropic-pool.ts` + `claude-token-proxy` stack. This is the closest
   match to the shipped example and the best-understood failure mode
   (`jev-router.ts:67-70`: "Keep a planning model the session already uses,
   so switching to jev/auto costs no cache miss" / falls back to the cheap
   model when Jev is unreachable).
3. **Explicit escalation** (`PI_LLM_CLASS_ESCALATE=1`, read in
   `anthropic-pool.ts:120`, acted on by `escalated_class()` in
   `claude-token-proxy:1377-1384`) is already a one-step, proxy-enforced
   lift (`mechanical → research → build → interactive`). A classifier could
   decide *when* to set this flag (e.g. "this mechanical job is actually
   hard, escalate once") rather than a human or a fixed rule — again
   pre-dispatch, not a live quota override.
4. **Scheduling** (`bin/llm-schedule`, `bin/llm-wait`): these already consult
   `/_route` and `/_usage` for hard availability before running a job. A
   classifier could annotate a queued job with an estimated class/cost
   *before* enqueueing, but `llm-schedule`'s `reason()` function
   (`bin/llm-schedule:33-55`) already does deterministic windowing against
   real usage data — there is no gap here that calibration-poor probability
   output would improve, and doing so would add a dependency on an external
   paid service to a component whose entire purpose is avoiding paid
   fallback.

**Hard gates that must stay out of Jev's reach**, all enforced server-side in
`bin/claude-token-proxy`, never by a client-sent class or model string:
- `class_eligible()` / per-class Anthropic `oi_max_used` ceiling
  (`claude-token-proxy:1386-1396`) — classes.json values, not negotiable by a
  classifier choosing a *different* class value.
- `pick()`'s token selection, cooldowns, `MIN_VALID` warnings
  (`claude-token-proxy:1396-1451`) — entirely server-side state.
- DeepSeek passthrough gates (`CC_PROXY_DEEPSEEK_MIN_BALANCE`,
  `is_available`, opt-in `CC_PROXY_DEEPSEEK_FALLBACK`) — unaffected by
  classification; a classifier can only ever pick *which class/model to ask
  for*, never bypass the proxy's own quota arithmetic. Any Jev integration
  must therefore be upstream of the proxy (choosing what header value to
  send) and never attempt to read or write proxy state directly.

## 4. Deterministic baseline vs Jev-assisted — comparison

| Dimension | Deterministic baseline (today) | Jev-assisted |
|---|---|---|
| Decision basis | Fixed defaults (`--class build`, `RALPH_CLASS`) or explicit human flag | LLM-probability judgment of task-prompt text |
| Confidence/abstention | N/A — deterministic | Docs give no abstention convention; `jev-router.ts` uses a bare `>=0.5` threshold with silent fallback, not abstain-and-ask |
| Latency | Zero added latency | One classify call before first token (`docs/virtual-models.md:112`); amortizable to once-per-session like `jev-router.ts` |
| Per-decision cost | $0 | $0 on `typesafe/jev-latest` direct or `cloudflare-workers-ai` route (catalog price 0); ~$0.042/1M input tokens on openrouter/vercel-ai-gateway/opencode paid route, input only (state+questions text, typically well under 1K tokens per call ⇒ sub-cent per decision even on the paid routes) |
| Cache keys | N/A | None documented for classifiers (`cacheRead`/`cacheWrite` always 0 in the catalog); every call is a fresh request — a local cache keyed on a hash of `(state, questions)` would be the caller's own responsibility |
| Prompt privacy / token custody | Task prompt only goes to the already-chosen provider (Anthropic/Codex/DeepSeek) | Classifying "is this task complex" requires sending (at least a prefix of) the task prompt to **a fourth party** (TypeSafe directly, or via OpenRouter/Cloudflare/Vercel/OpenCode) before the real provider is even chosen — a new data-custody surface that does not exist today. `jev-router.ts:69` truncates to `.slice(0, 16_000)` chars, which still leaves meaningful prompt content exposed |
| Prompt injection | N/A | `docs/llama-cpp.md:95` (stated for local classifiers, same contract applies): "Small models may follow instructions written inside the state. The prompt tells the model to judge the state as data, but that is not a guarantee." A classified task prompt that contains attacker-controlled text (e.g. delegated web content) could attempt to manipulate the classifier's own verdict |
| Failure fallback | N/A | Must be designed: `jev-router.ts:67,78` falls back to a fixed cheaper model when Jev is unreachable or `stopReason !== "stop"` — this pattern generalizes (fall back to the existing static default class) |
| Observability | `/_usage`, `/_route`, `routing.*` counters in `claude-token-proxy`, already class-aware | A classifier's own `usage`/cost, if captured, surfaces only in Pi's own `/session` footer (codemode path) per `docs/models.md:134`; it is a **separate spend ledger from `claude-token-proxy`'s `/_usage`**, specifically for a different provider (TypeSafe/OpenRouter/etc., not Anthropic/Codex/DeepSeek) — nothing in `bin/llm-schedule`, `bin/llm-wait`, or `scripts/llm_usage.py` is aware of it, so a Jev integration adds an invisible-to-today's-tooling cost unless explicitly wired into `/_usage`'s own JSON or a parallel ledger |
| Quota vs inference spend | Single concept: Anthropic weekly/5h buckets, Codex/DeepSeek balance, all read-only polled into `/_usage` | Two distinct concepts that must not be conflated: (a) the chosen class/model's *existing* quota (Anthropic OAuth pool, Codex ChatGPT plan, DeepSeek balance — unaffected by Jev) and (b) **new, separate metered spend** on whichever Jev provider is used to make the decision. A regression here would be reporting Jev's own token cost as if it affected the pool it is routing *into* |
| Does classifier output override hard gates? | N/A | Must not, and nothing in Pi's source lets it: `route()` can only pick among models whose provider already has credentials (`docs/virtual-models.md:65`); it cannot touch `claude-token-proxy`'s cooldowns, ceilings, or DeepSeek balance gates (§3) |

## 5. Recommended smallest useful opt-in experiment

**Goal**: measure whether Jev's `complexity` classification (mirroring
`jev-router.ts`'s own question) correlates usefully with the `delegate.sh
--class` a human would have picked, **without changing any routing
behavior**.

### 5.1 Scope

- **Observe-only.** No `PI_LLM_CLASS` is ever set by the classifier result in
  this experiment; it is logged next to the human/default choice for later
  comparison. This directly satisfies "no auto route changes."
- **One provider, free tier only**: `typesafe/jev-latest` via direct
  `TYPESAFE_API_KEY`, or the `cloudflare-workers-ai` route if a Cloudflare
  account/key is already provisioned for other dotfiles tooling — both are
  catalog-priced at $0, so there is no new paid-API exposure (§1.2). Do
  **not** use the openrouter/vercel-ai-gateway/opencode paid routes for this
  experiment; they're the fallback only if the free routes turn out to be
  unavailable or rate-limited, and only with an explicit opt-in cost cap.
- **Codemode-gated, project-local only**: enable `"defaultTools":
  ["+codemode"]` in a project-scoped `.pi/settings.json` for a throwaway
  test session — never in `~/.pi/agent/settings.json` or this repo's
  `config/pi/settings.example.json` — so the experiment cannot change
  behavior for any other session.

### 5.2 Implementation plan (not executed here)

1. **New credential**: provision `TYPESAFE_API_KEY` (or a Cloudflare
   Workers AI key, if preferred) in `local/env/.env` per this repo's own
   local-config convention (`CLAUDE.md` → "Local/Private Configurations"),
   never in the shared dotfiles tree.
2. **One-off codemode script** (not an extension, to keep it fully opt-in
   and reviewable per invocation): a script invoked manually via `pi
   --tools read,bash,edit,write,codemode -e <script>` that:
   - Reads the last user message text (same truncation as `jev-router.ts`,
     16,000 chars) from the running session.
   - Calls `models.classify(jev, { state: { prompt }, questions: {
     task_class: { type: "choice", instructions: "...", criteria: {
     mechanical: "...", research: "...", build: "...", interactive: "..."
     } } } })`, mirroring `classes.json`'s four categories verbatim so the
     comparison is apples-to-apples.
   - Prints `{ choice, probabilities, confidence, stopReason, usage }` —
     nothing else; does not call `tools.bash` to set `PI_LLM_CLASS` or touch
     `delegate.sh`.
3. **Comparison harness**: for a sample of ~20 real `delegate.sh` invocations
   (replay their stored prompts, if available, or re-run manually), record
   the human-chosen `--class` next to Jev's `task_class` choice and
   `confidence`/`probabilities`. Store results as a flat CSV/JSONL in
   `.scratch` or a new `docs/research/` appendix, not in `/_usage` or any
   proxy-facing file.
4. **No service changes**: `claude-token-proxy`, `anthropic-pool.ts`,
   `llm-failover.ts`, `classes.json`, `routes.json` are untouched. No
   systemd unit restarted. No `--class`/`PI_LLM_CLASS` default changed.

### 5.3 Offline/live test and evaluation criteria

- **Offline**: unit-test the question/criteria text and the parsing of
  `ClassifierResult` (`stopReason`, missing `confidence`, `probabilities`
  summing near 1.0) against a few hand-built mock payloads, the same way
  `tests/unit/test_anthropic_pool.mjs` and `test_llm_failover.mjs` test pure
  functions without hitting a real process (per this repo's own testing
  convention) — this needs no network access and no spend.
- **Live, bounded**: a small number (e.g. ≤20) of real classify calls against
  the free `typesafe/jev-latest` or `cloudflare-workers-ai` route, each
  logged with input/output token counts and the catalog-implied cost (should
  be $0 on both routes; if a bill appears, stop immediately — that would
  mean the catalog price in §1.2 is stale or the account is actually on a
  paid tier).
- **Evaluation**: agreement rate between Jev's `task_class` and the human's
  `--class` on the sample; distribution of `confidence`/`probabilities` on
  agreements vs disagreements (does low confidence correlate with
  disagreement — i.e. is it calibrated enough to gate on?); latency added
  per call (wall-clock, from the `codemode` tool result's own timing); any
  cases where sending the prompt to TypeSafe/Cloudflare would have been a
  privacy concern (secrets, customer data) — if any appear in the sample,
  that alone is grounds to not proceed further without a redaction step.
- **Decision rule to progress past this experiment**: only propose wiring
  Jev into `delegate.sh`'s default `--class` selection (still as a
  suggestion a human/flag can override, never silently) if agreement rate is
  materially better than the current static `build` default would achieve
  against the same sample, *and* no privacy-sensitive prompt content was
  observed being sent off-box, *and* added latency is acceptable for an
  interactive delegation flow (sub-second to low-seconds, consistent with
  "adds latency before the first token" in §2.3).

### 5.4 Rollback and knobs

- Rollback is trivial by construction: nothing is wired into the running
  stack. Removing the throwaway `.pi/settings.json` codemode flag and the
  one-off script fully reverts the experiment.
- Knobs for a future opt-in (not built yet): an env var analogous to
  `PI_ANTHROPIC_POOL=off` (e.g. `PI_DELEGATE_JEV=off`, default off) would
  gate any eventual non-observational use exactly the way `anthropic-pool.ts`
  and `llm-failover.ts` already gate their own behavior — consistent with
  this stack's existing pattern of "notify/suggest, human or explicit flag
  decides."

## 5a. Empirical follow-up: authorized bounded live test (2026-10-02)

User supplied a TypeSafe API key (`/home/gustaf/.local/state/jev-research/api-key`,
0600 file in a 0700 directory, outside git) and explicitly authorized a small
live test. This section records what was actually measured, kept strictly
separate from the catalog claims in §1.2. The key was read only via shell
command substitution directly into a subprocess environment variable
(set from the private key file via shell command substitution into the
subprocess environment, as documented in `jev-test.mjs`'s own header); it was never
echoed, logged, written to a file, or included in any artifact. The private
key file itself was left in place for the parent to clean up, per instructions.

### Official pricing (verified before sending, supersedes §1.2's catalog-only claim)

Fetched directly from TypeSafe's own docs (`https://docs.typesafe.ai/models.md`,
`https://docs.typesafe.ai/api.md`, `https://docs.typesafe.ai/confidence.md`,
accessed 2026-10-02, no search engine involved):

- **`jev-1.13.0`** (alias `jev-latest`): **$42 per billion input tokens
  ($0.042/Mtok)**, **output tokens are free**. This is charged on every
  account, including direct API access — TypeSafe's docs make no mention of a
  free tier for the direct `api.typesafe.ai` endpoint.
- Rate limits: 100K tokens/sec and 40 requests/sec per account, explicitly
  called out as adjusting dynamically without notice.
- Context budget: 64k tokens total (`state` + all questions); 32k tokens for
  `state` plus the single longest question.
- Endpoint: `POST https://api.typesafe.ai/v1/systemone`, `Authorization:
  Bearer <key>`, body `{ state, model, questions }`. Response:
  `{ model, answers, usage: { input_tokens, output_tokens } }`. Wire-level
  question types are `noul` (yes/no), `choice`, `score` — confirming the
  `bool → noul` field rename already documented in Pi's own source comment
  (`typesafe-system-one.d.ts`: "public `bool` values mapped to wire-level
  `noul`").
- Errors: `401` (bad key), `422` (validation), `429` (rate limit), `529`
  (overloaded); SDKs retry 429/529 with backoff honoring `retry-after`.
- Confidence: officially documented as `(n·peak − 1)/(n − 1)` for `choice`
  (same formula Pi's `llama-cpp.md` uses for its local token-probability
  read-out, §1.3) and an analogous spread-based formula for `score`. `noul`/
  `bool` answers carry **no separate confidence field** — the probability
  itself is the only signal, and a value near 0.5 is TypeSafe's own
  documented definition of "the model is unsure." This is an **officially
  documented absence of an abstention mechanism**, not a gap in Pi's
  integration: callers must threshold `probability` (for bool) or
  `confidence` (for choice/score) themselves; TypeSafe's own docs say
  "Start with conservative thresholds, test with your own data, and adjust
  as you observe results" — i.e., there is no vendor-supplied default.

**Discrepancy found**: Pi's bundled catalog (§1.2,
`node_modules/@earendil-works/pi-ai/dist/providers/data/typesafe.json`) lists
`cost: { input: 0, output: 0, ... }` for the direct `typesafe/jev-latest`
route. TypeSafe's own docs say input is **not** free ($0.042/Mtok). The
measured test below confirms Pi's cost accounting reports `$0` for these
calls even though the real TypeSafe invoice (by their own published price)
would be nonzero. This is a **concrete, verified under-reporting risk** in
Pi 0.99.1's session/`/session` cost ledger for this specific provider route —
flag for whoever eventually wires Jev in: do not trust `/session`'s dollar
figure for `typesafe/jev-latest` classify calls; compute cost from
`usage.input`/`usage.output` and the official $0.042/Mtok rate instead. The
Cloudflare Workers AI route's advertised $0 and OpenCode's `jev-1.13-free`
were not tested and could not be checked against an independent official
price page in the time available — treat their "free" catalog entries with
the same skepticism until independently verified.

### Test method

Script: `docs/research/jev-test.mjs` (committed, credential-free, reusable —
reads `TYPESAFE_API_KEY` from the environment only, never a file path).
It imports `classify` directly from the **installed Pi package's own dist
file** (`.../pi-coding-agent/node_modules/@earendil-works/pi-ai/dist/api/typesafe-system-one.js`),
satisfying "use the installed Pi classifier API/provider implementation" —
this is not a reimplementation, it is the exact function `jev-router.ts` and
`models.classify()` call under the hood (traced in §2.1–2.2). The model
object passed in is a literal copy of Pi's own catalog entry for
`typesafe/jev-latest` (verified by `node -e "import(...).then(m =>
console.log(m.TYPESAFE_CLASSIFIER_MODELS))"` against the installed package).

Run: one unbilled `GET /v1/models` (confirms the key works, lists
`jev-latest`/`jev-preview` aliases with release dates — matches docs) followed
by exactly **5 billed `classify()` calls**, each a short synthetic prompt
(no real code, conversations, or task history), hard-capped in the script
itself (`MAX_BILLED_CALLS = 5`, throws rather than exceed it).

### Measured results (sanitized, reproduced in full — no secrets, no real data)

| Case | Question type | Input | Answer | Confidence/probability | Latency | input/output tokens | Pi-reported cost |
|---|---|---|---|---|---|---|---|
| `noul_clear_approval` | bool | "The change works, thanks." | `true`-leaning | probability **0.97** | 258 ms | 299 / 20 | $0 (see discrepancy above) |
| `noul_ambiguous` | bool | "It's fine I guess, not sure yet." | `true`-leaning but weak | probability **0.32** | 226 ms | 303 / 20 | $0 |
| `choice_task_class_clear` | choice (mechanical/research/build/interactive) | "Rename this variable from `x` to `count` across the file." | `mechanical` | probabilities `{mechanical:1, others:0}`, confidence **1.0** | 210 ms | 384 / 50 | $0 |
| `choice_task_class_ambiguous` | choice (same 4 options) | "Look into why it's slow sometimes and maybe fix it if it's easy." | `build` | probabilities `{build:0.58, research:0.42, mechanical:0, interactive:0}`, confidence **0.44** | 228 ms | 385 / 48 | $0 |
| `score_complexity` | score (Trivial/Standard/Complex) | "Add a retry with exponential backoff around one HTTP call." | score **0.84** (between Trivial=0 and Standard=1, close to Standard) | confidence **0.75** | 207 ms | 316 / 19 | $0 |

All five calls returned `stopReason: "stop"` (no errors, no aborts) and a
well-formed `usage: { input, output, cacheRead: 0, cacheWrite: 0, totalTokens,
cost }` object — **confirming `result.usage` is populated for this provider**,
answering the brief's question of whether the SDK output contains usage: yes,
structurally, every time, for all three question types. Whether that usage is
*displayed/accounted* in an actual Pi session footer or `/session` was **not**
verified here — this test called `classify()` directly, outside a running Pi
agent session, so no footer/`/session` was ever rendered to check against.
That remains exactly as flagged in §6: unverified whether `/session` picks up
an extension's direct `ctx.modelRegistry.classify()` cost the same way it
picks up a `codemode` script's. This test does not close that gap; it only
confirms the prerequisite (the raw `usage` object exists and is well-formed).

### Interpretation — explicitly not a calibration claim

Five requests is not a benchmark and no calibration conclusion is drawn.
What the ambiguous-input cases show is **directional plausibility**, nothing
more: the deliberately hedged bool prompt ("It's fine I guess, not sure yet")
scored lower (0.32) than the clear approval (0.97), and the deliberately
vague task description ("maybe fix it if it's easy") produced the lowest
choice confidence of the two choice cases (0.44 vs 1.0), split across two
plausible classes (`build`/`research`) rather than collapsing onto one. This
is consistent with §1.1's note that confidence is a usable *relative* signal,
not evidence that the probabilities are well-calibrated in the statistical
sense — that would require many labeled examples and is out of scope here.

### What this does and does not change in the recommendation

- No routing, defaults, or service state changed. `docs/research/jev-test.mjs`
  is a standalone, opt-in script; it is not wired into `delegate.sh`, any
  extension, `classes.json`, or `claude-token-proxy`.
- §5's recommended experiment stands, with one correction: budget estimates
  for a future larger pilot must use the **official $0.042/Mtok input price**,
  not the $0 catalog figure — e.g. 20 calls at ~350 input tokens each (this
  test's average) is ~7,000 tokens ≈ **$0.0003**, still negligible, but it is
  not contractually free as §1.2 alone would have implied.
- The pricing discrepancy itself (not the small dollar amount) is the most
  actionable new finding: anyone later wiring Jev into a cost-sensitive path
  in this stack must not rely on Pi's own `/session` dollar display for the
  direct `typesafe` route and should compute real cost from `usage.input` and
  the official per-token rate.

## 6. Open questions / flagged uncertainties

- Whether `ctx.modelRegistry.classify()` called from an extension (not
  codemode) also contributes to `/session` cost accounting — not stated in
  `docs/models.md` or `docs/virtual-models.md`.
- The $0.042/1M input price for the non-free Jev routes and the "free" status
  of the `typesafe` direct and `cloudflare-workers-ai` routes are Pi's
  bundled catalog at version 0.99.1; this is not a live TypeSafe/OpenRouter
  price page and should be re-verified before any spend decision.
- "JevBench" (mentioned in `docs/llama-cpp.md:92` as the benchmark that
  justified reading the state twice) is referenced only by name in Pi's own
  docs; no external corroboration was sought, per the budget/scope
  constraints of this task **[unverified externally]**.
- No local llama.cpp router is configured in this dotfiles checkout, so the
  "local classification, zero marginal cost" alternative in §1.3 is
  currently only a theoretical option, not a drop-in replacement for hosted
  Jev today.

## Sources

- `docs/models.md` (installed Pi 0.99.1) — classifier contract, provider
  table, codemode/cost accounting.
- `docs/virtual-models.md` (installed Pi 0.99.1) — virtual model
  registration, `route()` contract, state, example reference.
- `docs/llama-cpp.md` (installed Pi 0.99.1) — local classifier mechanism,
  calibration caveat, prompt-injection caveat.
- `docs/cli.md` (installed Pi 0.99.1) — codemode enablement, `models.classify`
  concurrency cap, `defaultTools`.
- `examples/extensions/jev-router.ts` (installed Pi 0.99.1) — only shipped
  Jev integration example; basis for §5's experiment design.
- `node_modules/@earendil-works/pi-ai/dist/types.d.ts`,
  `dist/api/system-one-shared.d.ts`, `dist/api/typesafe-system-one.d.ts`,
  `dist/providers/typesafe.models.d.ts`,
  `dist/providers/data/{typesafe,openrouter,cloudflare-workers-ai,vercel-ai-gateway,opencode}.json`
  (installed `@earendil-works/pi-ai` 0.99.1) — exact TypeScript contract and
  bundled catalog prices.
- This repo (`$DOTFILES` worktree `research/jev-pi-routing`):
  `bin/claude-token-proxy`, `config/pi/extensions/anthropic-pool.ts`,
  `config/pi/extensions/llm-failover.ts`, `config/llm-proxy/{routes,classes}.json`,
  `config/pi/skills/delegate/scripts/delegate.sh`,
  `config/pi/skills/ralph-loop/SKILL.md`, `ralph/llm-utilization/loop.sh`,
  `bin/llm-schedule`, `bin/llm-wait`, `scripts/llm_usage.py`,
  `docs/handover/routing-H-task-classes*.md`,
  `docs/research/routing-10-of-10-plan.md` — current routing/data flow and
  task-class mechanism.
- `https://docs.typesafe.ai/models.md`, `https://docs.typesafe.ai/api.md`,
  `https://docs.typesafe.ai/confidence.md` (TypeSafe's official docs, fetched
  directly 2026-10-02, no search engine) — official pricing, rate limits,
  wire contract, confidence formulas; used in §5a to verify and correct the
  catalog-only claims of §1.2.
- `docs/research/jev-test.mjs` (this worktree, committed) — bounded live-test
  script and its console output, reproduced in §5a. 1 unbilled `GET
  /v1/models` + 5 billed `classify()` calls against `typesafe/jev-latest`,
  run 2026-10-02 with a user-supplied key read only from
  `process.env.TYPESAFE_API_KEY` (never from a file path, never logged,
  never committed). Total measured input tokens across the 5 calls: 1,687 ⇒
  real cost at TypeSafe's official $0.042/Mtok rate ≈ $0.00007, authorized
  and within the 5-request/<1000-tokens-each bound set by the task.
