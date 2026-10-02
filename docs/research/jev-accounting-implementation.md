# Jev local classifier activity in `llm-usage` — implementation notes

Status: implemented on branch `feat/jev-accounting`, shadow-only observation
milestone. Scope per handover
(`docs/handover/implement-jev-accounting.md`): own
`scripts/llm_usage.py` + `tests/unit/test_jev_usage.py` + this doc only. No
proxy, routing/classes config, or helper changes. No network calls, no
credential reads, no browser use.

## What this is, and what it is explicitly not

- This is **local observed activity**: counts/latencies/estimated cost read
  from a local JSONL ledger that some other component (the "helper", owned by
  a sibling branch) is expected to append to.
- It is **not** a remote account/subscription balance. Jev has no known
  quota endpoint in this stack; `jev` is intentionally **not** added to
  `ADAPTERS` or `REPORT_SOURCES` (the provider-shaped tables used for
  `/_usage`-style quota polling), so it can never be mistaken for a routable
  provider or a known-balance account.
- `applied` is always expected to read `false` at this milestone (Pi's
  routing has not been wired to act on Jev's verdicts yet). The code does not
  hardcode that assumption away: it counts and **surfaces** any
  `applied: true` events it finds, both in JSON (`applied_count`) and text
  (an explicit "anomaly" line), rather than silently treating 0 as a given.

## Parent review pass (before commit)

After the first implementation pass, parent review flagged five issues, all
addressed in the same uncommitted change set (see `jev_validate_event`,
`jev_aggregate`, `jev_classifier_lines` in `scripts/llm_usage.py`):

1. `status`/`source`/`cost_source` membership tests against a plain `in
   {set}` can raise `TypeError` for an unhashable value (a list/dict in a
   malformed line) -> switched to `jev_enum()`, which type-checks before
   testing membership.
2. `class` (and `model`/`rubric_version`) were only length-bounded, not
   content-whitelisted -> added `jev_safe_token()`/`JEV_SAFE_TOKEN_RE` so
   control characters, whitespace, and secret-shaped text are dropped to
   `null` instead of ever being retained or rendered.
3. Numeric fields accepted `NaN`/`Infinity`/negative values -> added
   `jev_finite()`/`jev_nonneg_finite()`/`jev_nonneg_int()` so a corrupt row
   can't poison a cost sum or a latency min/max/avg, and token counts must
   be real non-negative integers.
4. A `cache_hit` with `cost_source: "cache"` and a known `0` cost was being
   counted as *unknown* cost (because only `published-rate` summed) ->
   `JEV_KNOWN_COST_SOURCES = {'published-rate', 'cache'}` now treats a
   known-zero cache cost as known, not unknown.
5. `calls` conflated "observations we read" with "calls that reached a
   classifier" -> added `network_calls` (status `ok`/`abstained`/`error`
   only; `cache_hit`/`skipped` are observations, not network calls) as a
   distinct field, surfaced in both JSON and text.

A sixth, separate finding (4dp cost formatting rounding real activity to
`$0.0000`) is addressed under "Cost is formatted at 6 decimal places" below.
Regression tests for all six live in `HardeningTests` in
`tests/unit/test_jev_usage.py`. The parent will live-verify default
`llm-usage` output after merge.

## Sibling contract status at implementation time

At the time this was implemented, `feat/jev-helper` and `research/jev-pi-routing`
had **no commits beyond `master`** — the sibling's helper/ledger-writer code
had not landed yet. There is therefore no live ledger to validate against;
the schema below is implemented exactly as specified in the handover brief
(the "proposed ledger" contract), with defensive validation so that any
deviation in a real helper's output degrades to "skip this line, count it,
move on" rather than crashing or fabricating data.

**Action for the parent / sibling reconciliation:** when `feat/jev-helper`
lands, diff its actual ledger writer against the schema below before merging
both branches. If field names, the status vocabulary, or `cost_source`
values differ, `jev_validate_event()` in `scripts/llm_usage.py` is the single
place to update — invalid/unknown-shaped lines are already counted and
skipped rather than rendered, so a contract mismatch fails safe (activity
shows as 0 / "no activity", not wrong numbers) until this file's validator is
updated to match.

