---
name: delegate
description: Hand a task to a fresh sub-agent running in a new tmux window of the current session — an interactive pi session (using Pi's configured default unless a model is specified) booted with a complete written handover brief, a clean context window, and a reference to the parent that spawned it. Use when the user says "delegate this", "hand this off", "spin up an agent for X", when a task needs a fresh context window, or when several independent work items should run in parallel.
---

# Delegate to a sub-agent

Boots a **new interactive pi session in a new tmux window of the current session**,
hands it a written brief, and tells it who its parent is. The child keeps working
after you move on; you monitor it with `tmux capture-pane`.

```bash
~/.pi/agent/skills/delegate/scripts/delegate.sh --brief "$(ws route dotfiles | awk '{print $4}')/my-task.md" \
  --task "fix the flaky daemon shell suite" \
  --model anthropic/claude-sonnet-5 --min-context 1000000 \
  --owns 'tests/**' --after 'pr:gustaf-ag47/dotfiles#73:merged'
```

## The rule that makes delegation work: write the brief first

A delegated agent has **no memory of your conversation**. Everything it needs must be
in the brief. Store it in operator notes: the runs folder from `ws route <project>`
(fourth field). Keep briefs and raw reports out of the repo; commit only code or
project documentation. A `--worktree` launch may copy the brief into the child
checkout temporarily; do not stage that copy.

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
- **Where to record findings** — the operator-notes runs folder for reports; name
  any code or project documentation changes separately.
- **Cost guidance** — and what to do when blocked instead of burning budget.

## Decide before delegating

Implementation lanes implement **decided items only**. Record the chosen design,
acceptance tests and merge owner before launch. Open questions stay draft/ADR
questions in operator notes, not silently chosen implementation details. Delegate
investigation separately when a decision still needs evidence.

For risky work (shared contracts, migrations, auth, concurrency or production
changes), run an adversarial review of the brief/design before coding: have an
independent reviewer challenge failure paths, dependency order, ownership collisions
and verification gaps. Resolve evidenced defects and record accepted trade-offs
before handing implementation to the child.

Prefer small vertical PRs, each independently testable and green in CI. Every
implementation launch passes an explicit `--model`, `--min-context 1000000`, scoped
`--owns` globs and `--after` dependencies. If no predecessor exists, identify an
already-merged baseline PR explicitly; do not use branch ancestry as a proxy for
completed dependency work. Check the launch summary's verified model
and capacity; a successful availability probe alone is not model verification.

## Coordination contract

Steer a running child with `delegate-send <session:window-or-%pane> --file <message>`
(or `--text <literal-message>`). The durable record is injected in-band at the next
turn boundary. Use a file for multiline text or shell metacharacters. Do not type
messages into panes; reserve pane input for slash commands and launcher bootstrap.
`delegate-send` prints the record path. Its `state/<filename>.json` transitions from
`queued` to `accepted` (Pi queue) to `delivered` (message started); `ack/` retains the
payload. Delivery acknowledges receipt, not implementation of the instruction.
Pending steering survives session restart and may be replayed: make instructions
idempotent. A child needs the updated mailbox extension loaded (`/reload`).

The child sends **one result or blocker**, never a chat ACK, receipt or relay:
`<task>: <PASS|BLOCKER|DONE|FAILED> <sha-or-none> - <report path>`.
Use a real commit SHA (at least 7 hex digits) or literal `none`, and a real path
without spaces or angle-bracket placeholders. **Every DONE line cites a real SHA
and a successful CI run ID for that exact SHA:**
`<task>: DONE <sha> - <report-path> ci:<run-id> [pr:<number>]`.
The brackets mean optional syntax, not literal characters. Tokens must be in that
order. `pr:<number>` asserts the SHA is that PR's **current head**, and the green
CI run must list that PR and head SHA in its GitHub association. This supports
unmerged work ready for review; it does not assert a merge. For a merge-commit
claim, omit `pr:` and use the merge SHA with its post-merge CI run. Unknown tokens,
stale PR heads and unrelated CI runs fail verification.
Use BLOCKER/FAILED rather than DONE when evidence is missing. Legacy lines remain
readable, but are not an exemption for newly delegated work. The watcher recognizes this line
and the older `PARENT: … done|accepted` handshake. A BLOCKER or FAILED line
ends automatic `/goal` retries; it does not claim that work passed.
Keep reports in their designated path; never git-commit or push the operator Vault.
At 300k tokens of context (the TUI footer's absolute count, not a percentage), write
a handover with remaining work, evidence and paths; report that pointer and stop.
Briefs reference this rule by name; they do not restate a number. A parent verifies
results against gates and CI itself. For DONE, run `delegate-verify '<result-line>'`
in the child's checkout (or pass `--cwd`/`--repo`). The mailbox extension runs it
automatically on DONE completion records and annotates PASS/FAIL evidence. Missing
commits, unreachable PR ancestry, absent/pending/red CI and false merge claims fail.
Merged PRs must have their merge commit on the base branch. `--merged` or report
metadata `merged: true` explicitly asserts a merge; optional `ci_run: <id>` report
metadata or the required new-work `ci:<id>` result suffix ties a run to the exact
claimed SHA. Legacy result lines are still parsed. Automatic verification is evidence, not merge
authorization or a substitute for the repository's own tests/review gates.

When the brief's DONE condition is met, report and stop, even if more work is in
sight — do not widen scope. The parent re-delegates follow-on work to a new session.

Before the final report: destroy your own stack (`scripts/worktree-stack.sh destroy`
if you started one), remove images you built (`docker rmi`, never `docker system
prune` or anything you did not create), and confirm with `df -h /`.

Parents never sleep-poll a child's pane with `tmux capture-pane` in a loop; the
mailbox delivers completions in-band (see In-band delivery below). After push, call
`ci_wait` with the PR number and end the turn; never sleep or poll for CI. Keep the
interactive/RPC session open: the tool wakes it with a verdict or timeout. On a
superseded head, register the new head. After wake-up, check the merge gates and
continue owning the merge. If the tool is unavailable, return the verification
command to the parent rather than blocking in `gh --watch`.

Merge only through `merge-pr.sh` (`scripts/merge-pr.sh`, wraps `gh pr merge`): it
appends pane/run-id/pr/head-sha to `~/.pi/agent/merge-log.tsv`, and refuses when the
caller's brief has a standalone current-PR hold such as `Merge: no-merge`,
`Do not merge this PR.` or `Do not merge PR #123.` (for PR 123), or when the PR or
any of its commits were authored by someone other than the agent identity.
Conditional safety prose (for example, "do not merge onto a red base"), quoted/code
examples and directives naming other PRs are not blanket holds. Continue to enforce
the actual CI/base/review gates regardless of whether an explicit hold exists.

One coordinator owns the queue. Owners merge their own reviewed, green PRs unless
the brief assigns merge ownership to the coordinator or declares a deploy hold;
do not add an unassigned slot round trip. After delegation,
decide and record rather than asking repeatedly. A genuine fork gets at most one
question, at the top, with a recommended default. Before closing a PR as superseded,
check local branches and worktrees for unpushed work. Before cancelling a deploy,
read its current stage. Reviews block only for a failing Gate, an AGENTS.md violation
or an evidenced defect. A brief must not invent policy: verify the enforcement
reader before claiming a ratchet blocks.

`pi-claude-sub` is a compatibility shim to `pi`, not a separate orchestration skill;
the same coordination contract applies when it launches a child.

## Options

| Flag | Purpose |
|---|---|
| `--brief <file>` | Brief the child reads first. Strongly recommended. |
| `--task "<text>"` | One-line summary; also names the window. |
| `--model <m>` | Prefer exact `provider/model`; verified against the live footer before handover. |
| `--min-context <tokens>` | Minimum rendered context capacity; retries the model pin once, exits 4 without delivering work on failure. |
| `--worktree <branch>` | Isolate a code-writing child in its own git worktree + branch off `origin/main`. |
| `--cwd <dir>` | Working directory (default: current). |
| `--agent <bin>` / `--provider <p>` | Launcher defaults to `pi` for every provider. Example: `--model openai-codex/gpt-6-astra` or `--model deepseek/deepseek-v4-pro`. |
| `--no-probe` | Skip the model availability check. |
| `--after <condition>` | Queue until every PR/branch/lane dependency holds; repeatable. |
| `--owns <glob>` | Reserve a repository-relative file scope; repeatable. |
| `--allow-overlap` | Explicitly permit a reported ownership conflict. |
| `--dry-run` | Show the plan, change nothing. |

## Dependency-gated launches

Pass repeatable `--after pr:owner/repo#123:merged`, `--after branch:feature:merged`,
or `--after lane:run-id:done`; all conditions must hold before the launcher creates
any window or worktree. Branch conditions require a MERGED PR with that exact head
branch in the target repository (`gh pr list --head <branch> --state merged`). A
fresh branch at the base commit, no PR, or an open/closed-unmerged PR stays queued;
Git ancestry is never completion evidence. Squash merges work too. Use a specific
PR condition when branch names are reused across multiple pieces of work. Lane conditions require a
closed lane with `result_status: DONE` in the same project's lane directory.
API/ref errors keep the launch queued, with `last_error` evidence in its manifest.

`delegate-queue list|cancel <run-id>` uses the unrouted lane directory by default;
pass `--directory <runs>/.lanes` for a project. Queued manifests live under
`.lanes/queued/` so `ws up` cannot accidentally resume one before its dependencies.
A user systemd timer checks every 30 seconds. Cancellation never kills a started
agent. Transient timers do not survive reboot; inspect queued manifests and run
`delegate-queue _tick <manifest-path>` to retry a retained queue after reboot.

## File ownership

Pass repeatable `--owns 'path/**'` for each implementation lane. Claims are scoped
to the Git common directory (worktrees of one repository share ownership) and
reserved under a lock before window/worktree creation. Active overlapping claims
print the owner and refuse launch; `--allow-overlap` is an explicit coordinated
override, not the default. Closed lanes release their claims; failed launches release
reservations. A crashed lane with an open manifest remains owned until reconciled.

Globs use case-sensitive `fnmatch` semantics: `*` can match `/`; paths are relative
to the repository. Wildcard/wildcard intersection is conservative: compatible literal
prefixes conflict even when suffixes might be disjoint. Prefer directory scopes.
Run `delegate-owns-check` before committing (the launcher exports the manifest path),
or pass `--manifest <lane.json>`. It lists staged paths outside ownership and exits
nonzero; a lane with no ownership declaration cannot pass this check.

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

**Self-continue (2026-09-28).** Briefed children get a default `PI_DELEGATE_GOAL`; the first
time the watcher sees the child idle without a results/blocker line it sends
`/goal <condition>` so `goal.ts` keeps the child working (up to `PI_GOAL_MAX_TURNS`, 25)
instead of stopping after one slice and calling the rest "blocked". Only a second idle
nudges the parent. Watchers now run as `systemd-run --user` units (fallback `setsid`) because
`nohup` did not survive the tool-call shell that spawned them — seven delegations in a
row produced zero nudges.

A delegated child can finish and sit idle. Without a watcher nothing wakes the
parent, so work stops until a human happens to look. Measured 2026-08-29: nine agents
finished and **22.5 hours passed with zero merges** — every one of them a single nudge
from progress.

`delegate.sh` therefore detaches `watch-child.sh` per child. It polls the child's pane
and, when the child goes idle, writes a durable record and nudges the parent.
To avoid changing the rising-edge, grace, /goal and ACK/re-nudge state machine,
watchers remain per-child for now. After 10 minutes, their default poll interval
increases from 20 to 60 seconds, reducing tmux captures by two thirds for old
lanes. Explicit `PI_DELEGATE_POLL_SECS` overrides both intervals:

```
notify : watching (nudges Work-Driver:speedup ci on idle)
```

**In-band delivery (2026-10-03).** Parents that are pi sessions load
`delegate-mailbox.ts` (via `pi-setup`), which watches the mailbox from
inside the session and injects records addressed to its `$TMUX_PANE` with
`pi.sendMessage(..., {triggerTurn: true})`, auto-acking on delivery. Keystroke
nudges below are the fallback for parents without the extension — measured
2026-10-03: a child finished, 8 keystroke nudges fired, none reached the
parent's context; the operator closed the loop by hand.

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
  **ack the durable mailbox record** (this is bookkeeping, not a child chat ACK): `mv <record> ~/.pi/agent/delegate-mailbox/ack/`. An unacked record means
  re-nudges keep landing in your input box.
- At the start of any turn where you suspect a child finished (or after being away),
  **sweep the mailbox**: `ls ~/.pi/agent/delegate-mailbox/*.md` — any record there is a
  completion you have not processed yet.

It watches **from the outside**, so a child that crashes, wedges, or simply forgets to
report is still reported — the loop must not depend on the child's cooperation.

For lanes with a Git checkout, the watchdog discovers the branch's PR (or uses a
`pr` number/URL recorded in its manifest). An idle child, or one displaying `ci_wait`,
with a DIRTY/BEHIND PR or failed required checks gets a durable rebase/fix steer;
the parent receives the same blocker. Without configured required contexts, all
reported checks are considered. Draft PR check failures are ignored: some repos
intentionally fail verdict jobs when draft CI is disabled. Converting to draft clears
red-check stall/escalation state; marking ready restores normal check monitoring.
DIRTY/BEHIND conflicts still alert, even on drafts. A stalled lane stays open instead of being reaped
as a completion. Repeated alerts are deduplicated by PR head and reason.
`PI_DELEGATE_STALL_POLL_SECS` defaults to 60; `PI_DELEGATE_PARENT_IDLE_MINUTES`
defaults to 10 before an additional parent-idle alert. State is under mailbox
`watchdog/`. API failures are logged as unknown, never reported as green.

Watcher verdicts identify idle, never-started prompts and missing windows; idle
alone is not proof of completion. The watcher does not yet distinguish an idle
provider error from other idle stops. Its mailbox record includes the pane tail
for diagnosis.
That second one matters: a child that never received its task must not be reported as
finished.

**A fresh child is not busy either.** Between the prompt landing and the first
`Working...` frame it looks exactly like a finished one, so the watcher requires a rising
edge — it must have seen the child busy, or seen its context gauge move off `0.0%` —
plus a startup grace window (`PI_DELEGATE_MIN_GRACE_SECS`, default 45s). Without that it
reports "finished" during startup, which is the same mistake as calling a not-yet-ready
TUI ready.

Before probing, the launcher waits for a selected provider to become routable via `llm-wait`. Set `PI_DELEGATE_WAIT_MAX` (default `2h`) to bound that wait; a timed-out Codex wait can use the alternate-model/probe fallback only when no explicit `--model` was supplied.

Host admission runs before the provider probe and before creating a worktree/window:
Linux CPU PSI `some avg60 > 40`, load1 per `nproc > 3`, or MemAvailable `< 6 GiB`
queues in 30-second intervals for `PI_DELEGATE_LOAD_WAIT_MAX` seconds (default
1800), then exits 5. Tune via `PI_DELEGATE_CPU_SOME_MAX`,
`PI_DELEGATE_LOAD_PER_CORE_MAX`, `PI_DELEGATE_MEM_AVAILABLE_MIN_GIB`;
`--force` skips it, `--dry-run` reports the verdict without waiting. Hosts
without CPU PSI skip admission. The legacy 15%-of-total memory guard was
replaced so `--force` applies consistently.

Finished-child reaping uses one shared `pi-delegate-reap.timer` (5-minute
checks). Run `make install` / `pi-setup --apply` to install the new unit and
script, then `systemctl --user daemon-reload && systemctl --user enable --now
pi-delegate-reap.timer`. The launcher also starts an already-installed timer.
`reap-children.py --dry-run` reports eligible windows without changing them.
It scans only `~/.pi/agent/delegate-lanes/` (manifest symlinks registered at
launch), requires a real result and ACK, checks exact tmux window identity,
observes ≥`PI_DELEGATE_REAP_IDLE_MIN` (30) minutes idle, and refuses dirty,
untracked or unpushed worktrees. It closes only the window, never removes a
worktree; every reap goes to `~/.pi/agent/reap-log.tsv` beside merge-log.tsv.

Knobs: `PI_DELEGATE_WAIT_MAX` (2h), `PI_DELEGATE_MAILBOX`, `PI_DELEGATE_POLL_SECS` (20 then 60 after 10m), `PI_DELEGATE_IDLE_STREAK`
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
- **A `--worktree` child cannot see a brief outside its checkout by default.**
  The script copies a brief into the child worktree temporarily. For an external
  operator-notes brief, this is `DELEGATE_BRIEF.md`; leave it untracked and never
  commit it.
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
