# Pi delegation completion contract

A delegated child sends one terminal result or blocker line:

`<task>: <PASS|BLOCKER|DONE|FAILED> <sha-or-none> - <report path>`

The SHA is at least seven hexadecimal digits, or the literal `none`. The path is a real path without spaces or placeholders. At about 80% context the child writes a handover with remaining work and sends its path as the report. Briefs specify who owns merging; a coordinator-owned merge is an exception to owner-self-merge. Raw Vault reports are not git artifacts; only repository changes are committed or pushed when the task calls for it.

`watch-child.sh` recognizes all four terminal statuses and the legacy `PARENT: … done|accepted` handshake. A BLOCKER or FAILED line prevents its one automatic `/goal` continuation, but is not a PASS verdict. ACK and progress messages and template placeholders are not terminal. The watcher still produces its durable mailbox record on idle; the parent pi extension ingests and acknowledges it. That mailbox ACK is bookkeeping, not child chat traffic.

Completion matching joins terminal-wrapped lines (`capture-pane -J`) and avoids
`grep -q` pipeline SIGPIPE false negatives on long histories. Task labels may contain
colons, but the terminal record must end at its report path. The launcher resolves
automatic session targeting from its own pane, not whichever client is focused;
numeric session names use an explicit session target when creating a window.

The watcher currently reports `idle`, `never-started`, `window-gone` or timeout. It does **not** identify a provider-error stop separately, and idle is not proof of successful work. The fallback nudge still uses tmux keystrokes and is not collision-safe; mailbox delivery by the pi extension is the safer path. Error-idle recovery, readiness checks and collision-safe fallback need separate runtime changes and tests.

## Verification

- Before the parser change, `python3 -m unittest tests.unit.test_delegate_contract -v` failed for PASS, DONE, BLOCKER and FAILED because the watcher sent `/goal` after each.
- After the change, `python3 -m unittest tests.unit.test_delegate_contract tests.unit.test_jev_delegate -v`: 11 tests passed after the convergence follow-up, including wrapped/long records
  and numeric/own-pane session targeting. The tests use fake tmux and a temporary HOME; no user panes are touched and no model/network call is made.
- `bash -n config/pi/skills/delegate/scripts/{delegate,watch-child}.sh`: passed.
- `shellcheck config/pi/skills/delegate/scripts/{delegate,watch-child}.sh`: passed.
- `git diff --check`: passed.
- `make test-unit`: 329 tests passed, 1 skipped (provider-integration opt-in).

Limitations: this verifies the watcher process with fake tmux, not a real Pi TUI or mailbox extension end to end. A child whose result line has scrolled beyond the captured 400-line history can still receive one `/goal`. The default goal no longer requires a pushed Vault report, but an explicit task brief can independently require pushing repository changes.