## Ledger contract implemented

Path: `${XDG_STATE_HOME:-$HOME/.local/state}/jev/events.jsonl`
(`jev_ledger_path()`). Directory/file permissions (`0700`/`0600`) are the
writer's responsibility (the helper, out of scope here); this reader never
widens permissions and never writes to the ledger itself.

One JSON object per line, schema `jev-event.v1`:

```json
{
  "schema": "jev-event.v1",
  "timestamp": "2026-10-02T09:12:03Z",
  "source": "delegate",
  "status": "ok",
  "class": "mechanical",
  "confidence": 0.88,
  "model": "jev-1.13.0",
  "rubric_version": "r3",
  "latency_ms": 145,
  "input_tokens": 612,
  "output_tokens": 0,
  "estimated_cost_usd": 0.0000257,
  "cost_source": "published-rate",
  "applied": false
}
```

Validated vocabulary (`jev_validate_event` in `scripts/llm_usage.py`):
- `status`: one of `ok | abstained | error | skipped | cache_hit`, checked
  via `jev_enum()`, not a bare `value in {set}` — a list/dict `status` in a
  malformed line is unhashable and would raise `TypeError` against a plain
  set membership test; `jev_enum()` checks `isinstance(value, str)` first, so
  an unhashable field just fails validation instead of crashing the reader.
  `source` and `cost_source` use the same guard.
- `source`: `delegate | pi` (else stored as `null`, event still counted).
- `cost_source`: `published-rate | unknown | cache`. A numeric
  `estimated_cost_usd` is only summed into the cost total when `cost_source`
  is `published-rate` **or** `cache` (`JEV_KNOWN_COST_SOURCES`) — a cache hit
  recording a known cost of `0` is a known zero, not an unknown cost.
  `cost_source: unknown`, a missing/non-numeric amount, or a non-finite/
  negative amount all increment `cost_unknown_calls` instead of being added
  as `0`.
- `input_tokens`/`output_tokens`: both must be present, a real `int` (not
  `bool`), and **non-negative** (`jev_nonneg_int()`) for a row to count
  toward the token totals; otherwise the row increments
  `tokens_unknown_calls` and contributes `0` to the sum — unknown or
  negative token counts never silently become zero-cost/zero-usage success
  or a nonsensical negative total.
- `confidence`, `latency_ms`, `estimated_cost_usd`: numeric, `NaN`/`±Inf`
  rejected (`jev_finite()`); `latency_ms` and `estimated_cost_usd` are
  additionally required to be **non-negative** (`jev_nonneg_finite()`) or
  they are dropped to `null` and (for cost) counted as unknown rather than
  letting a corrupt row poison a sum or a latency min/max/avg.
- `class`, `model`, `rubric_version`: **whitelisted**, not just
  length-bounded (`jev_safe_token()` / `JEV_SAFE_TOKEN_RE`: must start with
  an alphanumeric and consist only of `[A-Za-z0-9_.:-]`, ≤128 chars).
  Anything with whitespace, control characters (e.g. ANSI escapes), or
  secret-shaped punctuation is dropped to `null` instead of being retained
  or rendered — this is the only free-text-ish field ever derived from an
  untrusted ledger line, and it fails closed rather than merely truncating.
- `applied`: must be a real `bool` or it is stored as `null` (not coerced to
  `False`).

Any line that is not valid JSON, or is valid JSON that fails the above (wrong
`schema`, unknown/unhashable `status`, unparseable/naive `timestamp`), is
**skipped and counted** — never rendered. Counts are split into
`parse_errors` (invalid JSON) and `schema_errors` (valid JSON, invalid/
unexpected shape), and summed as `malformed_lines_skipped`.

### Bounded, safe reads

- At most 5 MiB (`JEV_MAX_LEDGER_BYTES`) is read from the ledger per call;
  if the file is larger, the excess is truncated and `truncated_bytes: true`
  is reported (not silently dropped without a flag).
- At most 50,000 parsed events (`JEV_MAX_EVENTS`) are retained per call; a
  larger ledger sets `truncated_events: true` and stops parsing further
  lines.
