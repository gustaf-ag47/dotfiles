# Brief — Step 5: make plain `pi` load `config/pi/extensions/*.ts`, and green up `make test-unit`

**Agent:** delegated pi sub-agent, worktree branch `llm-proxy/step5-pi-loading`.
**Parent:** the orchestrator pi pane. **Date:** 2026-09-25.
**Repo:** `$DOTFILES` = `/home/gud1/sync/src/dotfiles`, default branch `master`, public repo.

## Context

Steps 1–4 of `docs/handover/llm-proxy-implementation.md` landed today (read it, incl.
the "done" notes and "Remaining manual items"). Two items are yours:

**(A) Extension loading.** `config/pi/extensions/llm-failover.ts` (Step 4) and the
older `llm-usage.ts`, `anthropic-subscription.ts`, `goal.ts` only reach a running pi
when launched via `bin/pi-claude-sub` (it passes `-e` for each). Plain `pi` — the
launcher the `delegate` skill uses for Codex/OpenAI sessions — loads only
`~/.pi/agent/extensions/` (today just `goal.ts`, a *copy* not a link). So a Codex
session has no `/usage`, no `/failover`, and no switch-back to Anthropic.

**The intended mechanism already exists but is UNTRACKED and unverified.** A previous
agent's "wire pi into dotfiles" work (brief:
`docs/handover/2026-08-30_wire-pi-into-dotfiles-brief.md`, research:
`docs/research/pi-unified-providers-and-dotfiles.md`) left these in the master
checkout, never committed: `scripts/pi_setup.py` (186 lines) + `bin/pi-setup`,
`tests/unit/test_pi_setup.py`, `tests/unit/test_pi_provider_integration.py`,
`tests/unit/test_pi_route.mjs`, `tests/e2e/pi-unified-tmux.py`, `config/pi/lib/`,
`config/pi/skills/`, `config/pi/{models,settings}.example.json`,
`config/pi/upstreams.json`, and the three older extensions. Also **modified but
uncommitted** tracked files from the same work: `bin/pi-claude-sub` (an
"Anthropic-only" argument guard + `PI_DOTFILES_LEGACY_CLAUDE_PID`), `scripts/install.sh`,
`.gitignore`, `bin/claude-usage`, `bin/waybar-claude-usage`. A remote branch
`origin/research/wire-pi-into-dotfiles` exists; check whether it is the same work or
older. **Ground-truth all of this before deciding anything** — `make test-unit` already
picks up the untracked tests (running `pi-setup` as a side effect: "Installed 1
resources … Rollback: pi-setup --rollback …" appears in the output, which a unit test
must never do against the real `~/.pi/agent`).

**(B) `make test-unit` is red** on one pre-existing failure:
`test_pi_provider_integration.ProviderIntegration.test_anthropic_route_and_deepseek_isolation`
(needs an OpenRouter key). Both Step 2 and the orchestrator hit it.

Binding decisions (see `docs/research/generic-llm-proxy.md` §"Operator decisions"): #1
pi stays on the OAuth pool via `pi-claude-sub` — do not change how Anthropic sessions
authenticate; #3 failover is notify-only.

## Your job

1. **Ground-truth (A).** Read `scripts/pi_setup.py` fully and the brief/research it came
   from. Determine: what it installs, whether it symlinks or copies, whether it is
   idempotent and reversible (it prints a rollback manifest), and whether it touches
   `auth.json`/`settings.json`. Diff the untracked tree against
   `origin/research/wire-pi-into-dotfiles`. Write a short verdict in your report:
   *land as-is / land trimmed / replace with a 10-line symlink step*. Prefer the
   **smallest** mechanism that makes `pi` load `config/pi/extensions/*.ts` — a symlink
   per file into `~/.pi/agent/extensions/` (idempotent, reversible, and exactly the
   guard `bin/pi-claude-sub` already checks: `[ ! -e ~/.pi/agent/extensions/llm-failover.ts ]`).
   If `pi_setup.py` is that mechanism with tests, land it; if it is 186 lines doing
   more than asked, land only the part you need and leave the rest untracked with a
   note.
