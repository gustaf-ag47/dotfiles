# Jev in this Pi setup: observation-only pilot

Jev classifies a short delegated task as `interactive`, `build`, `research`, or
`mechanical`. It does **not** choose or switch models, alter task classes, authorize
tools, declare goals complete, compact sessions, or modify the token proxy.

## What runs

- `config/pi/lib/jev.mjs`: shared classifier, confidence gate, private result cache,
  daily budget, and metadata-only ledger. Uses Pi's native TypeSafe classifier.
- `bin/jev-classify`: command-line interface to the same module.
- `config/pi/extensions/jev.ts`: explicit Pi `/jev` commands; no automatic turn hooks.
- `config/pi/skills/delegate/scripts/delegate.sh`: observes only `--task` after
  validation and model probing, once per launch attempt. It never reads the brief
  for classification, never consumes the result as routing instructions, and skips
  observation for dry runs, queued jobs until launch, or missing task descriptions.
- `scripts/llm_usage.py`: displays local `classifier_activity`, separate from provider
  quota. It reloads the ledger even when using cached provider observations.

The checked-in defaults live in `config/llm-proxy/jev.json`: observation-only mode,
Jev `jev-1.13.0`, minimum confidence 0.6, up to 100 attempted calls/day and a $0.05
estimated daily budget, a 3-second classification timeout, and private bounded caching.
Confidence thresholds are pilot settings, not calibrated correctness guarantees.

## Credentials and installation

The existing user's key is stored outside git at
`${XDG_CONFIG_HOME:-$HOME/.config}/jev/api-key` with mode 0600 in a 0700 directory.
`PI_JEV_KEY_FILE` can point to another private file; `TYPESAFE_API_KEY` is also
supported. Nothing copies this key into Pi auth or tmux command arguments.

On another host, install/provide your own key privately, then:

```sh
cd "$DOTFILES"
bin/pi-setup --check
bin/pi-setup --apply
bin/jev-classify --status
```

The installer links the extension and shared helper; it does not distribute keys.
Restart Pi or `/reload` to see the command. No extra provider gateway or codemode
configuration is needed.

## Controls

In Pi:

```text
/jev status
/jev classify Rename a local variable from x to count
/jev off
/jev observe
```

These are local control commands, not chat-model prompts. `/jev off` disables
manual classification in that Pi session; `/jev observe` clears that session
override and returns to environment/config policy. These controls do not change
independent terminal processes or the repository's configuration.

For terminal/delegate observation:

```sh
# Disable for this launch and propagate the non-secret setting to its child:
PI_JEV_MODE=off bash "$DOTFILES/config/pi/skills/delegate/scripts/delegate.sh" ...

# Explicit classification; only this short synthetic text is sent:
printf '%s' 'Rename a local variable from x to count' |
  "$DOTFILES/bin/jev-classify" --task-stdin --source delegate

llm-usage
llm-usage --json
```

Set `mode` to `off` in `config/llm-proxy/jev.json` to disable the pilot by default
for all callers using this checkout; an explicit `PI_JEV_MODE` overrides it.
No action/apply mode exists. Existing explicit `--class` and `--model` selections,
quota policies and spending restrictions remain unchanged.

## Privacy, latency, and accounting

**Observation mode makes real, metered requests to TypeSafe.** Only the short
`--task` argument or explicitly submitted `/jev classify` text is sent. No automatic
brief, repository, conversation, or file collection occurs. Avoid sensitive details
in task titles, or disable the observer for that launch.

State is local under `${XDG_STATE_HOME:-$HOME/.local/state}/jev/`, protected by
0700/0600 permissions. Cache keys are hashes; the cache/ledger contain no raw task
text, credentials, prompts, or provider error payloads. Cached judgments still are
not permission to execute an action.

`llm-usage` shows observations versus attempted network calls, cache hits,
abstentions, failures, tokens, estimated USD, and latency. It is **local retained
activity**, not TypeSafe account-wide balance or an invoice. Failed/uncertain
requests do not magically become known-zero cost. The rate is explicitly
$0.042 per million input tokens, output free; Pi's bundled zero-price catalog
entry is not used for the estimate.

The delegate launcher enforces an additional 5-second outer timeout and discards
classifier stdout/stderr. Missing keys, dependency/config errors, low confidence,
budget exhaustion or timeouts must leave the ordinary launch path unchanged.

## Rollout

This pilot deliberately leaves `llm-failover.ts`, `routes.json`, `classes.json`,
`goal.ts`, and compaction untouched. Evaluate representative task labels and
actual downstream outcomes before proposing automatic routing. File triage is a separate opt-in capability with its own privacy controls;
see [context-efficient reads and file scouting](jev-context.md). It does not
change this task-classification pilot's routing policy.

## Verification on this host (2026-10-02)

- One real synthetic classification via the installed Pi classifier: a variable
  rename → `mechanical`, confidence **0.98**, **362 ms**, 420 input tokens and
  50 output tokens; estimated cost **$0.00001764**. No real brief/source was sent.
- Repeated CLI request and the installed Pi `/jev classify` command both hit the
  shared cache without another network call.
- `/jev off` skipped a different synthetic task; `/jev observe` restored the
  configured policy. Verified in tmux window `jev-pilot`.
- `llm-usage` correctly reports one network call, two cache hits, one skipped
  observation, no applied decisions, and approximately **$0.000018** estimated cost.
- State directory 0700; key, ledger, cache and budget files 0600. No credential
  content is copied to git, argv or tmux commands.
- 36 new offline helper tests plus 24 failover tests passed. Delegate integration
  tests cover task-only input, unchanged model/class, dry runs, missing helper,
  mode off, failures, and outer timeout. The combined local Python suite passed
  268 tests with one existing skip (including concurrent, separate freshness tests).

Research: [Pi routing investigation](research/jev-pi-routing.md),
[ten-levels-of-jev review](research/jev-ten-levels-review.md).
