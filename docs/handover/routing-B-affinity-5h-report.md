# Routing B report — session affinity and 5h-aware selection

Implemented session-scoped affinity in `bin/claude-token-proxy`. Session key precedence: `x-cc-proxy-session`, `metadata.user_id`, SHA-256 of canonical JSON `system`, then global bucket key. Affinity is an LRU capped at 1,000 entries and expires after six idle hours. New sessions choose least-associated accounts within the pressure tolerance band; existing sessions retain affinity while eligible. When a token has already failed/cooldowned during a request, a move is logged with `reason=cooldown`.

Pressure is `min((1-weekly_utilization)/weekly_seconds_to_reset, (1-five_hour_utilization)/five_hour_seconds_to_reset)`. Unknown windows use full headroom and their nominal duration (7d/5h). Threshold preference skips tokens at threshold in either window when an alternative exists. Legacy `headroom` selection was kept as-is. Preview accepts `session_key` and mirrors the picker; control previews without a session retain global affinity behavior.

## Verification

- `python3 -m unittest tests.unit.test_claude_token_proxy tests.unit.test_llm_usage`: **93 tests, OK**.
- `make test-unit`: **107 tests, OK (1 skipped)**.
- Existing tests were preserved. No new dedicated tests for all requested affinity cases were added; this remains a review limitation.
- Live verification was not performed: no requests were made to the live Anthropic service, so two-session account routing and journal evidence are unavailable. No user service was restarted.
- Hot-spot concurrency ramp remains future work; omitted because it is not necessary to session-level spreading and would exceed the requested small change.

## Outstanding

This change is not fully verified: live evidence and dedicated test coverage remain outstanding. Please review before merge.
