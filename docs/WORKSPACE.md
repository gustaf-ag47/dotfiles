# Workspace as code

`bin/ws` reconciles three things against one private file: the shell
environment, tmux sessions, and the delegated-agent lane manifests
`delegate.sh` writes. The schema lives here (public); the actual data lives
in the private overlay, never in this repo.

## Why a private data file

This repo is public. Area names, session names, repo remotes and filesystem
paths under `$SYNC` are not. `bin/ws` and `scripts/ws.py` are generic: they
take a `--workspace <path>` flag (or `$WORKSPACE_YAML`), defaulting to
`$LOCAL_CONFIG/workspace/workspace.yaml` (`$SYNC/state/dotfiles-local/workspace/workspace.yaml`,
which is Syncthing-synced but not a git repo).

## Schema

A restricted YAML subset: nested mappings, lists of mappings, scalar
strings. No flow style, no anchors, no multi-line scalars — see
`scripts/ws_yaml.py` for exactly what's supported.

```yaml
env:
  SYNC: /home/example/sync
  NOTES: /home/example/sync/Vault
  DOTFILES: /home/example/sync/src/dotfiles
  SRC: /home/example/sync/src
  WORKTREES: /mnt/example-nvme/scratch/tmp
areas:
  - name: widgetco
    session: Widgetco
    cwd: /home/example/sync/src/widgetco/app
    runs: /home/example/sync/Vault/Widgetco/agent-runs
projects:
  - name: widgetco
    area: widgetco
    window_prefix: sub-
  - name: widgetco-admin
    area: widgetco
    cwd: /home/example/sync/src/widgetco/admin
    window_prefix: adm-
repos:
  - path: /home/example/sync/src/widgetco/app
    remote: git@github.com:example/widgetco-app.git
    area: widgetco
    autosync: false
units:
  - name: tmux.service
  - name: ws-up.service
```

- `areas`: one entry per tmux session/area. `session`, `cwd` and `runs` are
  the defaults a `project` in that area falls back to.
- `projects`: a more specific routing target than its area. Anything it
  doesn't set (`session`, `cwd`, `runs`, `window_prefix`) falls back to its
  `area`. `window_prefix` defaults to `sub-` if neither sets it.
- `repos`: declared checkouts `ws check` inspects for dirty/ahead/behind
  state. `remote: none` is a valid value for a local-only repo.
- `units`: systemd `--user` unit names `ws check`/`ws up` expect enabled.

## Subcommands

```
ws route <project|area>
```
Prints `session window-prefix cwd runs` (space-separated) for the most
specific match: a `projects` entry by name, else an `areas` entry by name.
`delegate.sh --project <name>` shells out to this to fill in `--session` and
`--cwd` (unless the caller passed them explicitly).

```
ws check
```
Drift report: required env vars, which declared sessions are missing and
which live sessions aren't declared, dirty/ahead/behind repos, worktrees
under `/tmp` (forbidden — see `delegate.sh`'s `WORKTREES` guard), pane ids
(`%NNNN`) found in `~/.hermes/cron/jobs.json`, declared units that aren't
enabled, open lane manifests with no matching tmux window, and — best effort,
only if present on this host — `$SRC/homelab`'s own hardware/boot-order and
live-drift validators for the host layer. Exits non-zero only on hard failures (missing
env, a `/tmp` worktree); everything else is reported but not fatal.

```
ws lane close <target> [--result "<line>"] [--dry-run]
```
Sets `status: closed` and `finished_at` on the manifest named by `<target>`
(a bare run id, resolved the same way as `ws lane set`, or an explicit path).
With `--result`, the line is parsed the same way `watch-child.sh` parses a
pane's result line (see below) and the resulting `result`/`result_status`/
`result_sha`/`result_path` fields are written too. For lanes with no
watcher — adopted lanes, Hermes' own — this is how a result becomes durable
without a pane to scrape.

```
ws lane set <target> [key=value ...] [--result "<line>"] [--dry-run]
```
`--result` is the same parse as `ws lane close --result`, but does not touch
`status`: it only fills in the result fields and `finished_at`. Combine with
a `status=closed` assignment to do both in one call.

```
ws lanes --finished-since <ISO> [--json]
```
Lists every manifest (open or closed, across all declared lane dirs) whose
`finished_at` is strictly after the given UTC ISO-8601 cursor, sorted by
`finished_at` ascending. This is what a cron reading lane outcomes into
project notes calls; each row (or JSON object, under `--json`) has exactly:
`run_id`, `session`, `window`, `brief`, `result`, `result_status`,
`result_sha`, `result_path`, `finished_at`, `cost`, `mailbox_record`. A
manifest with no `finished_at` (still open, no terminal verdict yet) never
appears. `--json` emits a JSON array; without it, one line per lane.

```
ws up [--dry-run] [--non-interactive]
```
Creates any declared session that doesn't exist yet (each with an explicit
`-c <cwd>`, so a session's start directory never depends on where its shell
happened to launch), enables any declared unit that isn't, and handles open
lane manifests: `resume: auto` lanes are reopened immediately; everything
else is listed and reopened only after one confirmation (skipped entirely
under `--non-interactive`, which is what `ws-up.service` passes at login).
Reopening runs `pi --continue` in the lane's recorded `cwd`.

## Lane manifests

`delegate.sh` writes `<runs>/.lanes/<run-id>.json` at launch (`<runs>` from
`ws route`, or the lowercased session name as a fallback, or
`$NOTES/.unrouted-lanes` as a last resort): `run_id`, `session`, `window`,
`cwd`, `branch`, `model`, `brief`, `pi_session` (filled in later, currently
always `null`), `parent`, `resume` (`auto|confirm`, from `delegate.sh
--resume`, default `confirm`), `status` (`open`→`closed`), `created_at`.

`watch-child.sh` flips `status` to `closed` on every terminal verdict (idle,
window-gone, never-started, watch-timeout) and, in the same atomic write,
records what the child actually reported — the result line a task's contract
requires (`<task>: PASS|BLOCKER|DONE|FAILED <sha|none> - <path>`), scraped
from up to 400 lines of pane history:

- `result`: the last matching line, verbatim, or `null` if the child never
  printed one (window-gone, a timeout, a dropped prompt, ...);
- `result_status`: the `PASS|BLOCKER|DONE|FAILED` token from that line, or
  the verdict itself (`idle`, `window-gone`, `never-started...`,
  `watch-timeout-...`) when there's no line to parse;
- `result_sha` / `result_path`: the sha (or `none`) and report path from the
  line, or `null`;
- `finished_at`: UTC ISO-8601 timestamp of the terminal verdict;
- `cost`: the pane's last `$N.NN` cost figure at verdict time, or `null`;
- `mailbox_record`: path to the durable record `watch-child.sh` writes under
  `$PI_DELEGATE_MAILBOX`.

`ws lane set --result` / `ws lane close --result` write the same five result
fields from a line handed to them directly, for lanes with no watcher.
`ws up` only reopens lanes still `open`.

## Known limitations

- Parent/report targets are `session:window-name`, resolved to a pane at
  send time. Two independent conversations sharing one tmux window still
  collide on this address — give each its own window.
- `ws check`'s repo scan shells out to `git status`/`git rev-list` per
  declared repo; a large `repos:` list is O(repos), not cached.
- `ws up`'s lane reopen is a single `pi --continue` keystroke sequence with
  no readiness/landing verification (unlike `delegate.sh`'s multi-attempt
  prompt-landing check) — a session that isn't ready yet can drop it.
