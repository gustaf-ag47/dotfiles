---
name: hermes
description: Work with the Hermes Agent running in tmux as a peer — send it a task or update, hand it work on its own files (crons, skills, memory, ~/.hermes), take its DONE/BLOCKER report lines, and verify them. Use when the user says "tell Hermes", "ask Hermes", "update Hermes on the work", "let Hermes run it", or when a change touches paths that Hermes' crons, skills or memory reference.
---

# Hermes Agent as a peer

Hermes is a long-running Nous Research agent (`hermes chat --cli`) in a tmux
window, usually named `hermes`. It owns the scheduled side of the workspace:
crons, monitors, project notes, skills and memory under `~/.hermes`. You
reach it the same way it reaches you: one line typed into the other's pane.

## Send

```bash
S=~/.pi/agent/skills/hermes/scripts/hermes-send.sh
$S --where
$S --state
$S "<one-line message>"
$S --tail 20
```

`hermes-send.sh` finds the single window named `hermes` (or
`$HERMES_TMUX_TARGET`), types the message literally, presses Enter
separately, and prefixes `/queue` when Hermes is busy. The prefix matters:
Hermes' default `busy_input_mode` is `interrupt`, so a plain message to a
busy Hermes **aborts the run it is in**. Use `--mode steer` only to correct
the run in flight, and `--mode interrupt` only when that run is wrong.

The message is one line: a newline submits it half-typed. Long is fine.

## Write the message

Hermes acts on what the line carries, so give it the whole frame:

1. **Who and where:** you are `<session>:<window-name>`; reply there.
2. **Authority:** who decided ("the user approved on <date>") and what is
   out of scope or parked.
3. **Evidence measured:** counts, ids, paths, SHAs, from commands you ran
   just now.
4. **Numbered items**, each with an owner and a done condition. Ask for one
   line per item: `<task>: DONE|BLOCKER <sha|none> - <path or note>`.
5. **Boundaries:** what it must not start, touch or decide.

Then end your turn. Its reply arrives in your pane as a new user message;
you don't need to poll or sleep. If you need the live state, read
`$S --tail`.

## Ownership

- **Hermes alone edits its own files:** cron jobs (`~/.hermes/cron/jobs.json`
  and its prompts), skills, memory, scripts and config. When your change
  moves a path, renames a repo or retires a window those files reference,
  `grep` them, send Hermes the list of hits, and let it make the edits. Read
  them yourself only to verify.
- **You own your lanes:** briefs, delegated sub-agents, PRs and merges you
  started. Hermes may dispatch lanes too; its lanes report to it, unless
  the brief names you.
- **The human decides** secrets, spending, deletions and destructive or
  irreversible actions. Hermes knows this list; don't relay those decisions
  through it.

## Addressing

Address every pane, yours and Hermes', as `session:window-name`, where the
window name is unique and the window has a single pane. Pane ids (`%123`)
change across tmux restarts, and window indexes shift whenever a window
closes. When Hermes or a brief records a parent as `%id`, an index, a raw
session id like `$1`, or a generic name (`zsh`, `bash`, `pi`), ask for the
name instead. Keep your own window name unchanged while replies are due.

## Verify its claims

A DONE line is a claim. Before accepting or relaying it, read back the
state it names:

- merged PR: `gh pr view <n> --json state,mergeCommit` and the base branch
  run for that commit;
- file edits: `grep` or `sed -n` the exact lines;
- cron changes: `hermes cron list` (read-only for you);
- moved or removed things: `ls` the old and new path.

Read the source the way its owner does: parse note frontmatter as YAML and
glob patterns with `fnmatch`. A quick regex over `tmux: ["…[0-9]*"]` stops
at the first `]` and reports false misses.

Hermes is usually right and sometimes corrects you; it can also report a
step done that only got started. The read-back settles it either way.
Accept with the evidence, or send back the specific gap in one line.

## Its context

Hermes' status bar shows its context use (`~284K/1M`). Near its handover
limit, it writes a handover and a successor continues. Resend open items to
the successor with their ids rather than assuming they carried over.