2. **Land it.** Commit the chosen mechanism + its tests + the `config/pi/` files it
   needs. Run it for real on this machine once (`~/.pi/agent/extensions/` gets the
   links), then verify: `pi --model gpt-6-luna -p "/usage"` (or `-p "reply OK"` if
   Codex is out — check `llm-usage`) loads with no extension error, and
   `pi -p "/failover status"` prints the route ranking. If `~/.pi/agent/extensions/goal.ts`
   is a copy that diverged from `config/pi/extensions/goal.ts`, diff them and keep the
   newer content before linking.
3. **Fix (B).** Make `test_pi_provider_integration.py` skip cleanly when its
   prerequisites (OpenRouter key, whatever else) are absent — `skipUnless` with a
   named reason — and make sure **no unit test runs `pi-setup` against the real
   `~/.pi/agent`** (use a temp `PI_CODING_AGENT_DIR`). Decide per file whether the
   other untracked tests (`test_pi_setup.py`, `test_pi_route.mjs`, `tests/e2e/…`) are
   landed with the mechanism or left untracked; never leave `make test-unit` red.
4. **`bin/pi-claude-sub` modified hunks.** The uncommitted Anthropic-only guard is
   sound (it refuses `--provider deepseek` etc.). Commit it in its own commit if its
   behaviour is covered by a test you can run; otherwise leave it uncommitted and say so.
   Do not commit the other unrelated modified files (`hypr/*`, `nvim/*`, `toggle-power-mode`,
   `enroll-yubikeys.sh`, `install.sh` unless it's part of the mechanism).
5. **Report** `make test-unit` green with the count, and the exact `ls -la
   ~/.pi/agent/extensions/` after your step.

## Scope fence

- **You own:** `scripts/pi_setup.py`, `bin/pi-setup`, `config/pi/**` (excluding
  `llm-failover.ts` content — wiring only), `tests/unit/test_pi_*`, `tests/e2e/pi-*`,
  `bin/pi-claude-sub`, `scripts/install.sh` (only if the mechanism needs it),
  `~/.pi/agent/extensions/` (links only).
- **Do NOT touch:** `bin/claude-token-proxy`, `scripts/llm_usage.py`, their tests,
  `config/llm-proxy/`, `~/.pi/agent/{auth,settings,models}.json`, the running
  `claude-token-proxy.service`.
- Sibling running now: **Step 6** on `llm-proxy/step6-failover-live` owning
  `config/pi/extensions/llm-failover.ts` + `tests/unit/test_llm_failover.mjs` and
  `local/env`. It launches pi sessions via `pi-claude-sub -e …` explicitly, so your
  linking does not race it; but do not edit its two files.

## Constraints

- `CLAUDE.md`/`README.md` first. Commit hook: `type(scope): subject`, lowercase,
  imperative, ≤50 chars; blocks company names / secret-looking strings.
- Gates by name: `make test-unit` (green, report count); `python3 -m unittest
  tests.unit.test_pi_setup -v` if landed; the two live `pi -p` checks in job 2.
- Git: `GIT_EDITOR=true`; rebase on `origin/master`, linear, `git push origin
  HEAD:master`. The master checkout has uncommitted modifications — work in your
  worktree; copy the untracked files you decide to land INTO the worktree from
  `$DOTFILES` (they are not in git, so the worktree does not have them).
- Scratch under `$(pi-scratch dir llm-step5)`, never `/tmp`.

## Where to record findings

Commit bodies + "Step 5 — done" note in `docs/handover/llm-proxy-implementation.md`
(sha(s), verdict on `pi_setup.py`, gates by name, what stays untracked and why).
Raw output → `$NOTES/<project>/driver/agent-runs/2026-09-25/<HHMM>_llm-step5-output.md`
(`$NOTES=/home/gud1/sync/Vault`) with front-matter `model`, `cost_usd`, `branch`, `landed_in`.

## When done or blocked — report back to the parent

```bash
tmux send-keys -t "$PI_PARENT_PANE" -l "STEP5 DONE <sha> — <one line: what landed, gates, open items>"; tmux send-keys -t "$PI_PARENT_PANE" Enter
```
`PI_PARENT_PANE` is exported; fallback pane id `%1520`. Then stay idle.

## Cost guidance

Target ~$8. Stop at $15 with what you have committed and reported.
