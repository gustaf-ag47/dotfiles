---
name: delegate
description: Hand a task to a fresh sub-agent running in a new tmux window of the current session — an interactive pi session (using Pi's configured default unless a model is specified) booted with a complete written handover brief, a clean context window, and a reference to the parent that spawned it. Use when the user says "delegate this", "hand this off", "spin up an agent for X", when a task needs a fresh context window, or when several independent work items should run in parallel.
---

# Delegate to a sub-agent

Boots a **new interactive pi session in a new tmux window of the current session**,
hands it a written brief, and tells it who its parent is. The child keeps working
after you move on; you monitor it with `tmux capture-pane`.

```bash
~/.pi/agent/skills/delegate/scripts/delegate.sh --brief docs/handover/my-task.md \
  --task "fix the flaky daemon shell suite"
```

## The rule that makes delegation work: write the brief first

A delegated agent has **no memory of your conversation**. Everything it needs must be
in the brief — and the brief belongs in the repo, not only in the prompt, so the work
survives the session (state lives in git, not in a context window).

Write the brief to a file, then pass `--brief`. Use
[references/handover-template.md](references/handover-template.md) as the skeleton.
A brief that omits *why* or *what "done" means* produces an agent that solves the
wrong problem confidently.

Minimum contents:
- **Context** — what happened so far, with links to commits/PRs/docs, not recollection.
- **Job** — numbered, checkable outcomes.
- **Scope fence** — files/dirs it owns, and explicitly what it must not touch
  (critical when siblings run in parallel).
- **Constraints** — repo conventions (AGENTS.md), verification gates it must run.
- **Where to record findings** — an in-repo path it commits.
- **Cost guidance** — and what to do when blocked instead of burning budget.

## Options

| Flag | Purpose |
|---|---|
| `--brief <file>` | Brief the child reads first. Strongly recommended. |
| `--task "<text>"` | One-line summary; also names the window. |
| `--model <m>` | Prefer `provider/model`; defaults to Pi's configured model. |
| `--worktree <branch>` | Isolate a code-writing child in its own git worktree + branch off `origin/main`. |
| `--cwd <dir>` | Working directory (default: current). |
| `--agent <bin>` / `--provider <p>` | Launcher defaults to `pi` for every provider. Example: `--model openai-codex/gpt-6-astra` or `--model deepseek/deepseek-v4-pro`. |
| `--no-probe` | Skip the model availability check. |
| `--dry-run` | Show the plan, change nothing. |

## Parallel delegation

Give every child **its own `--worktree`** and a **scope fence naming its siblings' files**.
Two agents editing one checkout corrupt each other; two agents editing the same ratchet
constant or shared index file produce merge conflicts you resolve by hand later.

Expect shared-file collisions anyway (run indexes, ratchet ceilings). Tell each child to
re-measure rather than guess a number when it hits one.

## Monitoring

```bash
tmux capture-pane -t <session>:<window> -p | tail -20   # progress
tmux select-window -t <session>:<window>                # watch live
git -C <worktree> log --oneline origin/main..HEAD       # what it produced
```

An idle window with no `Working...` line means it finished or is waiting on input.
Check for commits/PRs before assuming success — an agent that exits cleanly without
committing has done nothing.

## The feedback loop

A delegated child runs to completion and then **sits idle forever**. Nothing wakes the
parent, so work stops until a human happens to look. Measured 2026-08-29: nine agents
finished and **22.5 hours passed with zero merges** — every one of them a single nudge
from progress.

`delegate.sh` therefore detaches `watch-child.sh` per child. It polls the child's pane
and, when the child goes idle, writes a durable record and nudges the parent:

```
notify : watching (nudges Work-Driver:speedup ci on idle)
```

**Two channels, deliberately.** The nudge is a keystroke, and keystrokes get dropped — a
TUI mid-turn swallows them without trace. So the *state* goes to a mailbox on persistent
disk (`~/.pi/agent/delegate-mailbox`, **not** a tmpfs worktree) and only the *pointer*
goes in the keystroke. A dropped nudge loses nothing; the record is still there for the
next turn. Never put the payload in the keystroke.

**Delivery is at-least-once, closed by an ACK (added 2026-09-07).** A single nudge is
not delivery: a parent mid-turn with its operator swallows the keystroke, and the
operator finds out before the parent does (measured same day, first session using the
watcher). The watcher now waits for the parent's pane to go idle, sends, and **re-sends
every `PI_DELEGATE_RENUDGE_SECS` (300) up to `PI_DELEGATE_MAX_NUDGES` (8) times until
the parent acknowledges** by moving the record into the mailbox's `ack/` subdirectory
(the nudge text contains the exact `mv` command). Unacked records survive in the mailbox
root either way.

**Parent duty — if you spawned children, this is on you:**
- When you process a completion (via nudge OR by reading the pane/output yourself),
  **ack it**: `mv <record> ~/.pi/agent/delegate-mailbox/ack/`. An unacked record means
  re-nudges keep landing in your input box.
- At the start of any turn where you suspect a child finished (or after being away),
  **sweep the mailbox**: `ls ~/.pi/agent/delegate-mailbox/*.md` — any record there is a
  completion you have not processed yet.

It watches **from the outside**, so a child that crashes, wedges, or simply forgets to
report is still reported — the loop must not depend on the child's cooperation.

Three verdicts: `idle` (finished), `never-started (prompt dropped)`, `window-gone`.
That second one matters: a child that never received its task must not be reported as
finished.

**A fresh child is not busy either.** Between the prompt landing and the first
`Working...` frame it looks exactly like a finished one, so the watcher requires a rising
edge — it must have seen the child busy, or seen its context gauge move off `0.0%` —
plus a startup grace window (`PI_DELEGATE_MIN_GRACE_SECS`, default 45s). Without that it
reports "finished" during startup, which is the same mistake as calling a not-yet-ready
TUI ready.

Knobs: `PI_DELEGATE_MAILBOX`, `PI_DELEGATE_POLL_SECS` (20), `PI_DELEGATE_IDLE_STREAK`
(3), `PI_DELEGATE_MIN_GRACE_SECS` (45), `PI_DELEGATE_WATCH_HOURS` (12). `--no-notify`
disables it.

Several children finishing together serialize their nudges under `flock`, so they cannot
interleave keystrokes into one corrupted prompt.

## Always verify the child received its task

The single most common failure is a child that boots perfectly and never gets its
prompt. It is **invisible**: the window exists, the banner rendered, the input box is
empty, and context sits at `0.0%` forever. Nothing errors.

Measured on 2026-08-29/30: **19 of 20 delegations** hit this, and the script reported
success for every one of them, because its check inspected `tail -3` of the pane while
the status bar carrying the gauge sits further up. Fixed, but check anyway:

```bash
tmux capture-pane -t <session>:<window> -p | grep -oE '[0-9.]+%/1\.0M' | tail -1
# 0.0%/1.0M  -> the prompt was DISCARDED, the child has no task
```

The script now scans the whole pane, requires positive evidence (gauge off `0.0%`, or
`Working...`), retries up to 3×, prints `prompt : consumed`, and **exits 3** if the
child never received its task — so a spawn loop can tell rather than moving on.

If you spawn several in a loop, verify each one before reporting that work started.

## Failure modes this script already handles

- **Swallowed keystrokes** — waits up to 180s for the context gauge to render, then
  settles 8s more, because a rendered status bar means the bar is painted, *not* that
  the input loop accepts keys. Do not key readiness off the model name: it can be
  missing while a long skills/extensions banner renders.
- **A `--worktree` child cannot see an untracked brief.** The worktree is a fresh
  checkout of `origin/main`, so a brief you just wrote in the parent checkout does not
  exist there — the child is pointed at a missing file and confidently invents a task.
  The script now copies the brief into the worktree at its repo-relative path, so the
  child can also commit it.
- **Prompts are sent with `send-keys -l`**, then submitted separately. Without `-l`,
  tmux parses words like `Enter` or `Space` inside your prompt as key names.
- **Parent attribution** comes from `$TMUX_PANE`, not `display-message -p '#S:#W'` —
  the latter reports whichever window the client is *looking at*, so an orchestrator
  spawning from a background pane told every child its parent was a random sibling.
- **Dirty prompt line** — sends `C-u` first, so leftover buffered input cannot
  concatenate with the launch command.
- **Dead model** — probes with a trivial prompt and refuses to boot into an exhausted
  quota pool. Quota is **per pool**: `claude-fable-5` can be exhausted (Fable/overage
  at 100%) while `claude-opus-5`/`claude-sonnet-5` are fine on the same account. Check
  `llm-usage`; a proxy "available" count can be misleading because it may reflect
  usage ratios rather than active cooldowns.
- **Multi-line prompts** — the handover is sent as a single line; `send-keys` submits
  at the first newline, so a multi-line prompt fires half-written.

## Put these in every brief

Earned the hard way; each one cost real time when it was missing:

- **`GIT_EDITOR=true git rebase --continue`.** Redirecting stdin does *not* stop git
  launching `$EDITOR`. An agent sat wedged for **20.7 hours** on nvim holding an empty
  `COMMIT_EDITMSG`, showing `Working...` the whole time with its cost frozen.
- **The exact test invocation.** If a suite is behind a build tag, a plain run compiles
  zero files and *passes*. An agent reported such a run as evidence in a PR body.
- **Who owns merges.** If you are running a merge train, say so — a child that
  self-merges pushes every sibling BEHIND and costs each a full CI cycle.
- **What it must not touch**, naming siblings' branches and shared files. Expect
  collisions in run indexes and ratchet constants; tell children to re-measure rather
  than copy a number from prose (one brief quoted a ceiling of 8 when the code said 4).
- **Read-only boundaries** for any shared environment, with the escape hatch: *report
  it and propose the commit, do not fix it on the box.*
- **Caches and scratch space live on persistent disk, never `/tmp`.** On hosts where
  `/tmp` is a small tmpfs, two children writing Go build/module caches there filled 8G
  and BOTH died mid-arc with ENOSPC (2026-09-07, ~$8 of work lost, one PR left half
  repaired). Name the exact cache path in the brief (e.g. a warm shared cache dir on
  the big volume) — "use a cache" without a path is how they end up in `/tmp`.

## Things the script cannot do for you

- **Never `pkill` a child mid-task.** It may hold a lock or be mid-commit. Ask it to
  stop, or kill the supervisor and let the in-flight step finish.
- **Rescue work before killing a window.** Children commit to a worktree branch that is
  often on tmpfs and unpushed. Push the branch, or the findings die with the window.
- Interrupting an agent TUI with `C-c` often does nothing — it ignores SIGINT and
  swallows the keystroke as input.
