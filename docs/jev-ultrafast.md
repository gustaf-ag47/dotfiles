# jev-ultrafast: opt-in browser agent skill

This documents `config/pi/skills/jev-ultrafast/`, a thin wrapper around
[browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast) (MIT, Browser Use), pinned at
commit `1231850a0bf1a0c0341fe408ef1668dbbfdfac46`. It is a **separate integration** from the existing
Jev task classifier documented in `docs/jev-pi.md` / `config/pi/lib/jev.mjs` / `bin/jev-classify`: that
classifier labels a short delegated task string (`interactive|build|research|mechanical`) and never
touches a browser or applies a decision. This skill drives a real Chrome tab toward one explicit
goal+URL using TypeSafe's indexed operation/target picker (`CLICK`/`TYPE_TEXT`/`SELECT`/...). Do not
confuse the two, reuse `classifyTask()`'s budget/cache/ledger for this, or feed arbitrary page DOM
content into `classifyTask()`.

Full usage is in [`config/pi/skills/jev-ultrafast/SKILL.md`](../config/pi/skills/jev-ultrafast/SKILL.md)
and its `references/`. This doc covers what isn't appropriate to put in the skill itself: the design
rationale, what was verified, and what remains for the parent to decide.

## Why a thin wrapper instead of vendoring

Upstream is a small (~750 line) Python library plus a Browser Harness dependency that manages its own
Chrome daemon. Vendoring the dependency tree into dotfiles git would mean tracking `uv.lock`, pulling in
`browser-harness`/`httpx` as committed artifacts, and re-pinning on every upstream change by hand.
Instead `scripts/setup.sh` clones the pinned commit into
`${XDG_CACHE_HOME:-$HOME/.cache}/jev-ultrafast/src` (persistent, outside git) and runs `uv sync` there;
the skill's own scripts (`run.py`, `doctor.py`, the `_*_driver.py` helpers actually executed inside that
checkout's venv) are the only things that live in git.

## Credential handling

TypeSafe's key reuses the **same canonical file** the existing shadow task classifier already uses:
`${XDG_CONFIG_HOME:-$HOME/.config}/jev/api-key` (0600), with the same `PI_JEV_KEY_FILE`/
`TYPESAFE_API_KEY` override names, for operational consistency — one place to rotate a TypeSafe key.
The two integrations are still billed and tracked completely separately: this skill never reads or
writes `config/pi/lib/jev.mjs`'s ledger (`${XDG_STATE_HOME}/jev/events.jsonl`), cache, or budget files,
and `bin/jev-classify`'s daily budget caps in `config/llm-proxy/jev.json` do not apply to browser-agent
calls. `run.py`/`doctor.py` never print the key value; it is passed to the `uv run` subprocess only
through the environment, never argv.

