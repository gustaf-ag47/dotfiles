---
name: machine-handoff
description: Hand every in-flight piece of work on this machine — running agents, worktrees, unpushed commits, untracked artefacts, pending questions — over to another machine so it continues there without loss and the target's Hermes knows. Direction-agnostic (laptop ↔ PC, any machine in machines.conf). Use when the user says "hand over to <machine>", "I'm going home", "take this to the laptop/PC", or a machine is about to go offline.
---

# Machine handoff

Moves all in-flight work from **this machine (source)** to a **target machine**,
then briefs the target's Hermes. Machine facts (ssh destination, users, sync
roots, handover dir, Hermes window) are private: they live in
`$LOCAL_CONFIG/machine-handoff/machines.conf` (the `$SYNC/state/dotfiles-local`
overlay — seed it from [machines.conf.example](machines.conf.example)),
overridable with `$MACHINE_HANDOFF_CONF`. Never hard-code or commit them —
this repo is public.

```bash
S=~/.pi/agent/skills/machine-handoff/scripts
$S/machines.sh list                      # known machines
src=$($S/machines.sh get "$(uname -n)")  # source facts (hostname(1) may be absent)
tgt=$($S/machines.sh get <target>)       # target facts: ssh, src_root, handover_dir, hermes
```

**Dry run by default.** Steps 1–3 are read-only; present the plan and wait for
the user's go before step 4. Only explicit standing authority in the invocation
("hand over and go") skips the confirmation. The hard deadline: when the source
shuts down, everything the target needs must already be on the target or a
remote.

## 1. Inventory the source (read-only)

```bash
$S/inventory.sh          # TSV on stdout, summary on stderr; see --help
```

It reports agent panes (`active|waiting|idle|dead`, skipping its own
`$TMUX_PANE`), repos under the source's `src_root` with dirty files / commits
on no remote / stashes, and linked worktrees — which live **outside** the sync
roots (`/tmp`, `~/.cache`, `~/worktrees`) and never sync.

Then judge, per lane — this is your work, not the script's:

- **Current vs stale.** `stale` rows (old last-commit) and years-old dirty
  clones get listed in the report, not handed over. For each unpushed branch,
  `git fetch` then `git cherry origin/<default> <branch>` — squash-merged work
  shows as already landed and needs no transfer.
- **Pane truth.** Read each agent pane's tail yourself. A crashed session
  showing "Resume this session with" is dead; an idle pane may hold a finished
  result or a question for the user. A lane blocked on a human gets a brief
  but **no agent** until the human answers.
- Also sweep valuable untracked artefacts outside git: briefs, reports, the
  source's own `<handover_dir>/*`, `~/.pi/agent/delegate-mailbox/*.md`
  (unprocessed completions).

## 2. Verify what syncs — never assume

Working trees under the sync roots sync via Syncthing; **`.git` may not**
(true for dotfiles; varies per repo). `/tmp` and `~/.cache` never sync.
Confirm per repo over ssh before declaring anything safe:

```bash
ssh "$tgt_ssh" "git -C <target_repo> rev-parse --verify <branch> --" 2>/dev/null
```

A branch absent on the target and on the remote exists only on the source.

## 3. Plan

Write the plan as a lane table (lane, state, evidence SHAs, action:
transfer+spawn / transfer+wait-on-human / report-as-stale / drop), show it,
and get the go (unless pre-authorized).

## 4. Transfer

- Push local-only branches **you or the user own** to their remote; verify
  with `git ls-remote`. Never push someone else's branch. Pin any force-push
  lease to an exact SHA (`--force-with-lease=<branch>:<sha>`); if rejected,
  `git range-diff` before overwriting anything.
- Copy valuable untracked files to the target:
  `scp <files> "$tgt_ssh:$tgt_handover_dir/<source>-$(date +%F)/"`
  (mkdir -p over ssh first).

## 5. Brief per lane on the target

One brief per lane in `$tgt_handover_dir/<source>-<date>/`, following
[the delegate handover template](../delegate/references/handover-template.md):
state with SHAs, numbered steps, scope fence, **explicit merge policy** (a
fresh agent can merge a PR within 20 s of booting — say "do not merge" when
you mean it), and where to report (the target's Hermes pane).

## 6. Start agents on the target for unblocked lanes

```bash
ssh "$tgt_ssh" "tmux new-session -d -s <lane> -c <repo> 'pi @<brief> \"Execute this brief.\"; exec zsh'"
sleep 20
ssh "$tgt_ssh" "tmux capture-pane -p -t <lane>" | tail -20
```

Verify the prompt was consumed: the context gauge off `0.0%` or a `Working...`
line. A booted child with an empty input box has no task.

## 7. Tell Hermes on the target — one message

```bash
ssh "$tgt_ssh" '~/.pi/agent/skills/hermes/scripts/hermes-send.sh "From <source> handoff: <lanes started + briefs dir + what waits on the user>"'
```

(hermes-send finds the window named per `hermes=` in the registry and queues
if busy. Fallback: `tmux send-keys -t <pane> -l "<msg>"` then a separate
`send-keys Enter`.) Confirm the acknowledgement:
`ssh "$tgt_ssh" '~/.pi/agent/skills/hermes/scripts/hermes-send.sh --tail 20'`.

## 8. Clean up the source, then report

- Destroy compose stacks **you started**, scoped by compose-project label.
- Remove **your own** worktrees; container-created root-owned files
  (`__pycache__`) go via `docker run --rm -v <wt>:/w alpine rm -rf /w/<path>`.
- Delete your merged local branches. Leave other agents' worktrees, stacks
  and panes alone — ask an agent to stop; never `pkill -f` (the pattern can
  match your own shell, measured) and never kill a pane mid-commit.

Report to the user: what moved where (paths + SHAs), what was left as stale,
what waits on them.
