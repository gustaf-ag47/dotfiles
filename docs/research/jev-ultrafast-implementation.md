# jev-ultrafast skill: implementation record

Status: implemented, offline-verified only. Branch `feat/jev-ultrafast-skill`, worktree
`/home/gustaf/.cache/jev-implementation/ultrafast`. Implements
`docs/handover/implement-jev-ultrafast-skill.md`. No network access was used while building or testing
this; no real TypeSafe or text-model call was made; `scripts/setup.sh` was never run against the real
network (its `git clone`/`uv sync` are untested live).

## Source reviewed

Read-only upstream clone `/home/gustaf/.cache/jev-research/jev-ultrafast`, HEAD
`1231850a0bf1a0c0341fe408ef1668dbbfdfac46` (2026-09-18). Read: `README.md`, `AGENTS.md`, `LICENSE`
(MIT, Copyright 2026 Browser Use), `pyproject.toml`, `jev_ultrafast/agent.py`, `jev_ultrafast/model.py`,
`jev_ultrafast/browser.py`, `jev_ultrafast/questions.py`. Also re-read the existing in-repo Jev
classifier (`docs/jev-pi.md`, `config/pi/lib/jev.mjs`, `bin/jev-classify`) to avoid conflating the two
integrations, and `scripts/pi_setup.py` for the existing pinned-upstream pattern (`upstreams.json` +
`--fetch-upstreams`), which this implementation deliberately does not touch or extend (out of
ownership).

## Files owned by this implementation

- `config/pi/skills/jev-ultrafast/SKILL.md` — activation description, setup/credential/execution
  summary, points to `references/` for the two disclosed-reference docs.
- `config/pi/skills/jev-ultrafast/references/limitations.md` — upstream's own stated unsupported
  surfaces (frames/shadow DOM/canvas/uploads/multi-tab/CAPTCHA) plus this wrapper's additional bounds.
- `config/pi/skills/jev-ultrafast/references/text-model.md` — why no default text-model backend is
  wired, what the two env vars mean, and the explicit follow-up this leaves open.
- `config/pi/skills/jev-ultrafast/scripts/setup.sh` — idempotent pinned clone (`git clone --no-checkout`
  + `checkout --detach <pinned commit>`) into `${XDG_CACHE_HOME:-$HOME/.cache}/jev-ultrafast/src`, then
  `uv sync` there. Refuses to touch a checkout with local changes at the wrong commit. Reports (does not
  install) a missing Chrome/Chromium binary.
- `config/pi/skills/jev-ultrafast/scripts/doctor.py` — read-only readiness report (JSON or text):
  checkout presence/pin match, venv presence, `git`/`uv`/`node`/Chrome on `PATH`, whether a TypeSafe key
  and/or `TEXT_MODEL_API_KEY` are configured (**booleans only**, never the value), state dir existence
  and permission mode. No network call, ever.
- `config/pi/skills/jev-ultrafast/scripts/run.py` — the outer wrapper: resolves the TypeSafe key
  (`TYPESAFE_API_KEY` env, else `PI_JEV_KEY_FILE` override, else
  `${XDG_CONFIG_HOME:-$HOME/.config}/jev/api-key`, same resolution order as the existing
  `config/pi/lib/jev.mjs`), validates the pinned checkout, enforces step/time bounds (hard caps 20
  steps / 180 seconds) **before** touching the checkout or credentials, and launches
  `_agent_driver.py`/`_inspect_driver.py` via `uv run --project <checkout>` with the key passed through
  the subprocess environment only (never argv, never printed).
- `config/pi/skills/jev-ultrafast/scripts/_agent_driver.py` — runs *inside* the pinned checkout's own
  venv. Drives upstream's `Agent.command("predict")` / `Agent.command("act", ...)` one step at a time,
  printing operation/label/confidence/latency and prompting `y/N` before every mutating
  `CLICK`/`TYPE_TEXT`/`SELECT` (unless `--auto-approve`); `DONE`/`BLOCKED` never mutate and are never
  prompted, matching upstream's own `Agent.command` contract (`agent.py` lines ~90-110: `DONE`/`BLOCKED`
  branch returns before `state["browser"].act(...)` is ever called). Writes a redacted JSON trace (no
  raw page text, no request/response bodies, goal recorded only as a SHA-256 hash).
