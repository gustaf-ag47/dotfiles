# Routing E — no-starvation report

Date: 2026-09-28. Branch: `feat/routing-e-no-starvation`.

## Implemented

- `bin/llm-wait`: stdlib-only recursive-descent predicate evaluator and polling of `/_usage` + `/_route`; supports bounded waits, 3-consecutive-error exit, reset hint, and exits 0/2/3. Fake HTTP server tests cover success, timeout, and unreachable.
- Delegate launcher waits for provider routability before the probe and has a bounded Codex-to-Anthropic Sonnet fallback. Same hunk was applied to `~/.pi/agent/skills/delegate/scripts/delegate.sh` (that live copy is outside git). Delegate and ralph-loop skills document wait behavior.
- Proxy persists DeepSeek monthly balance baseline/minimum, handles top-ups and month rollover, gates route/fallback at `CC_PROXY_DEEPSEEK_MONTHLY_CAP` (default $20), and exposes cap/spend to `llm-usage`. Synthetic tests cover spend, top-up, month rollover, candidate/fallback refusal.
- Proxy records a starvation event/count when a 503 is issued despite `route_payload()` reporting a routable provider; persisted under `_routing_starved` and exposed in usage output. A handler-level 503 test forces the OAuth token down while Codex is routable and verifies the count increments.

## Tests and gates

- `python3 -m unittest tests.unit.test_llm_wait tests.unit.test_proxy_no_starvation tests.unit.test_claude_token_proxy tests.unit.test_llm_usage` — **PASS**, 111 tests.
- `make test-unit` — **PASS**, 139 tests, 1 existing skip.
- `bash -n config/pi/skills/delegate/scripts/delegate.sh` and `bash -n ~/.pi/agent/skills/delegate/scripts/delegate.sh` — **PASS**.
- `shellcheck config/pi/skills/delegate/scripts/delegate.sh` — **PASS**.
- `python3 -m py_compile bin/claude-token-proxy scripts/llm_usage.py` and `git diff --check` — **PASS**.

## Isolated live wait check

The first attempt encountered an existing listener on 8790 (`OSError: [Errno 98] Address already in use`); after that process exited, I successfully started the required separate instance on **8790**, with `CCTOKEN_FILE=$HOME/cctoken` and separate `XDG_CACHE_HOME=/mnt/my_encrypted_nvme/sync/tmp/pi-scratch/routing-e/cache-8790`:

```text
llm-wait: waiting for anthropic.routable; earliest known reset: unknown
llm-wait: timed out
EXIT=2
llm-wait: predicate satisfied for claude-sonnet-5
```

The three fingerprints (`ccb67338fbdb`, `82a293204226`, `a5de118c98c0`) were written to that isolated instance's `force_cooldown`, then the file was removed. The temporary 8790 process was stopped. No 8788 service/cache was touched. Actual output:

```text
llm-wait: waiting for anthropic.routable; earliest known reset: unknown
llm-wait: timed out
WAIT_EXIT=2
llm-wait: predicate satisfied for claude-sonnet-5
```

## Commits

- `f42caf4` feat: add llm quota wait command
- `69930d0` feat: wait for provider before delegate probe
- `8d9c890` feat: cap DeepSeek spend and count starvation
- `9d843ab` fix: fall back after Codex wait timeout
