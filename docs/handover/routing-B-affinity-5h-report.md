# Routing B report — session affinity and 5h-aware selection

Implemented session-scoped affinity in `bin/claude-token-proxy`. Session key precedence: `x-cc-proxy-session`, `metadata.user_id`, SHA-256 of canonical JSON `system`, then global bucket key. Affinity is an LRU capped at 1,000 entries and expires after six idle hours. New sessions choose least-associated accounts within the pressure tolerance band; existing sessions retain affinity while eligible. When a token has already failed/cooldowned during a request, a move is logged with `reason=cooldown`.

Pressure is `min((1-weekly_utilization)/weekly_seconds_to_reset, (1-five_hour_utilization)/five_hour_seconds_to_reset)`. Unknown windows use full headroom and their nominal duration (7d/5h). Threshold preference skips tokens at threshold in either window when an alternative exists. Legacy `headroom` selection was kept as-is. Preview accepts `session_key` and mirrors the picker; control previews without a session retain global affinity behavior.

## Verification

- `python3 -m unittest tests.unit.test_claude_token_proxy tests.unit.test_llm_usage`: **100 tests, OK**.
- `make test-unit`: **114 tests, OK (1 skipped)**.
- Added seven dedicated tests covering two-session spreading, same-session stickiness, cooldown movement, 5h threshold preference, 5h-pressure dominance, preview/picker parity with session key, and affinity expiry.
- Live check used a separate worktree instance on port 8790 (`CCTOKEN_FILE=$HOME/cctoken`, isolated scratch cache); the system service on 8788 was untouched. Three `claude-haiku-4-5`, `max_tokens:1` Messages requests returned HTTP 200. Log evidence:
  ```text
  POST /v1/messages -> token ccb67338fbdb model=claude-haiku-4-5 ... status 200  # session A
  POST /v1/messages -> token a5de118c98c0 model=claude-haiku-4-5 ... status 200  # session B
  POST /v1/messages -> token ccb67338fbdb model=claude-haiku-4-5 ... status 200  # session A again
  ```
- Hot-spot concurrency ramp remains future work; omitted because it is not necessary to session-level spreading and would exceed the requested small change.

## Outstanding

Concurrency hot-spot ramp remains future work; affinity now spreads newly opened sessions without introducing a coordination ramp.
