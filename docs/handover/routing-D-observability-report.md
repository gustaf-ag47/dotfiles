# Routing D observability — report

## Schema and implementation

- `usage.json["_samples"][fingerprint]["5h"|"7d"|"7d_oi"]`: bounded (200) `[epoch_seconds, utilization_fraction]` points. Sampled on header observations; restored history is validated, aged out after eight days, limited to present fingerprints, and reset-crossing history is dropped. `usage.json` remains atomic best-effort persistence.
- Each `tokens[]` row has `forecast[window]` with `burn_per_hour` (fraction/hour, null without two observations spanning 15 minutes), `projected_at_reset` (fraction, clamped 0–1), `forecast` (`waste|exhaust|on_track|unknown`), and numeric epoch `exhaust_at` or null. Quota API utilization supersedes header utilization when available.
- `providers.openai-codex.forecast[window-name]` exposes the same fields, using Codex window utilization/reset. Codex has no locally observed time series, so its slope is currently unknown (and forecast unknown) until a ledger source exists.
- `routing.forecast` has `weekly_waste_percent` (mean predicted unused 7d/7d_oi headroom for windows with usable forecasts; null if unavailable) and `first_exhaust` (`{fp, window, at}` ISO timestamp or null). `routing.recent` is the last 20 JSONL events.
- Routing switch events are appended to `$XDG_CACHE_HOME/cc-proxy/routing.log`; at 1 MB it rotates to `routing.log.1`. Account selection changes are logged per bucket with fingerprint-only `from_fp`/`to_fp`, timestamp, and known `cooldown`/`forced`/`pressure` reason. `POST /_event` accepts JSON `{kind, from, to, reason}` from loopback only; bounded values are appended to the same log.
- `llm-usage` carries `/_usage` fields through its JSON report and renders burn/waste/exhaust/on-track suffixes when supplied, plus pool forecast and three recent route entries.

### Sibling A integration snippet

At the extension provider-switch decision, fire-and-forget after the decision (do not make failover depend on telemetry):

```ts
void fetch(`${proxyUrl}/_event`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ kind: "provider_switch", from: previousProvider, to: nextProvider, reason }) }).catch(() => {});
```

## Gates

- `python3 -m unittest tests.unit.test_claude_token_proxy tests.unit.test_proxy_observability tests.unit.test_llm_usage`: **pass**, 100 tests.
- `make test-unit`: **pass**, 114 tests, 1 existing integration test skipped.

## Second-instance live check

Started an isolated `Handler` instance on `127.0.0.1:8790`, initialized with a synthetic token (no OAuth refresh, no live service restart); cache root was `$(pi-scratch dir routing-d)/cache`.

`curl -s localhost:8790/_usage | jq '.routing.forecast, .routing.recent'`:

```json
{
  "weekly_waste_percent": null,
  "first_exhaust": null
}
[]
```

`PI_ANTHROPIC_PROXY_URL=http://127.0.0.1:8790 XDG_CACHE_HOME=... bin/llm-usage --provider anthropic --refresh`:

```text
LLM usage left   (checked 08:20:32)

anthropic
  5d77358bce3d  UNKNOWN · awaiting fresh reading
    5h        ????????????????????   ?% left
    7d        ????????????????????   ?% left

routing  mode=pressure threshold=0.98
  forecast  weekly waste ? · no projected exhaust
  opus/sonnet (7d)   → 5d77358bce3d
      ● 5d77358bce3d    ?% left  pressure 1.65
  fable (7d fable)   → 5d77358bce3d
      ● 5d77358bce3d    ?% left  pressure 1.65
```

The synthetic instance intentionally has no quota observations, hence null pool forecast.
