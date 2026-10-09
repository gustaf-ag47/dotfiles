---
name: jev-ultrafast
description: Explicitly run or inspect a bounded Jev browser agent in Chrome, with human step approval and optional Pi-backed typing.
disable-model-invocation: true
---

# jev-ultrafast

Wraps [browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast), pinned at commit
`1231850a0bf1a0c0341fe408ef1668dbbfdfac46` (MIT, Browser Use). This is a **different** Jev integration
from `$NOTES/Homelab/dotfiles/jev-pi.md` / `config/pi/lib/jev.mjs` — that helper classifies a short delegated task string
into `interactive|build|research|mechanical` and never touches a browser. This skill drives an actual
page with TypeSafe's indexed operation/target picker. Do not conflate the two or feed this skill's
browser-page text into `classifyTask()`, or vice versa.

**Not auto-activated.** Nothing in this skill runs at Pi startup or on a normal turn. Every script here
is opt-in and must be invoked explicitly.

## 1. Check readiness (safe, read-only, no network, no secrets printed)

```sh
python3 ~/.pi/agent/skills/jev-ultrafast/scripts/doctor.py
```

Reports: pinned checkout present/matches commit/clean tree, `uv`/`git`/Chrome found, TypeSafe key file
configured (boolean only), text-model backend status, state dir permissions. Fixes nothing, makes no
live browser/network call — `browser_connectivity` is always reported as **not verified** by doctor;
only an actual `--inspect`/`--execute` run proves Chrome is reachable.

## 2. Set up the pinned checkout (idempotent, explicit)

```sh
~/.pi/agent/skills/jev-ultrafast/scripts/setup.sh
```

Clones `browser-use/jev-ultrafast` at the pinned commit into
`${XDG_CACHE_HOME:-$HOME/.cache}/jev-ultrafast/src` (outside git) if not already present at that commit,
then runs `uv sync --frozen` there (never updates the lockfile). Never touches `$HOME/.pi`, dotfiles git
state, or any other skill. Re-running is a no-op once the pin matches **and the tree is clean** — a
checkout at the right commit but with local changes is refused, not silently used, since a matching
`HEAD` alone doesn't prove the working tree still matches the pin. Requires `git` and `uv`; reports
(does not install) a missing Chrome.

## 3. Credentials

TypeSafe key (same canonical file the existing shadow classifier uses):
`${XDG_CONFIG_HOME:-$HOME/.config}/jev/api-key`, mode 0600. Override with `PI_JEV_KEY_FILE` or set
`TYPESAFE_API_KEY` directly. **This skill never prints, logs, or echoes the key value**, and never
reuses the shared `jev.mjs`/`bin/jev-classify` task-classifier budget, cache, or ledger — the two Jev
uses are billed and tracked completely separately on TypeSafe's side.

For `TYPE_TEXT`, explicitly choose a backend:

- **Pi credentials:** `--text-backend pi --pi-text-model openai-codex/gpt-5.6-luna`
  (or a saved preference). No separate text API key. One tool-less completion gets
  only the field context, not the agent's conversation or repository instructions.
- **API:** configure all of `TEXT_MODEL_API_KEY`, `TEXT_MODEL_BASE_URL`, and
  `TEXT_MODEL`. Partial or mixed-backend configuration is rejected.
- **None:** click-only goals can run; a typing step stops rather than guessing.

Read [references/text-model.md](references/text-model.md) for saved configuration,
supported Pi providers, deadlines, privacy, and accounting. The model is pinned
per run; no silent provider fallback or new login is performed. Provider usage
may still consume paid credits/extra usage even when using OAuth.

## 4. Inspect a page without any model call (safe default)

```sh
python3 ~/.pi/agent/skills/jev-ultrafast/scripts/run.py --url 'https://example.com' --goal 'describe intent' --inspect
```

Opens an **owned background tab** in the real installed Chrome via Browser Harness — never the user's
active tab — and closes it afterward. This is **not an isolated profile**: cookies, logged-in sessions,
extensions, and history for that Chrome profile are all visible to whatever the tab navigates to (see
[references/limitations.md](references/limitations.md)). The first `--inspect`/`--execute` on a given
machine may also prompt you, in that Chrome window, to allow remote debugging — that changes the
profile's CDP/debugging posture and needs your own explicit approval in the browser; this skill never
flips that toggle for you. No TypeSafe or text-model call is made by `--inspect`.

## 5. Execute a bounded, approved run

```sh
python3 ~/.pi/agent/skills/jev-ultrafast/scripts/run.py \
  --url 'https://example.com' --goal 'one explicit natural-language goal' \
  --max-steps 8 --max-seconds 60 --execute
```

- Requires `--execute` (omit it and the command only prints the resolved plan/config and exits).
- `--max-steps` capped at 20, `--max-seconds` capped at 180; both required with `--execute`.
- **Every CLICK/TYPE_TEXT/SELECT is printed (operation, target identifier, confidence) and asks `y/N`
  before it executes**, by default. `DONE`/`BLOCKED` never mutate the page and don't prompt.
- **This default `y/N` prompt needs a real interactive terminal.** Run `--execute` (without
  `--auto-approve`) in a visible, interactive pane (a tmux window/pane you're watching, not a
  non-interactive tool call) — a normal Pi bash-tool invocation has no interactive stdin, so the prompt
  will hang or fail there. If an agent is driving this skill on a user's behalf, it must launch
  `--execute` in a pane the user can see and type into themselves; the agent must not type `y` for the
  user.
- `--auto-approve` removes the prompt but **not** the step/time bounds. It is for the **human user to
  pass, with explicit authorization, once they trust a specific goal/site** — an agent must never add
  `--auto-approve` on its own judgment or self-declared confidence; that defeats the approval gate this
  skill exists to provide.
- A `DONE` decision is **not** verified success; inspect the actual browser page and confirm the goal
  yourself. Jev's own confidence or `DONE` choice is never treated as proof.
- Never performs a purchase/booking/send/account-changing action beyond what you individually approve
  per step, never attempts CAPTCHA bypass, and refuses to run without an explicit `--goal`/`--url`
  (http(s) only, no embedded credentials).
- Writes a **metadata-only, atomically-written** trace (0600 file in a 0700 dir: operation, probability,
  confidence, latency, whether the page changed, whether *some* text was entered — never an element
  label, never a full URL (origin only), never a title, never prompts/credentials) to
  `${XDG_STATE_HOME:-$HOME/.local/state}/jev-ultrafast/traces/`.
- Both `--inspect` and `--execute` run under their own hard outer timeout (process-group kill on
  expiry), separate from and in addition to the script's own step/time bounds, so a stuck browser call
  or an unanswered prompt cannot hang indefinitely.

## Limits

Read [references/limitations.md](references/limitations.md) for what upstream explicitly does not
support (frames, shadow DOM, canvas, uploads, multi-tab, CAPTCHA) and the shared-Chrome-profile privacy
note before using this on a site with a logged-in session.
