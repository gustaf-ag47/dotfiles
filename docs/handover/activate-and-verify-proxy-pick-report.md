# Report: activate + live-verify the new proxy pick

Ran 2026-09-09 as delegated sub-agent (run id `20260909T093814Z-907141`,
parent tmux window `%775`).

## What was verified

1. **Unit tests**: `python3 -m unittest tests.unit.test_claude_token_proxy -v`
   — all 11 tests pass, no changes needed. Ran before touching the service.

2. **Service restart (exactly once)**: single atomic command per the brief —
   `systemctl --user restart claude-token-proxy` followed by a poll loop on
   `/_status`. Came back within ~1s. Post-restart `/_status`:
   `{"usable": 3, "available": 2, "total": 3}` — 3 tokens loaded, as expected.
   Journal confirms the new pressure-mode code is live:
   `listening on http://127.0.0.1:8788 threshold=0.98 watch=30.0s ...` and
   subsequent request logs include `u7_oi=` (new field, absent from the old
   code's log format).

3. **Routing / Fable-debit probes**: sent one `claude-fable-5` and one
   `claude-sonnet-5` probe (`max_tokens: 1`) through the proxy. Both were
   served by token `82a293204226` (`gs@gustafsilver.se`) — see anomaly note
   below. Full header/utilization evidence and conclusion are appended to
   `docs/research/anthropic-ratelimit-buckets.md` under
   `## Empirical experiment (2026-09-08)`.

   **Conclusion on the open research question**: a Fable-5 request debits
   **only** the dedicated `7d_oi` bucket. Base `7d`/`5h` utilizations were
   byte-identical immediately before and after the Fable probe (and across
   several other real requests on the same token in the same window), while
   `7d_oi` moved (first observed reading, `0.07`, non-zero from prior real
   traffic). The follow-up Sonnet probe on the same token confirms
   `7d_oi-*` headers are **absent entirely** from non-Fable responses — it's
   not a shared bucket that other models report-but-leave-at-zero, it's
   Fable-specific. This matches and settles the hedge already present in the
   doc's Summary (item 2).

4. **`claude-usage`**: prints a sane 3-account report (weekly/5h percentages,
   Fable/overage weekly line for two accounts, quota-scope-unavailable notes,
   one account showing a retry-cooldown line for `antropic@gustafsilver.se`).

5. **`waybar-claude-usage`**: emits valid JSON;
   `waybar-claude-usage | jq .class` → `"critical"` (driven by the
   `antropic@gustafsilver.se` token reading 100% weekly / in cooldown — see
   anomaly below).

## Anomaly: routing did not match the brief's prediction

The brief predicted `antropic@gustafsilver.se` (fp `a5de118c98c0`) would
serve the Fable probe and `gs@gustafsilver.se` (fp `82a293204226`) would
serve the Sonnet probe. In practice **both** probes were served by
`82a293204226`. Root cause, from `/_status` immediately post-restart:

- `a5de118c98c0` (`antropic@gustafsilver.se`): `u7=1.0`, `last_status: 429`,
  `unified_status: "rejected"`, `cooldown_remaining: 346876.2` (until
  `2026-09-13T09:59:59Z`, i.e. its `7d` reset). This token was maxed out and
  in a multi-day cooldown at probe time — not eligible for selection at all
  under the new pressure logic (or the old one).
- `82a293204226` had by far the best headroom of the two eligible tokens
  (`u7=0.03` vs. `ccb67338fbdb`'s `u7=0.92`), so the picker correctly routed
  both probes there.

This is **not a bug in the new pick logic** — it's the real-world token state
having moved since the parent session's pressure replay was done (the
`antropic@gustafsilver.se` token crossed into cooldown between then and this
run). Flagging per the brief's "report, don't fix" instruction; no code was
touched.

## Files changed

- `docs/research/anthropic-ratelimit-buckets.md` — appended
  `## Empirical experiment (2026-09-08)` section (header/utilization data,
  no token values).
- `docs/handover/activate-and-verify-proxy-pick-report.md` — this file.

No other files touched. Did not commit (parent's job). Did not push.

## Status: DONE

All steps in the brief completed. No blockers. Service is live on the new
pressure-based code and confirmed healthy.
