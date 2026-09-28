# Routing D observability — report

## Schema and implementation

- `usage.json["_samples"][key][window]`: bounded (200) `[epoch_seconds, utilization_fraction]` points. Anthropic keys are token fingerprints with windows `5h`, `7d`, `7d_oi`; Codex keys are `codex:<window-name>`. Header observations and successful `openai-codex` provider refreshes are sampled. Restore validates/ages/prunes data and retains only current fingerprints plus Codex series. A window reset drops prior points.
- Each `tokens[]` row has `forecast[window]` with `burn_per_hour` (fraction/hour, null without two observations spanning 15 minutes), `projected_at_reset` (fraction, clamped 0–1), `forecast` (`waste|exhaust|on_track|unknown`), and numeric epoch `exhaust_at` or null. Quota API utilization supersedes header utilization when available.
- `providers.openai-codex.forecast[window-name]` has the same fields. Codex samples come from the read-only `wham/usage` poll (normally every five minutes).
- `routing.forecast` has `weekly_waste_percent` (mean projected unused 7d/7d_oi headroom where measurable; null if unavailable) and `first_exhaust` (`{fp, window, at}` ISO timestamp or null). `routing.recent` is the last 20 JSONL events.
- Routing switch events append to `$XDG_CACHE_HOME/cc-proxy/routing.log`; at 1 MB it rotates to `routing.log.1`. Account changes are logged per bucket with fingerprint-only `from_fp`/`to_fp`, timestamp, and known `cooldown`/`forced`/`pressure` reason. `POST /_event` accepts JSON `{kind, from, to, reason}` from loopback only.
- `llm-usage` carries fields through its JSON report and renders burn/waste/exhaust/on-track suffixes when supplied, plus pool forecast and three recent route entries.

### Sibling A integration snippet

At the extension provider-switch decision, fire-and-forget after the decision (do not make failover depend on telemetry):

```ts
void fetch(`${proxyUrl}/_event`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ kind: "provider_switch", from: previousProvider, to: nextProvider, reason }) }).catch(() => {});
```

## Gates

- `python3 -m unittest tests.unit.test_claude_token_proxy tests.unit.test_proxy_observability tests.unit.test_llm_usage`: **pass**, 101 tests.
- `make test-unit`: **pass**, 114 tests, 1 existing integration test skipped.

## Real-data second-instance check

Used a second `8790` instance with `CCTOKEN_FILE=$HOME/cctoken`, `XDG_CACHE_HOME=$(pi-scratch dir routing-d)/real-cache`, and a copy of the live `~/.cache/cc-proxy/usage.json`; the live usage file and service were not changed. It restored the three accounts, fetched read-only quota/provider status, seeded header observations, waited more than 15 minutes, and issued one minimal one-token Haiku request through this isolated instance to obtain a second real header sample. That request was needed for a real measured slope. Instance stopped after the check.

`curl -s localhost:8790/_usage | jq '{routing:.routing.forecast, tokens:[.tokens[]|{fp,forecast}], codex:.providers["openai-codex"].forecast}'` (actual result, compacted to the measured token and Codex window):

```json
{
  "routing": {"weekly_waste_percent": 35.0,
    "first_exhaust": {"fp":"ccb67338fbdb","window":"7d","at":"2026-09-29T03:09:22+00:00"}},
  "tokens": [{"fp":"ccb67338fbdb","forecast":{
    "5h":{"burn_per_hour":0.18356,"projected_at_reset":0.62315,"forecast":"waste","exhaust_at":null},
    "7d":{"burn_per_hour":0.03671,"projected_at_reset":1.0,"forecast":"exhaust","exhaust_at":1790651362.53},
    "7d_oi":{"burn_per_hour":0.0,"projected_at_reset":0.3,"forecast":"waste","exhaust_at":null}}}],
  "codex":{"primary_window":{"burn_per_hour":0.0,"projected_at_reset":0.0,"forecast":"waste","exhaust_at":null}}
}
```

`PI_ANTHROPIC_PROXY_URL=http://127.0.0.1:8790 XDG_CACHE_HOME=... bin/llm-usage --provider anthropic --refresh` actual forecast rendering (account labels abbreviated):

```text
anthropic
  account ccb67338fbdb  READY
    5h        95% left   resets in 3h 07m · burn 18.4%/h · will waste ~38%
    7d        72% left   resets in 4d 18h · burn 3.7%/h · exhausts in 19h 36m
    7d fable  70% left   resets in 4d 18h · burn 0.0%/h · will waste ~70%
  account 82a293204226  READY
    5h        90% left   resets in 7m
    7d         5% left   resets in 1d 22h
    7d fable   1% left   resets in 1d 22h
  account a5de118c98c0  READY
    5h        73% left   resets in 2h 07m
    7d        66% left   resets in 6d 02h
    7d fable  61% left   resets in 6d 02h

routing  mode=pressure threshold=0.98
  forecast  weekly waste 35.0% · first exhaust ccb67338fbdb 7d at 2026-09-29T03:09:30+00:00
```

The endpoint response and CLI are from real quota headers / restored quota readings and the real Codex poll. Anthropic OAuth quota API calls returned scope/rate-limit errors in this run, so its `quota` detail was unavailable; headers remain the selected quota source. Rate slopes reflect the seed/header readings and the one minimal smoke request, not account-wide billing.
