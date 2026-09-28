# Routing G — 5h capacity, boundary moves, burst ramp

Implemented G1–G3 on `feat/routing-g-no-5h-stalls`.

- `llm-usage --capacity [--horizon HOURS] [--json]` reads fresh local `/_usage`; uses median positive observed 5h burn across accounts divided by the number of affinity sessions active in the last 15 minutes (minimum denominator 1). Each account contributes `floor(5h headroom / (per-session burn × horizon))`. Unknown slopes or headroom contribute zero, **not** unlimited capacity. This is planning advice, not a guarantee: the proxy's forecast slope may span more than the past hour, and total active sessions (not per-account counts) are available. The two `delegate.sh` copies warn, never block, if the estimate is zero. `routing.active_sessions` counts distinct nonglobal affinity session keys touched within 15 minutes.
- Existing session affinity stays on its account mid-conversation; at `messages` length ≤ 2 or `x-cc-proxy-boundary: 1`, a >tolerance gap in 5h headroom/seconds-until-reset triggers a spread choice in the 5h band and a `reason=5h` route event. `rank_pool(..., messages_len=...)` previews the same selection. Global/no-session selection retains legacy pressure behavior.
- `append_route()` arms a token's post-move concurrency ramp (default two upstream calls for 60 seconds); `ramp_upstream()` waits for a semaphore outside `LOCK`, with a five-second maximum and a fail-open path. In-flight counts decrement in `finally`, including on upstream exceptions. Configurable via `CC_PROXY_RAMP_CONCURRENCY` and `CC_PROXY_RAMP_SECONDS`.

## Gates

- `python3 -m unittest tests.unit.test_proxy_5h tests.unit.test_claude_token_proxy tests.unit.test_llm_usage`: **108 tests OK**.
- `make test-unit`: **149 tests OK (1 skipped)**.
- `shellcheck config/pi/skills/delegate/scripts/delegate.sh /home/gud1/.pi/agent/skills/delegate/scripts/delegate.sh`: **pass**; `git diff --check`: **pass**.

## Live isolated instance

Launched port 8793 with `CCTOKEN_FILE=$HOME/cctoken`, `CC_PROXY_SEED=0`, and isolated `XDG_CACHE_HOME=$(pi-scratch dir routing-g)/cache`; stopped afterward. Six concurrent `claude-haiku-4-5`, `max_tokens:1` requests with six distinct `x-cc-proxy-session` keys: **six HTTP 200, zero 429**. Proxy log (email labels omitted):

```text
POST /v1/messages -> token 82a293204226 model=claude-haiku-4-5 status 200
POST /v1/messages -> token ccb67338fbdb model=claude-haiku-4-5 status 200
POST /v1/messages -> token ccb67338fbdb model=claude-haiku-4-5 status 200
POST /v1/messages -> token 82a293204226 model=claude-haiku-4-5 status 200
POST /v1/messages -> token a5de118c98c0 model=claude-haiku-4-5 status 200
POST /v1/messages -> token a5de118c98c0 model=claude-haiku-4-5 status 200
```

`PI_ANTHROPIC_PROXY_URL=http://127.0.0.1:8793 bin/llm-usage --capacity`: `capacity: 0 more heavy sessions are safe for the next 2h (accounts: ccb67338fbdb 0, 82a293204226 0, a5de118c98c0 0)`. JSON confirmed `per_session_burn: null`: new isolated cache lacks 15+ minutes of slope samples, so zero means **insufficient measurement**, not proof the pool is spent.

External installed delegate copy `/home/gud1/.pi/agent/skills/delegate/scripts/delegate.sh` was patched alongside its repository copy; this external copy is not tracked in the commit.
