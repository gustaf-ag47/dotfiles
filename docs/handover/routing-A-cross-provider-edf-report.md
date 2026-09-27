# Routing A — cross-provider EDF report

Date: 2026-09-27. Branch: `feat/routing-a-cross-provider`.

## Changes

- `bin/claude-token-proxy`: Anthropic's chosen pool token and Codex's worst usage window expose the same headroom-per-seconds pressure score (unknown reset defaults to seven days). `/_route` now accepts `current=`, adds `preferred`, and applies `PICK_TOLERANCE`; it excludes DeepSeek, Codex on credits, blocked/unavailable candidates, and Codex alternates later than the first Codex route. `first_routable` remains unchanged.
- `config/pi/extensions/llm-failover.ts`: polls the oracle at turn boundaries, follows its preferred provider with an explanatory notification, and uses the same mechanism to return when pressure preference changes. Exhaustion failover and its two-poll recovery stay intact. A manual model selection pins; `/failover pin|unpin` controls the pin and `/failover status` reports it.
- Added Python proxy coverage in `tests/unit/test_proxy_cross_provider.py` and TS proactive/pin/sticky-band cases in `tests/unit/test_llm_failover.mjs`. Adjusted a pre-existing date-sensitive wait test to tolerate its expected UTC date rollover.

## Gates

- `python3 -m unittest tests.unit.test_claude_token_proxy tests.unit.test_proxy_cross_provider tests.unit.test_llm_usage` — **PASS**, 97 tests.
- `node --test --experimental-strip-types tests/unit/test_llm_failover.mjs` — **PASS**, 21 tests.
- `make test-unit` — **PASS**, 111 tests, 1 skipped (existing opt-in provider integration).
- `python3 -m py_compile bin/claude-token-proxy && git diff --check` — **PASS**.

## Live verification

Ran a separate worktree proxy on port 8790 (service on 8788 untouched), then:

```sh
curl -s 'localhost:8790/_route?model=claude-opus-5-5&current=anthropic' | jq .preferred
```

Returned Anthropic as preferred (routable, 93% quota left, reset `2026-10-04T10:00:00+00:00`, pressure `0.0000015376984126984126`). This reflects the live account state; no inference/probe request was made and no quota spent.

## Remaining notes

- Live verification covered the preferred payload but did not exercise a real pi provider switch; the proactive flow is unit tested against the oracle answer. No service restart or real quota-consuming request was made.
- The work deliberately leaves existing exhaustion-triggered switching intact; DeepSeek is never chosen proactively.
