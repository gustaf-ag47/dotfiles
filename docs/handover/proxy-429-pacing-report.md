# Report: burst-429 pacing in `claude-token-proxy`

Branch `feat/proxy-429-pacing` (base `907f9bb`). Offline change; the live
systemd service was not touched.

## What changed

`bin/claude-token-proxy`

- **`classify_429(headers) -> "quota" | "burst"`** (pure). Returns `"quota"` when
  the response marks a spent bucket:
  - any header matching `anthropic-ratelimit-unified-(<claim>-)?status` whose
    value is `rejected` — covers the account-level
    `anthropic-ratelimit-unified-status` and the per-bucket forms
    (`-7d-status`, `-7d_oi-status`, `-overage-status`, …);
  - otherwise, if `anthropic-ratelimit-unified-representative-claim` names a
    known bucket and that bucket's `-utilization` is `>= 1.0`
    (claim→abbreviation map `CLAIM_ABBREV`, from
    `docs/research/anthropic-ratelimit-buckets.md` §3).

  Everything else — including a 429 with no unified headers at all — is
  `"burst"`.
- **`burst_pause_seconds(headers, cap=None) -> float | None`** (pure). Returns
  the number of seconds to wait before retrying the *same* token, or `None`
  meaning "take the historical cooldown + failover path". `None` when: the 429
  is a quota-429, there is no explicit `Retry-After`, `Retry-After` exceeds the
  cap, or the cap is `<= 0` (pacing disabled). Default cap is the new env knob
  `CC_PROXY_BURST_WAIT_MAX` (module constant `BURST_WAIT_MAX`, default `15`).
- **`header_map()`** — lower-cased snapshot of either an `http.client`
  `HTTPMessage` or a plain dict, so both helpers are testable without sockets
  and are case-insensitive.
- **`_proxy()`** — on a 429 it now asks `burst_pause_seconds()` first:
  - `None` → **exactly today's behaviour**: `cooldown_until = now +
    Retry-After`, add the fp to `tried`, fail over to the next token.
  - a number → the token is *not* cooled down and *not* added to `tried`; the
    response body is drained, the connection closed, `time.sleep(pause)` runs
    **outside `LOCK`**, and the loop continues. A `paced` set caps this at one
    pause per token per request; a second 429 from the same token falls through
    to the cooldown+failover path.
  - The attempt budget grew from `valid_count + 1` to
    `valid_count + 1 + valid_count` so a pause cannot eat a failover attempt.
  - Log line gains a `[burst, pausing Ns]` marker instead of `[failover]`.
- Module docstring: new paragraph documenting `CC_PROXY_BURST_WAIT_MAX` and the
  quota-vs-burst split.

`probe()` is unchanged — it still cools down on any 429, as required.

## Test evidence

New `Burst429Tests` (13 cases) in `tests/unit/test_claude_token_proxy.py`:
classification of account-level `rejected`, per-bucket `rejected` (3 subtests),
representative-claim at full utilization, `allowed_warning`, absent headers,
mixed header case; pacing within the cap, over the cap, quota-429, missing
`Retry-After`, `cap=0`, the `BURST_WAIT_MAX` default, and an
`email.message.Message` container.

```
$ python3 -c "import ast; ast.parse(open('bin/claude-token-proxy').read())"
$ python3 -m unittest tests.unit.test_claude_token_proxy -v
...
Ran 24 tests in 0.002s

OK
```

24 = 11 pre-existing + 13 new; nothing was modified in the existing classes.

## Design doubts

1. **"Same token" is achieved indirectly.** The paced retry does not hold a
   reference to the token across the loop; it just leaves it out of `tried` and
   out of cooldown and calls `pick()` again. `pick()` is deterministic over
   unchanged state and `LAST_PICK` now points at that token, so in practice it
   returns the same token (and keeps its prompt cache). A concurrent token-file
   reload or a `force_cooldown` write during the sleep could divert it — which
   is a *correct* outcome, but it means the guarantee is "usually the same
   token", not "always". Making it literal would mean bypassing `pick()`, which
   felt worse.
2. **No `Retry-After` → no pacing.** Conservative reading: without an explicit
   hint we do not invent a sleep duration, we rotate as before. If upstream
   turns out to omit `Retry-After` on burst 429s, this feature will look inert
   and the default would need revisiting.
3. **Representative-claim evidence is a soft signal.** The brief allowed the
   strict reading (`unified-status: rejected` only). I included the
   `representative-claim` + `utilization >= 1.0` rule as well because a spent
   bucket misclassified as a burst costs a wasted 15s sleep on every request;
   the reverse (burst misread as quota) is only today's behaviour. If that
   proves noisy, deleting the `CLAIM_ABBREV` branch reduces it to the strict
   reading with no other change.
4. **Serial pauses across tokens.** Worst case a request could pause once per
   token (`valid_count` × up to 15s) before failing. In practice a burst 429 on
   token A followed by a burst 429 on token B is a strong signal of a
   client-side send-rate problem; the extra latency is bounded and visible in
   the log. Not capped globally — a possible follow-up.
5. **Not exercised against live upstream.** Entirely offline per the brief; the
   `_proxy()` branch itself has no socket-level test (only the extracted pure
   helpers), so first real evidence will be a `[burst, pausing Ns]` line in the
   service journal.