- The **trailing line** of whatever was read is always dropped before
  parsing (not treated as corrupt). This covers two cases uniformly: a
  concurrent writer mid-`append()` leaving a half-written final line, and our
  own byte cap cutting a line in half. Either way the number reported is a
  safe undercount for the newest event, never a parse error or garbage in
  the output.
- `PermissionError`/`OSError` on open → `ledger_status: "unreadable"`, empty
  event list, no exception raised.
- Missing file (the expected default — no helper installed yet, or no
  activity yet) → `ledger_status: "missing"`, empty event list, rendered as a
  single quiet line, not as an error.
- No ledger I/O happens during JSON serialization/validation — only a single
  bounded `read()` call, so there is no unbounded-time risk from a pathological
  file (e.g. a FIFO or an infinite device) beyond that one bounded read.

## Report shape

### JSON (`llm_usage.py --json`)

A new top-level key, **separate from `providers`**:

```json
{
  "schema": "llm-usage.v1",
  "providers": { "...": "unchanged" },
  "classifier_activity": {
    "schema": "jev-classifier-activity.v1",
    "note": "Local observation only: ...",
    "ledger_path": "/home/user/.local/state/jev/events.jsonl",
    "ledger_status": "ok",
    "malformed_lines_skipped": 1,
    "parse_errors": 1,
    "schema_errors": 0,
    "truncated_bytes": false,
    "truncated_events": false,
    "today_utc": "2026-10-02",
    "today": {
      "calls": 4,
      "by_status": {"ok": 1, "cache_hit": 1, "abstained": 1, "error": 1},
      "by_class": {"mechanical": 2},
      "ok": 1, "abstained": 1, "errors": 1, "skipped": 0, "cache_hits": 1,
      "input_tokens": 1200, "output_tokens": 0, "tokens_unknown_calls": 1,
      "estimated_cost_usd": 5e-05, "cost_unknown_calls": 2,
      "latency_ms_summary": {"count": 3, "avg": 105.0, "min": 2, "max": 168},
      "applied_count": 0
    },
    "retained_total": { "...": "same shape, over every row the bounded read saw" }
  }
}
```

(Full sample captured from fixture data, not real user data, during
implementation — see "CLI sample" below for the exact command and output.)

`retained_total` is clearly a separate, explicitly-labeled field from
`today` — it is whatever the bounded ledger read currently retains (subject
to the 5 MiB / 50,000-event caps above), not a promise of unlimited history.

`calls` vs `network_calls`: `calls` is every retained *observation* in the
group regardless of status. `network_calls` is the subset whose `status` is
`ok | abstained | error` — i.e. actually reached a classifier. `cache_hit`
and `skipped` rows are observations but **not** network calls, and are
deliberately excluded from `network_calls` so a reader can't mistake "we
saw N events" for "we made N classifier requests".

### Text (`llm_usage.py`, default)

A new section appended after the existing provider blocks:

```
Jev classifier activity (observation only)
  today UTC (2026-10-02): observations=4 (network_calls=3) ok=1 abstained=1 error=1 skipped=0 cache_hit=1
  tokens in=1200 out=0 (1 unknown)  estimated cost=$0.000050 est. (+1 unknown-cost call(s))
  latency ms avg=105.0 min=2 max=168 (n=3)
  observed suggestions: mechanical=2
  skipped 1 malformed ledger line(s)
```

Cost is formatted at 6 decimal places (not 4): Jev's per-call cost is a few
millionths of a dollar at the published $0.042/M-input-token rate, and at
4dp a handful of real calls still visibly rounds to `$0.0000` — which reads
as "no cost", the opposite of what bounded observation is for. The label is
always `estimated cost=... est.`, never "cost" alone or "bill": this is a
locally computed estimate from a published rate, not an actual invoice.

When there is no activity today and the ledger is missing, the section is a
single quiet line:

```
Jev classifier activity (observation only)
  no local activity observed (ledger not found)
```

### Waybar (`--waybar`)

Untouched: `waybar_payload()` only reads `report['providers']`;
`classifier_activity` never appears in the Waybar JSON (covered by
`test_waybar_payload_ignores_classifier_activity`). The existing percent/
`class`/`tooltip` Waybar contract is unaffected.

## Cache interaction