`TYPE_TEXT` (typing a value into a field) needs a **second, separately configured** OpenAI-compatible
text model (`TEXT_MODEL_API_KEY`, optional `TEXT_MODEL_BASE_URL`/`TEXT_MODEL`). This skill does not
default to, assume, or silently route to OpenRouter or any Pi-managed model — see
[`references/text-model.md`](../config/pi/skills/jev-ultrafast/references/text-model.md) for the
reasoning and the explicit follow-up this leaves for the parent (a possible future Pi-OAuth-backed
shim). `doctor.py`/`run.py` report whether this is configured; `run.py --execute` proceeds without it
(only `TYPE_TEXT` steps fail at the point they'd be needed) rather than blocking the whole run.

## Execution bounds actually implemented

- `run.py` has three modes: no flags (pre-flight plan only, no browser/model call), `--inspect`
  (observe + print the element table, no TypeSafe/text-model call, no mutation), `--execute` (the full
  loop). `--execute` requires `--max-steps` (hard cap 20) and `--max-seconds` (hard cap 180);
  out-of-range values are rejected before the checkout or credentials are even consulted.
- Inside `--execute`, `_agent_driver.py` (run inside the pinned checkout's own venv) calls upstream's
  `Agent.command("predict")` then prints the decision (operation, element label, confidence, latency)
  and prompts `y/N` before `Agent.command("act", ...)` for every `CLICK`/`TYPE_TEXT`/`SELECT`.
  `--auto-approve` removes the prompt but not the step/time caps. `DONE`/`BLOCKED` never mutate the page
  (upstream's own `Agent.command` contract) and are never prompted.
- A `DONE` decision is explicitly **not** treated as verified success anywhere in this wrapper; the
  driver prints the final URL/title and a note to verify independently, matching upstream's own
  documented position ("A `DONE` choice still requires independent outcome verification").
- Browser Harness creates an owned **background** Chrome target (`Target.createTarget ...
  background=True`), not the user's active tab — but it is still the same installed Chrome profile
  (cookies/sessions/history shared). Documented as a privacy risk in
  [`references/limitations.md`](../config/pi/skills/jev-ultrafast/references/limitations.md); this
  wrapper does not create or manage an isolated profile (upstream doesn't offer one), so sites with a
  logged-in session the user doesn't want touched should only be used with per-step approval, never
  `--auto-approve`.
- The redacted trace written to `${XDG_STATE_HOME:-$HOME/.local/state}/jev-ultrafast/traces/*.json`
  contains operation, truncated element label, probability/confidence, latency, and a SHA-256 of the
  goal text (not the goal itself) — never raw DOM/page text, request/response bodies, or credentials.

## What was verified in this environment

This worktree has **no network access authorization** and this implementation did not clone upstream,
run `uv sync`, install Browser Harness, or make any TypeSafe/text-model call. Verified offline:

- `python3 -m unittest tests.unit.test_jev_ultrafast_skill -v` — 15/15 passed (see exact output in
  [`docs/research/jev-ultrafast-implementation.md`](research/jev-ultrafast-implementation.md)). Covers:
  SKILL.md frontmatter/discovery, script syntax (`py_compile` + `bash -n`), `doctor.py`'s missing-checkout
  report, that neither `doctor.py` nor `run.py` ever prints a configured key's value, `PI_JEV_KEY_FILE`
  override resolution, `run.py`'s dry-run/`--inspect`/`--execute` argument contract, step/time bound
  rejection above the hard caps, and refusal to `--execute` without a TypeSafe key — all before any
  subprocess or network call would occur.
- Manual runs of `doctor.py` and `run.py` (no flags) against this host's real environment: correctly
  detected the existing TypeSafe key at the shared canonical path (configured by the earlier shadow
  classifier pilot), reported "not ready" for the (not-yet-cloned) pinned checkout, found `git`/`uv`/
  `node`/`chromium` on `PATH`, and printed no secret value.
- `git diff --check` clean (see implementation doc).

**Not verified**: a real `scripts/setup.sh` clone/`uv sync`, a real Browser Harness/Chrome connection, a
real TypeSafe or text-model call, or a real bounded `--execute` run end-to-end. That requires network
access and a live paid TypeSafe key dispatch, which is explicitly the parent's call per the handover
brief ("Parent owns review, integration, live install and any paid smoke tests").

## Open items for the parent

1. **`config/pi/upstreams.json` integration.** `scripts/pi_setup.py` already has a generic pinned-skill
   clone mechanism (`--fetch-upstreams`) that targets `~/.agents/skills/<name>`. This implementation
   deliberately does not add an entry there (that file is explicitly out of this implementation's
   ownership) and instead gives `jev-ultrafast` its own `setup.sh` targeting
   `${XDG_CACHE_HOME}/jev-ultrafast/src`, since the upstream here is a Python library consumed via `uv`,
   not another skill directory to be symlinked into `~/.pi/agent/skills`. If you'd rather unify this
   under `upstreams.json`, that needs a small `pi_setup.py` change (not made here).
2. **Text-model backend.** No default is wired. If you want `TYPE_TEXT` to work out of the box against
   an existing Pi-managed subscription instead of a separately metered DeepSeek/OpenRouter key, that
   needs a small local OpenAI-compatible shim in front of a Pi provider — not built here; flagged as
   explicit follow-up in `references/text-model.md`.
3. **`classifier_activity`/ledger integration.** Not attempted. The browser-agent calls this skill makes
   are a different cost center from the task classifier's `classifier_activity` ledger; if you want them
   surfaced in `llm-usage` too, that needs a new event source/schema, proposed but not implemented here
   per the brief ("don't silently write invalid browser events or mislabel browser calls as task
   classification").
4. **Live smoke test.** First real `--inspect` and a single approved `--execute` step against a
   low-stakes public page (e.g. Wikipedia, matching upstream's own example) would be the natural next
   step once the parent authorizes the pinned clone + a live TypeSafe key dispatch.