- `config/pi/skills/jev-ultrafast/scripts/_inspect_driver.py` — observes a page and prints the indexed
  element table (via upstream's own `jev_ultrafast.model.action_space`) with **no** TypeSafe or
  text-model call and no `.command("act")` call anywhere in the script.
- `tests/unit/test_jev_ultrafast_skill.py` — 15 offline tests (`subprocess` + temp `HOME`/XDG dirs, one
  direct-import test with `checkout_ready` monkeypatched to avoid needing a real pinned git commit hash).
- `docs/jev-ultrafast.md` — usage/design summary, verification status, open items for the parent.
- This file.

Nothing else was edited: `config/pi/lib/jev.mjs`, `bin/jev-classify`, `config/llm-proxy/jev.json`,
`scripts/pi_setup.py`, `config/pi/upstreams.json`, `docs/jev-pi.md`, and every other skill are untouched
(verified by `git status`/`git diff --check` below only touching the files listed above).

## Credential decision actually made

Canonical key file is **reused** from the existing shadow classifier
(`${XDG_CONFIG_HOME:-$HOME/.config}/jev/api-key`, 0600) rather than inventing a second path, since
TypeSafe issues one account key regardless of which Jev product (System One classifier vs. Ultrafast
browser agent) is calling it, and rotating two separate files for one underlying credential would be
pure friction. The two integrations remain accounted for **separately**: this skill never touches
`config/pi/lib/jev.mjs`'s ledger/cache/budget state, and its own redacted traces live under a disjoint
state path (`${XDG_STATE_HOME}/jev-ultrafast/traces/`, vs. the classifier's
`${XDG_STATE_HOME}/jev/events.jsonl`).

Text-model backend (`TEXT_MODEL_API_KEY`) is **explicitly required, never defaulted**. Upstream's own
`field_text()` (`model.py`) already raises a `ValueError` with no key — this wrapper surfaces that same
fact pre-flight (`doctor.py`, `run.py`'s dry-run output) rather than silently routing to OpenRouter (the
README's example) or any other provider. No new credential was requested, read, or rotated while
building this.

## Execution-safety decisions actually made

- `run.py` has no mode that mutates a page without `--execute`, and `--execute` itself requires
  per-step `y/N` approval by default (`--auto-approve` opts out of the prompt only, never the
  step/time caps).
- Step/time caps (20 / 180s) are validated **before** the checkout or credentials are even looked at,
  so a malformed `--max-steps` never gets far enough to touch a real resource — verified by
  `test_execute_rejects_step_budget_above_cap`/`test_execute_rejects_time_budget_above_cap`, which pass
  with no pinned checkout present at all.
- `DONE` is never treated as verified success: `_agent_driver.py` prints an explicit note to check the
  final URL/title/goal manually, and `run.py`/`SKILL.md` repeat this in writing.
- Browser Harness creates a background tab (verified by reading `browser.py`:
  `Target.createTarget(url="about:blank", background=True)`), so the agent's tab is never the user's
  active one — but it is still the same Chrome **profile** (same cookies/sessions). Documented, not
  mitigated (upstream has no profile-isolation option); `references/limitations.md` tells the user to
  rely on per-step approval rather than `--auto-approve` on any site with a session they care about.

## Exact test command and result

```
$ python3 -m unittest tests.unit.test_jev_ultrafast_skill -v
```

Full captured output (`/tmp/jev_ultrafast_test_output.txt` in this worktree at implementation time):

```
test_doctor_never_prints_key_value ... ok
test_doctor_reports_missing_checkout_without_crashing_or_network ... ok
test_doctor_respects_pi_jev_key_file_override ... ok
test_dry_run_never_prints_key_value ... ok
test_dry_run_requires_url_and_goal ... ok
test_dry_run_without_checkout_reports_not_ready_and_makes_no_calls ... ok
test_execute_rejects_step_budget_above_cap ... ok
test_execute_rejects_time_budget_above_cap ... ok
test_execute_without_checkout_fails_before_any_subprocess ... ok
test_execute_without_typesafe_key_refuses_before_subprocess ... ok
test_inspect_and_execute_are_mutually_exclusive ... ok
test_referenced_scripts_exist_and_are_executable ... ok
test_references_exist ... ok
test_scripts_syntax_clean ... ok
test_skill_md_present_and_has_frontmatter ... ok

Ran 15 tests in 0.532s

OK
```

Also run, both clean:

```
$ python3 -m py_compile config/pi/skills/jev-ultrafast/scripts/{run,doctor,_agent_driver,_inspect_driver}.py
$ bash -n config/pi/skills/jev-ultrafast/scripts/setup.sh
$ git diff --check --cached   # 0 findings
```

Manual sanity run of `doctor.py` and `run.py` (no args) against this **host's real, unmodified**
environment (not a temp dir) correctly found the real TypeSafe key already installed at
`~/.config/jev/api-key` by the earlier shadow-classifier pilot, `git`/`uv`/`node`/`chromium` on `PATH`,
and reported the (not-yet-cloned) pinned checkout as not ready — with no secret value printed either
time.

## Not exercised (explicitly out of scope here)

- `scripts/setup.sh` was never run for real: no `git clone` of upstream, no `uv sync`, no Browser
  Harness/Chrome daemon connection attempt.
- No real TypeSafe `systemone` call and no real text-model call were made; `_agent_driver.py`'s
  approval-loop logic is therefore verified by code review against `agent.py`'s documented
  `Agent.command` contract, not by a live run.
- `uv run ruff check .` / `uv run pytest` (upstream's own offline test suite) were not run, since that
  needs the pinned checkout's `uv sync` to exist first, which needs network access this worktree does
  not have authorization to use.
- No live smoke test of a single approved `--execute` step against a real page.

These are the concrete remaining steps listed in `docs/jev-ultrafast.md`'s "Open items for the parent".

## Blockers: none that stopped delivery

No blocker prevented a usable, testable baseline. The two intentional scope boundaries — no default
text-model backend, no live network verification — are documented limitations, not blockers, per the
handover brief's instruction to "deliver safe useful baseline with explicit limitation and concrete
follow-up" if full upstream integration needed substantial additional work.

---

PARENT: 20261002T124638Z-1591271 done — jev-ultrafast skill implemented and offline-verified
(`config/pi/skills/jev-ultrafast/**`, `tests/unit/test_jev_ultrafast_skill.py`,
`docs/jev-ultrafast.md`, this file) on branch `feat/jev-ultrafast-skill` in
`/home/gustaf/.cache/jev-implementation/ultrafast`. 15/15 new offline tests pass, `git diff --check`
clean, no network/paid calls made, no shared files touched. Live install (`scripts/setup.sh`), a real
Chrome/Browser Harness/TypeSafe/text-model smoke test, and the four open items above are left for your
review and authorization.