The existing 60-second provider-report cache (`cache_dir / <hash>.json`
under `XDG_CACHE_HOME/llm-usage/`) is **untouched in shape and behavior**:
cache keying, locking (`fcntl.flock`), temp-file-then-`os.replace`, and file
mode (`0600`) are all unchanged.

`classifier_activity` is computed **after** the cache block resolves
`report` (whether from a fresh `collect()` or a cache hit) and is attached to
`report` every single invocation, so the local ledger is always read fresh
even when the provider-report cache is reused. This is covered by
`CacheIntegrationTests.test_providers_report_unaffected_cache_refresh_still_rereads_ledger`,
which calls `main()` twice with an identical cache identity and asserts the
second call's `classifier_activity.retained_total.calls` reflects a ledger
line written *between* the two calls, while `providers` stays cached/
unchanged.

## CLI sample (fixture data, not real user data)

```bash
HOME=/tmp/jev-demo/home \
XDG_CACHE_HOME=/tmp/jev-demo/cache \
XDG_STATE_HOME=/tmp/jev-demo/state \
PI_CODING_AGENT_DIR=/tmp/jev-demo/agent \
python3 scripts/llm_usage.py --provider deepseek --json
```

with `/tmp/jev-demo/state/jev/events.jsonl` containing 5 valid `jev-event.v1`
lines (1 from 2026-09-30, 4 from 2026-10-02: one `cache_hit` with
`cost_source: "cache"` and a known zero cost, one `abstained`, one `error`
with all-null numeric fields and `cost_source: "unknown"`) plus one line of
garbage (`not-json-at-all`), produces the JSON `classifier_activity` block
and text section shown above. `--provider deepseek` was used only to keep
the sample's `providers` section short (no DeepSeek credential configured in
the sandbox); `classifier_activity` is independent of `--provider` filtering.

## Tests

`tests/unit/test_jev_usage.py`, 21 tests, covering:
- ledger path resolution (`XDG_STATE_HOME` set / default under `$HOME`)
- missing ledger (quiet, clean, `ledger_status: "missing"`)
- empty ledger file
- unreadable ledger (chmod 000; skipped automatically if running as a user
  that bypasses file permissions, e.g. root)
- corrupt JSON lines + wrong-schema lines + invalid-status lines +
  unparseable-timestamp lines, all counted and never echoed into output
- a truncated/partial final line (simulated concurrent writer) dropped
  without being counted as corrupt
- unknown token counts and unknown cost sources never silently summed as `0`
  cost/usage — they increment dedicated "unknown" counters instead
- `applied: true` is surfaced (not hidden) in both JSON and text
- unhashable `status`/`source`/`cost_source` values (a list/dict in place of
  a string) do not raise `TypeError` and fail validation cleanly
- `NaN`/`Infinity`/negative `latency_ms`, `estimated_cost_usd`, and negative
  token counts are rejected and never poison a sum or a min/max/avg
- a secret-shaped or control-character `class` label is dropped to `null`
  and never appears in JSON or text output; a safe label still passes through
- a `cache_hit` event with `cost_source: "cache"` and a known `0` cost counts
  as a known cost, not an unknown one
- `calls` (observation count) vs `network_calls` (only `ok`/`abstained`/
  `error`) are asserted as distinct numbers in both JSON and text
- UTC day rollover, including a non-UTC-offset timestamp that crosses into
  the next UTC day
- cache-refresh integration: ledger is read fresh even when the
  provider-report cache is reused; ledger/dir permissions on a fixture file
  are not widened
- text rendering includes the Jev section without disturbing existing
  provider rendering; Waybar payload ignores `classifier_activity` entirely
- `jev` is not present in `ADAPTERS` or `REPORT_SOURCES`

Run:

```bash
python3 -m unittest tests.unit.test_jev_usage tests.unit.test_llm_usage -v
make test-unit   # full suite, 260 tests at implementation time, all green
```

## Explicitly out of scope / not done here

- No helper, no route/classes config, no extension code (sibling's scope).
- No live API calls, no credential reads, no browser automation.
- No claim of a known Jev account balance/subscription quota — `jev` is
  absent from `ADAPTERS`/`REPORT_SOURCES` by design.
- No ledger-writing code — this is a read-only consumer of whatever the
  helper eventually writes.
