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

`TYPE_TEXT` supports **Pi-backed typing** with existing credentials, or the original
explicitly configured OpenAI-compatible API backend. See
[`references/text-model.md`](../config/pi/skills/jev-ultrafast/references/text-model.md)
for configuration and privacy details. For one run:

```sh
python3 ~/.pi/agent/skills/jev-ultrafast/scripts/run.py \
  --url 'https://example.com' --goal 'one explicit task' \
  --text-backend pi --pi-text-model openai-codex/gpt-5.6-luna \
  --execute --max-steps 8 --max-seconds 60
```

A saved, non-secret preference in `~/.config/jev-ultrafast/text-model.json` can select
that model without repeating flags. The adapter uses Pi's native `ModelRuntime`
and credential refresh, not a full agent or another HTTP server. It loads no tools,
conversation history, skills or project instructions; only the selected Anthropic/
Grok provider factory is reused where necessary. State uses bounded stdin/stdout
pipes, not command-line prompts or saved sessions. It makes one completion and
accepts only a small, valid JSON field value. Model errors, quota exhaustion and
invalid output stop typing without a fallback provider.

The legacy API path still requires all of `TEXT_MODEL_API_KEY`,
`TEXT_MODEL_BASE_URL`, and `TEXT_MODEL` together. Mixed/partial settings are rejected.
No text backend configured means click-only mode, not permission to guess text.
Using OAuth removes the need for another API key, **not** the provider's usage charges.

## Execution bounds actually implemented

- `run.py` has three modes: no flags (pre-flight plan only, no browser/model call), `--inspect`
  (observe + print the element table, no TypeSafe/text-model call, no mutation), `--execute` (the full
  loop). `--execute` requires `--max-steps` (hard cap 20) and `--max-seconds` (hard cap 180);
  out-of-range values are rejected before the checkout or credentials are even consulted.
