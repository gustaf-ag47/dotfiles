# Context-efficient reads with Jev

This is separate from `/jev` task classification. The context extension is
**off by default**: new Pi sessions do not automatically send source files or
add scouting tools to the model's prompt.

## Modes

After installation, restart Pi or `/reload`:

```text
/jev-context status
/jev-context local
/jev-context on
/jev-context off
```

- **local:** use a freshness-aware `read_context` wrapper. No file content is sent
  to Jev. Normal reads remain available.
- **on:** additionally expose `scout_files`, after confirming that selected file
  contents and the explicit goal will be sent to TypeSafe.
- **off:** stop scouting and read reuse, clear session cache/retention state, and
  restore normal tool exposure. This does not alter your model or routing policy.

`PI_JEV_CONTEXT=local` is an explicit startup opt-in for local mode;
`PI_JEV_CONTEXT=on` opts into file scouting for non-interactive runs as well.
The global `PI_JEV_MODE=off` still prevents Jev API calls regardless of context
mode. Never enable file scouting globally merely to get duplicate-read reuse.

If you launch Pi with an explicit `--tools` allowlist, include the wrapper names:
`--tools read,read_context,scout_files`. An allowlist containing only `read` can
exclude the extension tools even while the context mode says `local`. Without an
explicit allowlist, the normal `/jev-context` commands handle tool activation.

## Example workflow

First let Pi use ordinary local search to find candidate files. Then ask:

> Use scout_files to rank these candidate files for investigating the refresh bug.
> Read the promising and uncertain files with read_context before drawing conclusions.

The scouting tool accepts an explicit `goal` and a short list of `paths`. It
returns relevance labels and confidence, not the file bodies. All candidates are
accounted for, including uncertain and skipped ones. A negative classification
is not proof that a file cannot matter; normal source reads remain available.

`read_context` accepts ordinary read arguments (`path`, `offset`, `limit`) and
`force: true` to bypass reuse. A repeat of the same requested range of an unchanged
file can return a short reference to its previous full result. Reuse is allowed
only while that full result is still available in the model's context; compaction,
branch/session changes, content removal, changed bytes, or uncertainty require a
fresh read. Concurrent first reads cannot suppress the only full copy.

This reduces duplicated **tool-result content**, not the number of requests the
model makes to invoke the wrapper. Tests, builds, shell commands and required
verification are never skipped or cached by this extension.

## File-send policy

Scouting is deliberately narrow:

- At most 8 explicit candidates; no recursive scans or glob expansion.
- Only tracked, non-ignored text files inside the current Git repository.
- No symlinks, outside-repository paths, secret/config paths, dependency trees,
  binary files, or oversized files.
- At most 16 KiB/file, 64 KiB combined source, and a 1000-character goal.
- Obvious credential literals are screened before transmission. This heuristic
  cannot detect every secret; review the candidates and don't enable scouting
  for repositories whose source must not leave the machine.
- Bounded concurrency, timeouts, cancellation, and the existing Jev daily budget.
- Low-confidence decisions and classifier failures yield uncertainty, never an
  automatic tool block or permission to execute an action.

No raw goals or source bodies are stored in the shared Jev ledger. Relevance
cache entries contain hashes and verdicts, not file contents. TypeSafe receives
source for eligible candidates; this is not an offline or private-only search.

## Accounting and scope

`llm-usage` includes scouting in local classifier activity under purpose
`file-scout`, separate from `task-class`. These are estimated classification
costs, not coding-model quota. Context status reports approximate characters
avoided, not a promise of billed-token or dollar savings.

The extension does not change model selection, `classes.json`, `routes.json`,
`llm-failover.ts`, `/goal`, compaction policy, or browser automation. It never
uses Jev confidence to authorize destructive actions.

## Verified behavior (2026-10-02)

A real Pi session in tmux window `jev-context-demo` used only synthetic tracked
fixtures. The first `read_context` returned **5,753 characters**; the repeated
unchanged read returned a **295-character reference**, avoiding **5,458 characters**
of duplicate tool-result content. This is not a claim about billed-token savings.

After confirming scouting, the actual `scout_files` tool classified `refresh.ts`
as relevant and `theme.css` as unrelated (both confidence 1.00). Two TypeSafe
requests used 2,049 input and 98 output tokens, estimated cost **$0.000086058**.
The tool result includes native Pi usage and `llm-usage` records purpose
`file-scout`. This checks the integration, not classification accuracy in general.

Switching off cleared the retained read cache. Tests also cover force rereads,
changed bytes, lost/redacted/error-marked context, parallel first reads, small
outputs where a marker would be larger, tracked/ignored files, symlink/path races,
credential and binary screening, cancellation, budgets, and partial failures.

The first Grok-backed proof attempt was blocked by Grok's free-tier quota;
verification used the existing Claude transport instead. No provider-routing
policy or account settings were changed.

Implementation: `config/pi/extensions/jev-context.ts`,
`config/pi/lib/jev-context.mjs`, and `config/pi/lib/jev-scout.mjs`.
Installation uses `bin/pi-setup --apply`; credentials and shared budgets use the
existing [Jev setup](jev-pi.md).
