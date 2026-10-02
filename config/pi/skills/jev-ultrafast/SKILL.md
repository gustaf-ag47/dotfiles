---
name: jev-ultrafast
description: Drive a real Chrome tab toward one explicit goal+URL using browser-use/jev-ultrafast (TypeSafe Jev picks CLICK/TYPE_TEXT/SELECT targets from a DOM snapshot; a separately configured text model only fills TYPE_TEXT values). Opt-in, bounded, step-by-step approved — not for Jev's own classifyTask() task-routing helper. Use when asked to automate a browser task with jev-ultrafast, check whether jev-ultrafast is set up, or run/inspect a bounded browser agent step.
disable-model-invocation: true
---

# jev-ultrafast

Wraps [browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast), pinned at commit
`1231850a0bf1a0c0341fe408ef1668dbbfdfac46` (MIT, Browser Use). This is a **different** Jev integration
from `docs/jev-pi.md` / `config/pi/lib/jev.mjs` — that helper classifies a short delegated task string
into `interactive|build|research|mechanical` and never touches a browser. This skill drives an actual
page with TypeSafe's indexed operation/target picker. Do not conflate the two or feed this skill's
browser-page text into `classifyTask()`, or vice versa.

**Not auto-activated.** Nothing in this skill runs at Pi startup or on a normal turn. Every script here
is opt-in and must be invoked explicitly.

## 1. Check readiness (safe, read-only, no network, no secrets printed)

```sh
python3 ~/.pi/agent/skills/jev-ultrafast/scripts/doctor.py
```

Reports: pinned checkout present/matches commit, `uv`/`git`/Chrome found, TypeSafe key file configured
(boolean only), `TEXT_MODEL_API_KEY` configured (boolean only), state dir permissions. Fixes nothing.

## 2. Set up the pinned checkout (idempotent, explicit)

```sh
~/.pi/agent/skills/jev-ultrafast/scripts/setup.sh
```

Clones `browser-use/jev-ultrafast` at the pinned commit into
`${XDG_CACHE_HOME:-$HOME/.cache}/jev-ultrafast/src` (outside git) if not already present at that commit,
then runs `uv sync` there. Never touches `$HOME/.pi`, dotfiles git state, or any other skill. Re-running
is a no-op once the pin matches. Requires `git` and `uv`; reports (does not install) a missing Chrome.

## 3. Credentials

TypeSafe key (same canonical file the existing shadow classifier uses):
`${XDG_CONFIG_HOME:-$HOME/.config}/jev/api-key`, mode 0600. Override with `PI_JEV_KEY_FILE` or set
`TYPESAFE_API_KEY` directly. **This skill never prints, logs, or echoes the key value**, and never
reuses the shared `jev.mjs`/`bin/jev-classify` task-classifier budget, cache, or ledger — the two Jev
uses are billed and tracked completely separately on TypeSafe's side.

`TYPE_TEXT` steps (typing a value into a field) additionally need a **separately and explicitly
configured** OpenAI-compatible text model: `TEXT_MODEL_API_KEY` (required), optionally
`TEXT_MODEL_BASE_URL` (upstream default `https://api.deepseek.com/v1`) and `TEXT_MODEL`. This skill
does **not** pick, default to, or silently fall back to any provider (not OpenRouter, not a Pi
OAuth-backed model) — if `TEXT_MODEL_API_KEY` is unset, `TYPE_TEXT` steps fail loudly and `run.py`
reports this before execution rather than after a paid dispatch. See
[references/text-model.md](references/text-model.md) before setting this.

## 4. Inspect a page without any model call (safe default)

```sh
python3 ~/.pi/agent/skills/jev-ultrafast/scripts/run.py --url 'https://example.com' --goal 'describe intent' --inspect
```

Opens an isolated background Chrome tab (via Browser Harness; never the user's active tab/profile
session), prints the numbered element table, and closes it. No TypeSafe or text-model call.

## 5. Execute a bounded, approved run

```sh
python3 ~/.pi/agent/skills/jev-ultrafast/scripts/run.py \
  --url 'https://example.com' --goal 'one explicit natural-language goal' \
  --max-steps 8 --max-seconds 60 --execute
```

- Requires `--execute` (omit it and the command only prints the resolved plan/config and exits).
- `--max-steps` capped at 20, `--max-seconds` capped at 180; both required with `--execute`.
- **Every CLICK/TYPE_TEXT/SELECT is printed (operation, element label, confidence) and asks `y/N`
  before it executes.** `DONE`/`BLOCKED` never mutate the page and don't prompt. `--auto-approve`
  removes the prompt but not the step/time bounds — use it only once you trust a specific goal/site.
- A `DONE` decision is **not** verified success; read the final URL/title/snippet this script prints
  and confirm the goal yourself. Jev's own confidence or `DONE` choice is never treated as proof.
- Never performs a purchase/booking/send/account-changing action beyond what you individually approve
  per step, never attempts CAPTCHA bypass, and refuses to run without an explicit `--goal`/`--url`.
- Writes a **redacted** trace (operation, label, confidence, latency, timestamps — no raw DOM text, no
  prompts, no credentials) to `${XDG_STATE_HOME:-$HOME/.local/state}/jev-ultrafast/traces/`.

## Limits

Read [references/limitations.md](references/limitations.md) for what upstream explicitly does not
support (frames, shadow DOM, canvas, uploads, multi-tab, CAPTCHA) and the shared-Chrome-profile privacy
note before using this on a site with a logged-in session.