- Inside `--execute`, `_agent_driver.py` (run inside the pinned checkout's own venv) calls upstream's
  `Agent.command("predict")` then prints the decision (operation, target identifier, confidence, latency)
  and prompts `y/N` before `Agent.command("act", ...)` for every `CLICK`/`TYPE_TEXT`/`SELECT`.
  `--auto-approve` removes the prompt but not the step/time caps. `DONE`/`BLOCKED` never mutate the page
  (upstream's own `Agent.command` contract) and are never prompted.
- A `DONE` decision is explicitly **not** treated as verified success anywhere in this wrapper; the
  driver prints the final URL origin and a note to verify the actual browser page independently, matching upstream's own
  documented position ("A `DONE` choice still requires independent outcome verification").
- Browser Harness creates an owned **background** Chrome target (`Target.createTarget ...
  background=True`), not the user's active tab — but it is still the same installed Chrome profile
  (cookies/sessions/history shared). Documented as a privacy risk in
  [`references/limitations.md`](../config/pi/skills/jev-ultrafast/references/limitations.md); this
  wrapper does not create or manage an isolated profile (upstream doesn't offer one), so sites with a
  logged-in session the user doesn't want touched should only be used with per-step approval, never
  `--auto-approve`.
- The redacted trace written to `${XDG_STATE_HOME:-$HOME/.local/state}/jev-ultrafast/traces/*.json`
  contains only operation, probability/confidence, latency, whether the page changed, whether *some*
  text was entered (never the text itself), and a SHA-256 of the goal text (not the goal itself) —
  never an element label, a URL path/query/fragment (origin only), a page title, request/response bodies, or
  credentials. Written atomically at 0600 in a 0700 directory.

The outer process timeout is exactly `--max-seconds`, including model calls and
human approval waits; it is not extended to let a late action execute. Killing a
run cannot undo previously completed browser actions.

## What was verified in this environment

Offline (no network, no credentials read beyond a boolean presence check, no paid calls), every commit
on this branch:

- `python3 -m unittest tests.unit.test_jev_ultrafast_skill tests.unit.test_jev_ultrafast_closeout -v` —
  **51 tests passing** at final integration. Includes exact outer-deadline forwarding,
  Ctrl-C process-group cleanup, origin-only diagnostics, and complete-backend readiness. Covers:
  SKILL.md frontmatter/discovery, script syntax (`py_compile` + `bash -n`), `doctor.py`'s readiness
  report (including that it never claims verified browser connectivity), that neither `doctor.py` nor
  `run.py` ever prints a configured key's value, `run.py`'s dry-run/`--inspect`/`--execute` argument
  contract, non-finite (`NaN`/`inf`) and out-of-range step/time bound rejection, http(s)-only/
  no-embedded-credential URL validation, the text-model all-three-or-none routing rule (a bare
  `TEXT_MODEL_API_KEY` is refused, never silently reaches upstream's DeepSeek default), a hard-walled
  subprocess timeout that kills a hanging child's whole process group, trace metadata/permissions
  (0600 file in a 0700 dir, atomic write, no label/URL-query/title/goal text), and dirty-pinned-checkout
  rejection (`setup.sh`'s `verify_pinned_clean()` sourced directly against local git fixtures, and
  `run.py`'s own independent `checkout_ready()` dirty check) — all offline, no real upstream clone
  needed for any of it.
- `git diff --check` clean on every commit.

Live, network-authorized, on this host (second commit on this branch — see
operator notes: jev-ultrafast-implementation.md for the full write-up): `scripts/setup.sh` ran for real — cloned the actual upstream repo at the pinned commit and
ran `uv sync` cleanly. `doctor.py` correctly reported readiness and found the pre-existing shared
TypeSafe key without printing it. `run.py --inspect` surfaced a clean upstream error tracing to Chrome's
`chrome://inspect` remote-debugging **consent toggle never having been enabled** on this host's regular
Chromium profile — a one-time interactive step upstream itself documents. That toggle flips the
profile's CDP/debugging posture and was deliberately **not** flipped automatically (would mutate the
user's regular browser without consent); the Chromium window Browser Harness launched during diagnosis
was closed immediately once the cause was isolated.

**Pi typing verified (2026-10-03):** a synthetic destination-field request returned
`London` via existing `openai-codex/gpt-5.6-luna` credentials in 4,936 ms (128 input,
9 output tokens; $0.0000364 catalog-estimated cost). No additional text API key,
agent tools, browser actions, or stored session were involved. Importing the pinned
upstream also confirmed that `Agent.command` uses the substituted `field_text`
callback. Anthropic/Grok provider registration and expected endpoints were checked
without inference. Offline tests cover strict state/output contracts, explicit
backend selection, callback pinning, subprocess timeout/output bounds, and no retry
or provider fallback.

**Live browser verification completed (2026-10-03):** both laptop and skrubben
used the explicitly selected Neko CDP browser. Production `--inspect` succeeded
against example.com with no model call. The opt-in fixture test then created an
owned about:blank tab with fixed synthetic HTML, used real Jev decisions and
Pi-backed typing, executed `TYPE_TEXT → CLICK → DONE`, and independently checked
that the input and result DOM both contained London. Three Jev calls and one Pi
text call per host; 22.272 s on the laptop, 22.481 s on skrubben including startup.
Each test closed its own tab and uniquely named daemon. No authenticated site or
account action was used. This is one integration check, not a general reliability
or speed benchmark. Production human approval controls remain separately covered
by offline tests; the fixture's deterministic gate authorizes only its test nodes.

## Neko connection on these two hosts

There is no need to modify the normal desktop Chrome profile. Start the existing
Neko co-browse service on skrubben explicitly, then select its CDP endpoint:

```sh
# Laptop (Tailscale connected):
BU_NAME=jev-neko-laptop BU_CDP_URL=http://100.95.138.80:9224 \
  python3 ~/.pi/agent/skills/jev-ultrafast/scripts/run.py \
  --url https://example.com --goal 'Observe this page' --inspect

# On skrubben:
BU_NAME=jev-neko-skrubben BU_CDP_URL=http://127.0.0.1:9224 \
  python3 ~/.pi/agent/skills/jev-ultrafast/scripts/run.py \
  --url https://example.com --goal 'Observe this page' --inspect
```

Use a dedicated `BU_NAME` so other Browser Harness sessions are unaffected. Clear
conflicting `BU_BROWSER_ID`/`BU_CDP_WS` overrides when choosing `BU_CDP_URL`.
Neko tabs share its automation Chrome profile/cookies, not an isolated profile per
task. Keep CDP on the trusted tailnet; never publish it to the Internet. `doctor.py`
still does not actively probe connectivity; `--inspect` is the live check.

The explicit, paid synthetic test is `tests/e2e/jev-ultrafast-fixture.py`, run through
the pinned upstream venv with `--allow-model-calls` and `BU_CDP_URL`. It refuses
cloud/default browser discovery, permits actions only on its own fixture controls,
and bounds calls/time. Without the opt-in flag it does nothing.

## Setup requirements and optional follow-ups

1. **`config/pi/upstreams.json` integration.** `scripts/pi_setup.py` already has a generic pinned-skill
   clone mechanism (`--fetch-upstreams`) that targets `~/.agents/skills/<name>`. This implementation
   deliberately does not add an entry there (that file is explicitly out of this implementation's
   ownership) and instead gives `jev-ultrafast` its own `setup.sh` targeting
   `${XDG_CACHE_HOME}/jev-ultrafast/src`, since the upstream here is a Python library consumed via `uv`,
   not another skill directory to be symlinked into `~/.pi/agent/skills`. **Closeout decision:**
   keep this explicit library setup separate; `pi-setup` installs the skill resources only.
2. **Text-model backend.** The Pi adapter is implemented. Each host needs an explicit
   model selection (flags/environment or its own saved preference) and that provider's
   existing credentials. This host is configured for `openai-codex/gpt-5.6-luna`.
   No text-provider API key or automatic model routing is required.
3. **`classifier_activity`/ledger integration.** Not attempted. The browser-agent calls this skill makes
   are a different cost center from the task classifier's `classifier_activity` ledger; if you want them
   surfaced in `llm-usage` too, that needs a new event source/schema, proposed but not implemented here
   per the brief ("don't silently write invalid browser events or mislabel browser calls as task
   classification").
4. **Further site testing.** Transport, typing and the synthetic browser loop are verified
   above. Real tasks still require explicit user intent and the normal approval controls;
   no purchases, bookings, account changes or arbitrary-site reliability are claimed.
