# Brief — <one-line title of the job>

**Agent:** delegated pi sub-agent, model `<model>`, worktree `<path>`, branch `<branch>`.
**Parent:** booted from tmux window `<parent>` (run id `<id>`). **Date:** <YYYY-MM-DD>.

## Context

What has happened so far, in enough detail that someone with **no memory of the
originating conversation** can act. Link to evidence rather than recalling it:
commits, PR numbers, spec/ADR paths, incident docs, previous agent-run outputs.

State what is already known to be true, and what is still assumption. If a previous
agent or the operator made a decision that constrains this work, say so explicitly and
name it — the child cannot infer intent it never saw.

## Your job

1. Numbered, checkable outcomes — not vibes.
2. Say what "done" means for each one.
3. If something is investigation-first, say so: "root-cause before changing code".

Prefer outcomes over instructions. A capable agent given the goal and the constraints
will find a better route than a step list written by someone not looking at the code.

## Scope fence

- **You own:** `<paths>`
- **Do NOT touch:** `<paths owned by sibling agents, or out of scope>`
- Sibling agents running in parallel right now: `<list, or "none">`
- **Shared files:** `<plan/index/ratchet files touched by more than one lane, and who
  owns edits to each — re-measure before writing a number into one, do not copy from
  prose>`
- **Merge:** `<who may merge this work — self once checks are green, the
  coordinator, or "no merge: <reason>">`

## Constraints

- Read `AGENTS.md` (and any per-directory `CLAUDE.md`) fully before acting.
- Repo conventions that apply here: <no comments in Go code / Docker-first / GitOps /
  no backwards-compat shims / ratchets are shrink-only / …>
- Verification gates you must run and report **by name**:
  ```bash
  <exact commands>
  ```
  A `-run` filter that matches nothing exits 0 — confirm the tests actually ran.
- Git: use `GIT_EDITOR=true` for any rebase/merge continuation so it cannot hang.
  `main` may enforce linear history — check before choosing a merge strategy.

## Where to record findings

Write briefs, research, audits and raw reports to operator notes (the runs
folder, fourth field of `ws route <project>`). Name the report's absolute path
here. Commit and push only code and project documentation when the task calls
for them. Include what changed, gates run, limits and evidenced out-of-scope
findings. Never commit or push operator notes.

Send the parent **one results-or-blocker line only**:
`<task>: <PASS|BLOCKER|DONE|FAILED> <sha-or-none> - <report path>`.
No ACK, receipt, progress relay or repeated unchanged verification. At 300k tokens
of context (the TUI footer's absolute count), write a handover file with state,
remaining work, evidence and paths; send its path in the line above and stop.

## When blocked

Do not improvise past a genuine blocker. Record what blocked you, what you tried, and
what would unblock it; leave the work in a reviewable state; stop.

## Cost guidance

After push, call `ci_wait` with the PR number and end the turn; never sleep or poll
for CI. Keep this interactive/RPC session open for the in-band wake-up. On wake-up,
verify the current head and merge gates, then continue under the assigned merge
ownership. If superseded, register again; if unavailable, hand back the verification
command instead of blocking in `gh --watch`.

Target ~$<n>. If you exceed it with no clear progress, write up what you have and stop.
