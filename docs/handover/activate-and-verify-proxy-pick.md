# Brief: activate + live-verify the new proxy pick, settle the Fable-debit question

## Context

Commit `4c800c9` (already on master, this checkout) changed
`bin/claude-token-proxy` from lowest-7d-utilization token selection to
pressure-based, model-aware selection (see the commit message and
`docs/research/anthropic-ratelimit-buckets.md` +
`docs/research/claude-token-rotation-oss.md`). Unit tests pass
(`python3 -m unittest tests.unit.test_claude_token_proxy -v` — run it to
confirm before touching the service).

The user systemd service `claude-token-proxy` (port 8788) is still running the
OLD code. `~/.local/bin/claude-token-proxy` symlinks to this repo's file, so a
restart activates the new code. **Your own pi session and sibling agents route
through this proxy** — a restart briefly interrupts any in-flight stream. That
is accepted; do the restart exactly ONCE, early, as a single atomic command.

## Job

1. Run the unit suite; abort and report if it fails.
2. Restart + wait until serving, in ONE bash invocation:
   `systemctl --user restart claude-token-proxy; for i in $(seq 60); do curl -fsS http://127.0.0.1:8788/_status >/dev/null 2>&1 && break; sleep 1; done; curl -fsS http://127.0.0.1:8788/_status | jq '{usable,available,total}'`
   Expect 3 tokens loaded. Check `journalctl --user -u claude-token-proxy -n 30`
   for the startup log (it now mentions pressure knobs in behavior; log lines
   include `u7_oi=`).
3. Verify routing. Send one cheap probe per bucket THROUGH the proxy and read
   which token served it from journalctl (labels: `antropic@gustafsilver.se`
   fp a5de118c98c0 should serve fable; `gs@gustafsilver.se` fp 82a293204226
   should serve sonnet, per the pressure replay in the parent session —
   re-derive from live `/_status` if numbers moved):
   ```bash
   curl -sS -D /tmp/hdr-fable.txt http://127.0.0.1:8788/v1/messages \
     -H 'content-type: application/json' -H 'anthropic-version: 2023-06-01' \
     -H 'anthropic-beta: claude-code-20250219,oauth-2025-04-20' \
     -H 'user-agent: claude-cli/2.1.75' -H 'x-app: cli' \
     -H 'anthropic-dangerous-direct-browser-access: true' \
     -d '{"model":"claude-fable-5","max_tokens":1,"system":[{"type":"text","text":"You are Claude Code, Anthropic'\''s official CLI for Claude."}],"messages":[{"role":"user","content":"."}]}' | head -c 300
   ```
   and the same with `claude-sonnet-5` into `/tmp/hdr-sonnet.txt`.
4. Settle the open research question (job 2 of
   `docs/research/anthropic-ratelimit-buckets.md`): does a Fable request debit
   ONLY `7d_oi`, or also base `7d`/`5h`? Method: snapshot `/_status`
   utilizations for the serving token immediately before and after the fable
   probe, AND inspect the raw `anthropic-ratelimit-unified-*` headers captured
   in `/tmp/hdr-fable.txt` (the proxy forwards upstream headers). Compare with
   the sonnet probe: sonnet should move `7d`/`5h` but not `7d_oi`. One probe
   per model is enough; max two extra probes if a result is ambiguous.
5. Append a `## Empirical experiment (2026-09-08)` section to
   `docs/research/anthropic-ratelimit-buckets.md` with the header values
   (utilizations/resets only — never token values) and your conclusion.
6. Verify `claude-usage` prints a sane report and `waybar-claude-usage` emits
   valid JSON (`waybar-claude-usage | jq .class`).
7. Write `docs/handover/activate-and-verify-proxy-pick-report.md`: what was
   verified, the Fable-debit conclusion with evidence, any anomalies
   (e.g. routing not matching prediction — report, don't "fix").

## Scope fence / constraints

- You may edit ONLY: `docs/research/anthropic-ratelimit-buckets.md` (append)
  and your report file. Do NOT touch `bin/`, `tests/`, or the systemd unit.
- A sibling agent works on a 429-pacing change in a separate worktree/branch
  (`feat/proxy-429-pacing`) — ignore it, do not merge or review it.
- Do NOT commit; the parent commits. Do NOT push.
- Never print, log, or copy token values; fingerprints and labels only. Do not
  read `~/cctoken`.
- Restart the service exactly once. If the service fails to come back within
  60s: `systemctl --user status claude-token-proxy` + last 50 journal lines
  into your report, then STOP (rollback is
  `CC_PROXY_PICK=headroom` via drop-in or `git revert` — parent's call).

## Cost guidance

This is a ~$1 task: a handful of max_tokens=1 probes and log reading. If
blocked, write the report with what you have and stop.
