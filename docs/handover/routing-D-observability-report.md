# Routing D observability — implementation report

## Status: blocked / partial

This branch adds an initial bounded per-token sample ledger, persisted as `_samples` in `usage.json`, a pure slope/forecast helper, routing-log append/rotation helpers, forecast fields on token snapshots, recent-route/routing-summary placeholders, and a loopback-only `POST /_event`. Token values are not included in telemetry. The `/_event` schema accepts `{kind, from, to, reason}`.

The requested end-to-end work is **not complete**. In particular, account-to-account route change detection is not wired; samples are not yet validated/pruned robustly on restore; Codex forecast and pool weekly-waste/first-exhaust calculations are absent; the `llm-usage` rendering/JSON additions and synthetic observability tests are absent; no live second-instance check was performed. Do not rely on the placeholder pool forecast values.

## Suggested sibling A extension call

At the provider-switch site in `config/pi/extensions/llm-failover.ts`, after deciding the switch and without awaiting/blocking failover, post to the local proxy:

```ts
void fetch(`${proxyUrl}/_event`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ kind: "provider_switch", from: previousProvider, to: nextProvider, reason }) }).catch(() => {});
```

## Validation

- `python3 -m py_compile bin/claude-token-proxy`: pass.
- `python3 -m unittest tests.unit.test_claude_token_proxy tests.unit.test_llm_usage`: pass (93 tests).
- `tests.unit.test_proxy_observability`: not created; required gate incomplete.
- `make test-unit`: not run.
- Live check: not run.

## Live output

Unavailable: no second instance was started. The required `/_usage` curl and `llm-usage` output remain to be captured after completion.
