# Workspace as code

`bin/ws` reconciles three things against one private file: the shell
environment, tmux sessions, and the delegated-agent lane manifests
`delegate.sh` writes. The schema lives here (public); the actual data lives
in the private overlay, never in this repo.

## Why a private data file

This repo is public. Area names, session names, repo remotes and filesystem
paths under `$SYNC` are not. `bin/ws` and `scripts/ws.py` are generic: they
take a `--workspace <path>` flag (or `$WORKSPACE_YAML`), defaulting to
`$LOCAL_CONFIG/workspace/workspace.yaml` (`$SYNC/dotfiles-local/workspace/workspace.yaml`,
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
only if present on this host — `$SRC/rissne`'s own hardware/boot-order
validators for the host layer. Exits non-zero only on hard failures (missing
env, a `/tmp` worktree); everything else is reported but not fatal.

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
`watch-child.sh` flips `status` to `closed` on every terminal verdict
(idle, window-gone, timeout). `ws up` only reopens lanes still `open`.

## Known limitations

- Parent/report targets are `session:window-name`, resolved to a pane at
  send time. Two independent conversations sharing one tmux window still
  collide on this address — give each its own window.
- `ws check`'s repo scan shells out to `git status`/`git rev-list` per
  declared repo; a large `repos:` list is O(repos), not cached.
- `ws up`'s lane reopen is a single `pi --continue` keystroke sequence with
  no readiness/landing verification (unlike `delegate.sh`'s multi-attempt
  prompt-landing check) — a session that isn't ready yet can drop it.
