# Brief: distinguish quota-429 from burst-429 in claude-token-proxy

## Context

You are in a dedicated git worktree on branch `feat/proxy-429-pacing`
(base: master @ `4c800c9`, which added pressure-based token selection).
Read first:
- `bin/claude-token-proxy` (single-file stdlib Python proxy; the `_proxy()`
  request loop and `FAILOVER_STATUSES` are your target)
- `docs/research/claude-token-rotation-oss.md` — Summary idea #3 and the
  teamclaude details section: every serious OSS peer treats a per-minute
  burst 429 differently from a spent weekly/session bucket. Rotating on a
  burst just moves the burst to another account and throws away the first
  account's warm prompt cache.

Today our proxy treats EVERY 429 as a failover trigger (cooldown +
same-request retry on the next token).

## Job

1. Add a pure helper `classify_429(headers) -> str` returning `"quota"` when
   the response marks a spent bucket (`anthropic-ratelimit-unified-status:
   rejected`, or any `anthropic-ratelimit-unified-*-status: rejected` /
   representative-claim evidence — study the header catalogue in
   `docs/research/anthropic-ratelimit-buckets.md` §3), else `"burst"`.
2. In `_proxy()`: on a quota-429, keep EXACTLY today's behavior (cooldown from
   Retry-After + failover to next token). On a burst-429 with
   `Retry-After <= CC_PROXY_BURST_WAIT_MAX` (new env knob, default 15s):
   sleep that long and retry the SAME token (do not add it to `tried`), at
   most ONCE per request; if it 429s again or Retry-After is larger than the
   cap, fall back to today's cooldown+failover path.
3. Make sure the sleep happens OUTSIDE the `LOCK` and that `probe()`'s 429
   handling stays unchanged.
4. Update the module docstring env-knob paragraph.
5. Unit tests in `tests/unit/test_claude_token_proxy.py` (new TestCase class):
   classification for rejected/plain/absent headers; the pacing decision
   (helper-level — keep `_proxy` thin by extracting the decision into a pure
   function like `burst_pause_seconds(headers) -> float | None` so it is
   testable without sockets); Retry-After over the cap → no pacing.
6. Run the FULL suite from the worktree root:
   `python3 -m unittest tests.unit.test_claude_token_proxy -v` — all green,
   including the 11 existing tests.
7. Sanity: `python3 -c "import ast; ast.parse(open('bin/claude-token-proxy').read())"`.
8. Commit on this branch (conventional commit, subject <= 50 chars, e.g.
   `feat(claude-token-proxy): pace burst 429s`). Do NOT merge to master, do
   NOT push. `GIT_EDITOR=true` for any git command that might open an editor.
9. Write `docs/handover/proxy-429-pacing-report.md` in the WORKTREE (commit it
   too): what changed, test evidence, and any design doubts.

## Scope fence / constraints

- Files you own: `bin/claude-token-proxy`,
  `tests/unit/test_claude_token_proxy.py`, your report. Nothing else.
- Do NOT restart or touch the `claude-token-proxy` systemd service — a sibling
  agent (`activate-and-verify`) owns the live service and is restarting it.
  Your worktree file is NOT the one the service symlinks to; keep it that way.
- Do NOT edit `docs/research/anthropic-ratelimit-buckets.md` (sibling appends
  to it in the main checkout).
- Never read `~/cctoken` or print credentials. No live API calls needed for
  this task — it is entirely offline code + tests.
- Pre-commit hooks run: no trailing whitespace, subject <= 50 chars,
  conventional format.

## Cost guidance

Offline task, budget accordingly (~$2–4). If a design question blocks you
(e.g. ambiguity about which header marks a quota rejection), pick the
conservative reading (`unified-status: rejected` only), note the doubt in the
report, and proceed — do not burn budget researching further.
