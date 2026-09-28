# Routing C — DeepSeek backstop report

## Operator top-up wizard

Run from the repository root:

```bash
bash scripts/deepseek-topup-wizard.sh
```

The wizard opens DeepSeek's top-up page, requires human confirmation, then reads
`~/.pi/agent/auth.json` (or `$PI_CODING_AGENT_DIR/auth.json`) and queries
`GET https://api.deepseek.com/user/balance`. It never prints, saves, or asks for
the API key. Success requires `is_available == true` and USD `total_balance` strictly
above `CC_PROXY_DEEPSEEK_MIN_BALANCE` (default `1.0`). It prints:

```text
llm-usage --provider deepseek --refresh
```

**Current published pricing checked 2026-09-27:** DeepSeek's official pricing page
(https://api-docs.deepseek.com/quick_start/pricing/) lists peak per-million rates of
$1.32 input / $3.96 output for V4 Pro and $0.30 / $1.20 for `deepseek-flash`
(V4.1 Flash); off-peak is half-price. For 5M uncached input + 200k output this is
$7.392 peak / $3.696 off-peak for Pro, and $1.74 / $0.87 for Flash. The wizard
recommends a $10 top-up to cover that representative peak Pro day with a small buffer.
This is a simple tokens-times-list-price estimate; cache hits cost less, and prices
may change. Pricing page notes peak hours are 01:00–04:00 and 06:00–10:00 UTC on
weekdays excluding Chinese public holidays.

Source corroboration: the official DeepSeek Pi integration page also documents model
ids and rates: https://api-docs.deepseek.com/quick_start/agent_integrations/pi_mono/.
Its example models identify `deepseek-v4-pro` and `deepseek-v4-flash`; the current
pricing page says the current Flash alias is `deepseek-flash` and legacy Flash ids are
served by V4.1 Flash.

## Passthrough readiness evidence

Tested a second process on `127.0.0.1:8790`, with `CC_PROXY_DEEPSEEK_FALLBACK=1`,
`CCTOKEN_FILE=$HOME/cctoken`, and a separate `XDG_CACHE_HOME` under
`$(pi-scratch dir routing-c)`. All three OAuth fingerprints were placed in that
instance's isolated `force_cooldown`; no live 8788 control/cache file was touched.
A normal poll of the real balance state correctly blocked fallback because the
account currently reports `is_available=false` and balance `-0.12 USD`. For the
transport test only, the isolated instance was given a synthetic healthy cached
balance so it could call the actual DeepSeek Messages endpoint (the real account has
no balance, so this request could not incur inference charges).

Redacted request/result:

```text
POST /v1/messages -> deepseek deepseek-v4-pro (fallback: anthropic pool exhausted) model=claude-opus-5-5
POST /v1/messages -> deepseek deepseek-v4-pro status 402
HTTP 402; error type=unknown_error; message=Insufficient Balance (request_id: [redacted])
```

DeepSeek's own HTTP 402 and error body reached the client unchanged. The proxy log
showed the fallback attempt and status. OAuth requests during startup returned 403;
the fingerprint cooldown still ensured none was selected for inference.

## Policy and pi extension

`config/systemd/user/claude-token-proxy.service` gets no fallback environment from
`systemctl --user cat`; it has no `EnvironmentFile`, and the proxy default is off.
Keep it off by default: fallback bills a different provider and sends conversations
to that provider, so it must remain an explicit operator opt-in. **No live service was
restarted, edited, or enabled.**

Existing `llm-failover.ts` consumes `first_routable` and selects routable non-Anthropic
candidates; existing `tests/unit/test_llm_failover.mjs` covers the deepseek candidate,
including notification of `deepseek/deepseek-v4-pro` when selection reaches it. Pi's
installed provider model registry (`@earendil-works/pi-ai/dist/providers/data/deepseek.json`)
contains `deepseek-v4-pro` and `deepseek-flash`; routes.json uses those exact ids.
`~/.pi/agent/models.json` has no custom deepseek entry, but the installed pi registry
provides the built-in DeepSeek provider and models, so no route-id change was needed.

## Gates

- `bash -n scripts/deepseek-topup-wizard.sh`: **pass**
- `shellcheck scripts/deepseek-topup-wizard.sh`: **pass**
- `python3 -m unittest tests.unit.test_claude_token_proxy tests.unit.test_proxy_deepseek_backstop`: **pass**, 73 tests
- `make test-unit`: **pass**, 111 tests, 1 expected skip
- Wizard dry abort (stubbed URL opener; declined top-up): **pass**, stage rendered and safely exited before balance check.

New focused tests are in `tests/unit/test_proxy_deepseek_backstop.py`. Existing shared
`DeepseekPassthroughTests` remain untouched. No changes were required to proxy logic,
routes, or the service configuration.
