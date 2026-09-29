# Evolving `claude-token-proxy` into a general LLM proxy (Anthropic / OpenAI-Codex / DeepSeek)

Status: decided 2026-09-25 — option (c); implementation tracked in
`docs/handover/llm-proxy-implementation.md`

## Operator decisions (2026-09-25)

1. **pi stays on the OAuth pool** with the Claude-Code identity extension. Accepted
   risk. No new cloaking, no CLIProxyAPI, no multi-tenant sharing; pi keeps its honest
   `originator` on Codex.
2. **Architecture (c):** proxy = Anthropic pool + cross-provider quota/route oracle
   (`/_usage` v2, `GET /_route?model=`); a pi extension does the switching.
3. **Failover is notify-only**, both directions (switch away and switch back). No
   deny-list for now.
4. **DeepSeek Anthropic-passthrough for Claude Code:** implemented, opt-in, off by
   default (`CC_PROXY_DEEPSEEK_FALLBACK=1`), balance floor 1 USD, surfaced in `/_usage`
   routing.
5. **Equivalence table** (`config/llm-proxy/routes.json`): fable → gpt-6-astra, gpt-6-sol
   / deepseek-v4-pro; **opus → gpt-6-luna** / deepseek-v4-pro; sonnet → gpt-6-sol /
   deepseek-flash; haiku → gpt-6-luna / deepseek-flash. Codex before DeepSeek.
6. **DeepSeek label:** `DEEPSEEK_ACCOUNT_LABEL` env first, `auth.json` `label` second,
   last-4 of key fallback. Codex label from the access-token JWT claims.

## Decision 4 (2026-09-26): wait for the earliest reset when nothing is routable

When every OAuth account is cooling for the requested model and no substitute is
routable, pi used to give up: the proxy's 503 `overloaded_error` matches pi's
agent-level retry (`retry.maxRetries` 3, 2/4/8 s backoff), which ignores
`Retry-After`, then the run settles on the error. Sessions whose last message is that
error: 6 on 2026-09-10, 5 on 09-11, 1 on 09-15, and 2 each on 09-20, 09-25 and 09-26.

`llm-failover.ts` now handles `agent_before_settle` (outcome `error`, last message the
proxy's `no OAuth account can serve` 503, provider `anthropic`):

- The wait target is the earliest future `cooldown until <ISO> for <model>` in the 503
  body or the oracle's anthropic `reset_at`, whichever is sooner. One line names the
  time and account: `⏳ … waiting until 00:39:59Z (in 13m) for gs@… to reset`.
- It re-polls `/_route` every `PI_FAILOVER_POLL_SECONDS` (60) and wakes 5–20 s after
  a known reset. Anthropic routable: it resumes. A substitute routable: it switches
  (decisions 2 and 3) and resumes.
- Resume means a `context_edit` that omits the failed attempt (what pi's own retry
  does), followed by `continue: true`. The same run continues, with no user message.
- The cap is `PI_FAILOVER_MAX_WAIT_HOURS` (6), counted across repeated failures and
  reset by a successful turn. A reset past the cap prints one line and does not
  wait. `PI_FAILOVER_WAIT=0` turns waiting off.
- To stop waiting, type a message or run `/failover off`. Esc does not wake the
  wait, because `ctx.signal` is unset at that boundary (pi 0.87.1: no low-level run is
  active).
- No `Retry-After` header on the proxy: pi's agent-level retry never reads it, and
  provider-level retries are off by default and capped at 60 s.

Tests: `tests/unit/test_llm_failover.mjs` (body parsing, plan, cap, the loop, and the
hook against a fake `/_route`), plus `tests/unit/test_pi_wait_for_reset.py` (real pi
against a fake proxy returning 503 then 200).

Date: 2026-09-25. Research only. `bin/`, `scripts/`, `config/` and `~/.pi/agent/*` were
not changed, and no services were restarted. Brief:
`docs/handover/research-generic-llm-proxy.md`. Sibling doc for *what each provider's
account/usage endpoints expose*: `docs/research/openai-deepseek-account-introspection.md`.
This doc covers *routing* only.

## TL;DR and recommendation

1. **Do not turn the proxy into a wire-format translator.** pi is the main client, and it
   already translates between providers natively. It has built-in Anthropic Messages,
   OpenAI Chat Completions and Codex Responses implementations, a normalized transcript,
   and supported cross-provider session handoff (`/model`). Translating
   Messages ⇄ Chat/Responses inside the proxy would duplicate that, lossily, in a
   stdlib-only file. It would also have to cover pi's Codex **WebSocket** transport
   (`openai-codex-responses.js`, `transport: "auto"` tries WebSocket first).
2. **Recommend option (c): provider-native paths plus a thin policy oracle.** The proxy
   stays an Anthropic credential pool. It grows a read-only, cross-provider
   **quota + routing oracle** (`/_usage` v2 and `/_route`). A small pi extension asks the
   oracle and calls `pi.setModel()` when the Anthropic pool can't serve a request. pi
   exposes every hook this needs (`after_provider_response`, `model_select`,
   `setModel`; see §3).
3. **One cheap wire-level exception is worth having:** DeepSeek serves an
   **Anthropic-compatible endpoint** (`https://api.deepseek.com/anthropic`), and its
   primary docs already map `claude-opus*` → `deepseek-v4-pro` and
   `claude-sonnet*/haiku*` → `deepseek-flash`
   ([DeepSeek, Anthropic API guide](https://api-docs.deepseek.com/guides/anthropic_api)).
   The proxy can therefore fail over an Anthropic-shaped request to DeepSeek with **zero
   translation**, just a different upstream host and key. This helps non-pi clients
   (Claude Code). It must be opt-in, because it changes who is billed and who receives
   the context.
4. **Smallest first step with real value (no routing change):** make the proxy's
   `/_usage` the single quota oracle for all three providers. Reuse the adapters that
   `scripts/llm_usage.py` already has, cache them for 60 s, and add a `providers` block.
   Add a pure `GET /_route?model=…` that returns ranked candidates across providers from a
   checked-in equivalence table (§4). Today's outage (2 of 3 Claude accounts cooling,
   Codex 7d at 100 %, DeepSeek at −0.12 USD) would then show up as one "nothing
   routable; next reset X" answer.
5. **Don't adopt an OSS gateway wholesale.** The only project that pools **both** Claude
   and Codex subscription OAuth, translates formats and adds OpenAI-compatible upstreams
   is **CLIProxyAPI** (Go, MIT, 53 k★). Its credential selection is round-robin /
   fill-first, which is weaker than our pressure policy. It also "cloaks" non-Claude-Code
   clients by default (Claude Code identity plus system-prompt replacement), which is
   exactly what Anthropic says it enforces against (§5). **LiteLLM** only forwards
   a single client OAuth header (and that is reported broken on `/v1/messages`,
   [#42170](https://github.com/BerriAI/litellm/issues/42170)). It has no pool, and it had a
   PyPI supply-chain compromise in March 2026. Borrow ideas instead:
   CLIProxyAPI's session-affinity and model-level cooling, teamclaude's
   "Anthropic-compatible backend as low-priority fallback", and 9router's tiered
   "subscription → cheap → free" combos.

## 1. Survey of OSS / hosted LLM proxies

Metadata comes from `gh api repos/…` on 2026-09-25. READMEs were fetched the same day.
"Sub-OAuth" means the project can front **subscription** OAuth credentials, not API keys.

| Project | ★ / license / last push / lang | Routes on | Sub-OAuth Anthropic / Codex | Translates Anthropic ⇄ OpenAI | Verdict |
|---|---|---|---|---|---|
| [router-for-me/CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) | 53.2k / MIT / 2026-09-25 / Go | round-robin, weighted-RR, fill-first; retry rounds on 403/408/429/5xx; per-credential cooldown, optional `claude.model-level-cooling`; session affinity ([config.example.yaml](https://github.com/router-for-me/CLIProxyAPI/blob/main/config.example.yaml)) | **Yes / Yes** (multi-account both), plus OpenAI-compatible upstreams (e.g. DeepSeek) | Yes (OpenAI Chat+Responses, Claude, Gemini; `internal/translator/{claude,codex,openai,…}`), streaming, tools, WebSocket | **Borrow ideas** (or adopt only if we accept (b) and turn cloaking off). It's the closest feature match, but it has no quota-header pressure policy, cloaking is on by default, and it's a large Go service. |
| [KarpelesLab/teamclaude](https://github.com/KarpelesLab/teamclaude) | 344 / MIT / 2026-09-22 / JS | quota headers, `expiryRouting` pressure, 429 kind | **Yes / Yes** (Codex pool "experimental"), **Anthropic-compatible backends (DeepSeek, GLM) as low-priority fallback** | No: each pool serves its own client | **Borrow ideas.** We already ported its pressure math. The DeepSeek-as-Anthropic fallback idea is option (a)'s cheap step. |
| [musistudio/claude-code-router](https://github.com/musistudio/claude-code-router) (CCR) | 37.4k / MIT / 2026-09-20 / TS | conditions on headers/body, ordered fallbacks, retries, credential pools | Kimi subscription only, per README; Claude/Codex sub-OAuth **could not verify** | Yes (OpenAI Chat/Responses, Anthropic, Gemini); lists **Pi** as a supported client | **Ignore for now.** Desktop-app control plane with sponsor-driven provider presets. It routes by rules, not by quota. |
| [decolua/9router](https://github.com/decolua/9router) | 29.8k / MIT / 2026-09-23 / JS | 3-tier combos subscription → cheap → free; round-robin per provider; quota tracking | Yes / Yes (OAuth, auto-refresh), per README | Yes (OpenAI ⇄ Claude ⇄ Gemini ⇄ Responses …) | **Borrow the "combo" concept** (ordered cross-provider fallback list per alias). Too big, and centred on "free tier" use. |
| [BerriAI/litellm](https://github.com/BerriAI/litellm) | 59.6k / MIT-ish (NOASSERTION, enterprise dir) / 2026-09-25 / Python | simple-shuffle (default), latency, least-busy, usage/rate-limit-aware, cost, custom; fallbacks and cooldowns ([routing docs](https://docs.litellm.ai/docs/routing)) | Anthropic: **pass-through of the client's own OAuth header only** ([tutorial](https://docs.litellm.ai/docs/tutorials/claude_code_max_subscription)), broken on `/v1/messages` per [#42170](https://github.com/BerriAI/litellm/issues/42170). Codex: `chatgpt/*` provider, single account per process ([docs](https://docs.litellm.ai/docs/providers/chatgpt), [#40893](https://github.com/BerriAI/litellm/issues/40893)) | Yes, most mature (`/v1/messages` for any backend) | **Ignore as runtime.** Heavy, no OAuth pool, and a [supply-chain incident, 2026-03-24](https://docs.litellm.ai/blog/security-update-march-2026) (1.82.7/1.82.8). Useful as a reference for translation edge cases. |
| [maximhq/bifrost](https://github.com/maximhq/bifrost) | 8.3k / Apache-2.0 / 2026-09-25 / Go | fallbacks, key load-balancing, budgets; "adaptive LB" is enterprise | No (API keys) / No | Yes (OpenAI-compatible surface, Anthropic drop-in) | **Ignore.** A fast API-key gateway, with no subscription-quota concept. |
| [Portkey-AI/gateway](https://github.com/Portkey-AI/gateway) | 13.1k / MIT / 2026-05-25 / TS | retries, fallbacks on chosen status codes, weighted LB, conditional routing | No / No | Yes (OpenAI-shaped universal API) | **Ignore.** Same reason, and it's less active. |
| [Helicone/ai-gateway](https://github.com/Helicone/ai-gateway) | 632 / GPL-3.0 / 2025-11-21 / Rust | latency P2C+PeakEWMA, weighted, cost; rate limits | No / No | OpenAI syntax in front | **Ignore.** Stale for 10 months, and GPL. |
| Kong AI Gateway (`ai-proxy-advanced`) | [Kong/kong](https://github.com/Kong/kong) 44k / Apache-2.0 | round-robin, consistent-hashing, least-connections, lowest-latency, lowest-usage (tokens/cost), semantic, priority ([Kong docs](https://developer.konghq.com/ai-gateway/architecture/)) | No / No | Yes (`llm_format`) | **Ignore.** Needs a full Kong deployment, and advanced features are Enterprise. |
| Cloudflare AI Gateway (hosted) | n/a | ordered fallbacks on error/timeout, `cf-aig-step` header ([docs](https://developers.cloudflare.com/ai-gateway/configuration/fallbacks/)) | No / No | Universal endpoint | **Ignore.** Hosted, API-key only, and sends prompts off-box. |
| OpenRouter (hosted) | n/a | price-weighted (inverse-square) LB across providers, outage-aware fallbacks ([docs](https://openrouter.ai/docs/guides/routing/provider-selection)) | No / No | Yes | **Ignore** for the subscription problem. It could be a paid last-resort tier, but it's a separate bill. |
| [starbaser/ccproxy](https://github.com/starbaser/ccproxy) | 346 / NOASSERTION / 2026-08-10 / Python | DAG hook pipeline; model bindings; Gemini 429/503 fallback chain | Yes (`anthropic_oauth`, `codex_oauth` refresh) / Yes | Yes, own `lightllm` adapter + SSE FSM; routes **DeepSeek via its `/anthropic` endpoint** | **Borrow ideas.** Its mitmproxy+WireGuard interception is overkill. It also advertises "compliance shaping", meaning replayed official-SDK envelopes (see §5). |
| [Soju06/codex-lb](https://github.com/Soju06/codex-lb) | 3.2k / MIT / 2026-09-25 / Python | ChatGPT-account pool LB, usage tracking | – / Yes (pool) | No | **Borrow ideas** if Codex multi-account is ever wanted. The operator ruled that out (`pi-unified-providers-and-dotfiles.md`). |
| [lidge-jun/opencodex](https://github.com/lidge-jun/opencodex) | 16.2k / MIT / 2026-09-25 / TS | per-client "any model" routing | could not verify | Yes (Codex/Claude Code clients → any provider) | **Ignore.** It aims at swapping the brain behind the Codex/Claude Code apps, not at quota routing. |
| [1rgs/claude-code-proxy](https://github.com/1rgs/claude-code-proxy) | 3.8k / none / 2026-06-23 / Python | BIG/SMALL model mapping | No / No | Anthropic → OpenAI/Gemini **via LiteLLM** | **Ignore.** No license, and it's a thin LiteLLM wrapper. |
| [fuergaosi233/claude-code-proxy](https://github.com/fuergaosi233/claude-code-proxy) | 2.8k / MIT / 2026-03-12 / Python | BIG/MIDDLE/SMALL mapping | No / No | Anthropic → OpenAI Chat, own converter (tools, streaming) | **Borrow as reference** for a Messages→Chat converter if (a)-full is ever chosen. |
| [luohy15/y-router](https://github.com/luohy15/y-router) | 384 / MIT / archived | – | No / No | Anthropic → OpenAI (CF Worker) | **Ignore.** Archived; points at OpenRouter's official Claude Code integration. |
| [ding113/claude-code-hub](https://github.com/ding113/claude-code-hub), [QuantumNous/new-api](https://github.com/QuantumNous/new-api) (48.9k, AGPL), [songquanpeng/one-api](https://github.com/songquanpeng/one-api), [Wei-Shaw/claude-relay-service](https://github.com/Wei-Shaw/claude-relay-service) | large, Node/Go + DB | multi-tenant relays, LB, billing | relay-style account pools | Yes | **Ignore.** Multi-tenant "carpool"/resale platforms (Postgres/Redis). They're built for the use case Anthropic explicitly forbids (§5). |
| `llm-router` style ([lm-sys/RouteLLM](https://github.com/lm-sys/RouteLLM), Not Diamond) | RouteLLM 5.5k, last push 2024-08 | learned strong/weak model classifier | No | No | **Ignore.** Capability routing by prompt difficulty, not quota. RouteLLM is dormant. |
| [nguyenphutrong/quotio](https://github.com/nguyenphutrong/quotio) | 4.9k / MIT / Swift | quota view + auto-failover on top of CLIProxyAPI | via CLIProxyAPI | via CLIProxyAPI | **Borrow the UX idea** (one quota board across providers). macOS only. |

`anyrouter` search results were public relay-service check-in bots and relay pools
(e.g. `millylee/anyrouter-check-in`). They're irrelevant here.

## 2. Wire-format translation feasibility

### 2.1 Mapping (Anthropic Messages → OpenAI Chat Completions / Responses)

| Concept | Anthropic Messages | Chat Completions | Responses (Codex) | Lossy corners |
|---|---|---|---|---|
| System prompt | top-level `system` (string or blocks, with `cache_control`) | `messages[0].role=system` (or `developer`) | `instructions` | Block-level cache markers are lost. DeepSeek's catalog sets `supportsDeveloperRole:false`. |
| Tool declaration | `tools[{name,description,input_schema}]` | `tools[{type:function,function:{name,description,parameters}}]` | `tools[{type:function,name,parameters}]` | `strict` mode semantics differ. Anthropic server tools (web_search, code exec) have no equivalent. |
| Tool call | assistant `content[{type:tool_use,id,name,input(obj)}]` | `message.tool_calls[{id,function:{name,arguments(string)}}]` | output item `function_call{call_id,arguments}` | Arguments go from an object to a JSON string, and IDs must be re-mapped consistently across turns. |
| Tool result | user `content[{type:tool_result,tool_use_id,content,is_error}]` | `role:tool, tool_call_id` | input item `function_call_output` | `is_error` has no OpenAI field. Images inside tool results are unsupported in Chat. DeepSeek ignores `is_error`. |
| Thinking | `thinking` blocks with a **signature**, `redacted_thinking`; must be replayed verbatim for tool-use turns | DeepSeek-specific `reasoning_content` (must be echoed back on assistant turns, per the pi DeepSeek compat flag) | encrypted `reasoning` items (`include: reasoning.encrypted_content`) | **Not portable**: signatures and encrypted reasoning are provider-bound. Cross-provider handoff must drop or re-text prior reasoning. |
| Prompt caching | explicit `cache_control` breakpoints, 5 m / 1 h | automatic prefix cache (OpenAI); DeepSeek automatic, `cacheRead` priced | automatic, plus `prompt_cache_key` | Anthropic breakpoints are lost. A provider switch always misses the cache: a full-price re-prefill of maybe 100k+ tokens. |
| Stop reason | `end_turn`, `tool_use`, `max_tokens`, `stop_sequence`, `pause_turn`, `refusal` | `stop`, `tool_calls`, `length`, `content_filter` | `status` + `incomplete_details` | `pause_turn` and `refusal` don't map cleanly. |
| Streaming | typed SSE events: `message_start`, `content_block_start/delta(text_delta, input_json_delta, thinking_delta, signature_delta)/stop`, `message_delta(usage, stop_reason)`, `message_stop` | `data:{choices[].delta}` chunks, `[DONE]`, usage only with `stream_options.include_usage` | typed `response.*` events; pi uses **WebSocket** for Codex by default | You need a state machine that opens and closes blocks, buffers partial tool JSON, and emits usage at the end. Errors that arrive mid-stream after HTTP 200 can't be failed over (CLIProxyAPI buffers the Codex bootstrap for exactly this reason). |
| Usage | `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` | `prompt_tokens`, `completion_tokens`, `prompt_tokens_details.cached_tokens` | `input_tokens`, `output_tokens`, `…details` | Anthropic's input excludes cache reads, while OpenAI's `prompt_tokens` includes cached tokens, so naive summing double-counts. |
| Images / docs | `image`, `document` (PDF), `search_result` | `image_url` | `input_image`, `input_file` | DeepSeek-anthropic: `document` and `search_result` are **not supported**. `deepseek-v4-pro` accepts text only (pi catalog). |

Primary references: the Anthropic Messages streaming spec
(<https://platform.claude.com/docs/en/build-with-claude/streaming>) and OpenAI Responses/Chat
streaming (<https://platform.openai.com/docs/api-reference/responses-streaming>). Both were
cited from knowledge and **not re-fetched in this run**. Search engines were
rate-limiting (Brave 429 / Ecosia 403). The DeepSeek field-support table *was* fetched
([anthropic_api guide](https://api-docs.deepseek.com/guides/anthropic_api)). It lists
`thinking` supported with `budget_tokens` ignored, `redacted_thinking` not supported,
`cache_control` ignored, `tool_result.is_error` ignored, `anthropic-beta` ignored for
`/messages`, and unknown model names mapped to `deepseek-flash`.

### 2.2 Who already implements the translation well

- **pi itself** (`@earendil-works/pi-ai/dist/api/{anthropic-messages,openai-completions,openai-codex-responses}.js`).
  It uses a normalized transcript, and cross-provider handoff is an explicitly tested
  concern (pi `docs/custom-provider.md`, "cross-provider session handoff"). For
  pi-originated traffic, this is the best translator available, and it's already running.
- **CLIProxyAPI** `internal/translator/*` (Go): the most battle-tested OSS translator that
  also handles Codex WebSocket and the in-stream `server_is_overloaded`.
- **LiteLLM** `/v1/messages` adapter (Python): the widest provider coverage, but a large
  dependency.
- **ccproxy `lightllm`** and **fuergaosi233/claude-code-proxy**: small, readable converters
  if we ever need to vendor one.

### 2.3 Translate vs. policy oracle

| | Wire-level router (proxy translates) | Policy oracle (pi switches model) |
|---|---|---|
| Who converts formats | the proxy (new, lossy code) | pi (existing, tested) |
| Thinking/signature handling | must strip or fake per hop, inside a live stream | pi handles handoff at turn boundaries |
| Codex WebSocket | must proxy WS or force `transport: sse` | untouched |
| Mid-stream failover | impossible after the first byte (true today too) | n/a: switch before the next turn |
| Transparency | client thinks it's talking to Claude, and the session log records the wrong model | session records the real provider/model; `/model` shows it |
| Non-pi clients (Claude Code) | benefit | don't benefit (except via DeepSeek's native Anthropic endpoint, §3a-lite) |
| Consent / privacy | silent provider change | the extension can prompt or notify (the earlier research doc asked for **no silent cross-provider failover**) |
| Effort | high, with ongoing churn per API change | low |

**Conclusion:** use an oracle for pi. Keep wire-level only where it needs no translation
(DeepSeek's Anthropic endpoint).

## 3. Architecture options

Shared prerequisites for every option: the equivalence table (§4) lives in one tracked
config file, e.g. `config/llm-proxy/routes.json`. Credentials never enter the repo.
Cross-provider moves are **opt-in per client**, and the default is "notify + switch",
not silent.

### (a) Extend the single-file Python proxy with provider adapters

- **Shape.** Add upstream adapters behind `pick()`. "anthropic-oauth-pool" is today's
  proxy. "deepseek-anthropic" is a passthrough to `api.deepseek.com/anthropic` with
  `x-api-key` and model mapping (no translation). "codex" would need
  Messages→Responses translation, SSE/WS, and Codex OAuth refresh (or reading pi's
  `auth.json`, which races pi's refresh).
- **pi config.** None for Anthropic traffic, because it already goes via the proxy. pi
  would *think* it's talking to Anthropic when served by DeepSeek. Cost display and the
  session model id would both be wrong.
- **llm-usage.** Reads everything from `/_usage` v2.
- **OAuth pools.** Anthropic: as today. Codex: the proxy would own refresh. That
  duplicates pi's login, and the operator ruled out Codex multi-account.
- **Failover decision.** The proxy tries the Anthropic pool first, then deepseek-anthropic
  once `pick()` returns None and fallback is enabled. It is gated by the DeepSeek
  balance being > 0 (`/user/balance`, cached).
- **Effort.** DeepSeek passthrough (the "a-lite" step): about 150 lines plus tests, 1 day.
  Codex translation: about 1.5–3k lines, 1–2 weeks, with permanent maintenance. Stdlib-only
  stays feasible for a-lite. For Codex WS it isn't (no stdlib WebSocket client).

### (b) Adopt an OSS gateway, and reduce `claude-token-proxy` to an Anthropic-OAuth backend

- **Shape.** CLIProxyAPI (the only realistic candidate) on `127.0.0.1:8317`. It owns the
  Codex OAuth and the DeepSeek upstream, and delegates Claude either to its own OAuth
  pool or (via an OpenAI-compatible/Claude "api-key" upstream pointed at `:8788`) to our
  proxy, keeping the pressure policy.
- **pi config.** Point `anthropic`, `openai-codex` and `deepseek` base URLs at the gateway
  (`models.json` `baseUrl` overrides), or register a single `gateway` provider. pi's
  Codex provider sends `originator: pi`. CLIProxyAPI forces the official Codex
  UA/Originator unless `disable-codex-cloaking: true`.
- **llm-usage.** Must scrape CLIProxyAPI's management API. Usage stats were removed in
  v6.10 and moved to third-party add-ons (README). The Anthropic bucket detail stays in
  our `/_usage`.
- **OAuth pools.** Two systems now hold credentials, so there are two refresh owners and
  two places to leak.
- **Failover decision.** Per-credential retry rounds plus model-level cooling. Its
  cross-*provider* failover is via configured model aliases and has no quota awareness.
  Our pressure/7d_oi logic is lost unless we keep `:8788` behind it.
- **Effort.** 1–2 days to stand up, plus ongoing Go-binary updates. The risk is high:
  cloaking defaults (§5), a big attack surface, and a double hop for Anthropic.

### (c) Provider-native paths plus a thin router/oracle (recommended)

- **Shape.** Each provider keeps its native path. Anthropic goes through `:8788` (as
  today). Codex and DeepSeek go direct from pi with pi-owned credentials. The proxy adds
  read-only endpoints and nothing else changes for traffic:
  - `GET /_usage` **schema 2**: today's `tokens`/`routing`, plus
    `providers.{openai-codex,deepseek}`. These come from the same adapters as
    `scripts/llm_usage.py` (move them into an importable module, keep the 60 s cache,
    never refresh OAuth).
  - `GET /_route?model=claude-opus-5-5`: an ordered candidate list, each entry with
    `{provider, model, routable, reason, resets_at, cost_tier}`. It uses the §4 table,
    the Anthropic `pick()` preview (already exists as `routing_preview()`), the Codex
    `wham/usage` `allowed` / `model_usage.*.available_at` (see the sibling doc), and the
    DeepSeek `is_available`/balance.
  - Optional `POST /_observe`: the pi extension forwards Codex `x-codex-primary-*` /
    `secondary-*` response headers (the names are confirmed in
    [openai/codex `rate_limits.rs`](https://github.com/openai/codex/blob/main/codex-rs/codex-api/src/rate_limits.rs)).
    This gives near-live Codex quota without polling. It's localhost only, and the header
    allow-list must drop auth headers.
- **pi extension** `config/pi/extensions/llm-failover.ts`, about 150 lines:
  - on `after_provider_response` (status + headers): post the Codex quota headers to
    `/_observe`, and remember 429/503 status.
  - on a failed turn (Anthropic 503 "no OAuth account can serve", Codex
    `usage_limit_reached`, DeepSeek 402): `GET /_route`, then `ctx.ui` notify/confirm,
    then `pi.setModel(next)` and let pi's normal retry run on the next turn.
    `setModel` returns false when auth is missing, so it falls through to the next
    candidate.
  - a `/route` command that shows the oracle answer. The same data drives `llm-usage` and
    Waybar.
- **Non-pi clients.** Claude Code gets only the (a-lite) DeepSeek passthrough, if enabled.
- **llm-usage.** Becomes a thin renderer of `/_usage` v2, falling back to its own adapters
  when the proxy is down.
- **OAuth pools.** Anthropic stays in `~/cctoken` under the proxy. Codex stays a single
  pi-owned account. The proxy only *reads* pi's `auth.json` via the existing read-only
  adapter, and never refreshes it.
- **Failover decision.** An ordered list per requested model (§4). Skip a candidate when
  it is not routable: Anthropic has no pickable token for that model scope, Codex has
  `allowed:false` or the model is unavailable, or DeepSeek has `is_available:false` or
  balance ≤ 0. Prefer subscription over metered. Among subscription candidates, prefer
  the earliest-perishing headroom (reuse `pressure()`). Never downgrade more than one
  tier without asking.
- **Effort.** Oracle: about 250 lines of Python plus tests, 1–2 days. Extension: about
  150 lines of TS, 1 day, tested against a mock oracle.

### Recommendation and sequencing

1. **Step 1 (value on day 1, zero routing risk):** `/_usage` schema 2 plus `/_route`, and
   `llm-usage` rendering from it. This is read-only.
2. **Step 2:** the pi `llm-failover.ts` extension in *notify-and-switch-on-confirm* mode.
3. **Step 3 (optional):** a-lite DeepSeek Anthropic passthrough in the proxy, behind
   `CC_PROXY_FALLBACK=deepseek` (off by default), for Claude Code sessions.
4. Revisit (b) only if Codex multi-account pooling becomes a requirement.

## 4. Model-equivalence table

Sources: pi's installed catalog (`pi --list-models`; `pi-ai/dist/providers/data/*.json`,
prices in USD per 1M tokens, input/output), `~/.pi/agent/models.json` (Codex context
overrides), and DeepSeek's own Claude-name mapping
([anthropic_api guide](https://api-docs.deepseek.com/guides/anthropic_api)). **No
capability benchmarks were compared.** The price tier is used as a proxy for the model
tier, so treat the substitutes as *starting points* for operator judgement, not as proven
equivalence.

| Claude model (pi price) | Codex substitute (sub-OAuth) | DeepSeek substitute (metered) | Notes |
|---|---|---|---|
| `claude-fable-5-1` (10/50, 1M ctx) | `gpt-6-astra` (10/50; 1.1M via models.json override, catalog 272K) | `deepseek-v4-pro` (1.32/3.96, **text-only**) | Fable is the top tier. The DeepSeek substitute is a clear capability drop and should need explicit confirmation. Astra was `unavailable` in `model_usage` at 07:50Z (sibling doc). |
| `claude-opus-5-5` (4/20, 1M) | `gpt-6-sol` (2/10, 272K) or `gpt-5.6-sol` (4/20, 272K) | `deepseek-v4-pro` (DeepSeek maps `claude-opus*` → v4-pro) | The context drop from 1M to 272K matters for long sessions, and pi may need to compact first. |
| `claude-sonnet-5` (2/10, 1M) | `gpt-6-sol` (2/10) / `gpt-5.6-terra` (2/12) | `deepseek-flash` (V4.1 Flash, 0.3/1.2, 1M, images) | DeepSeek maps `claude-sonnet*` → flash. |
| `claude-haiku-4-5` (1/5, 200K) | `gpt-6-luna` (0.1/0.5, 1M override) | `deepseek-flash` | Cheap tier for delegates and summaries. |

- **Tool calling:** every listed model is a tool-capable agent model in pi's catalog.
  DeepSeek has `supportsStrictMode:true`, and Codex models add OpenAI grammar tools.
- **Reasoning:** all are `reasoning:true`, but the level maps differ.
  `deepseek-v4-pro` only accepts `high`/`max` (so `minimal`/`low`/`medium` → null), and
  `deepseek-flash` accepts `low`/`high`/`max`. The extension should re-clamp the thinking
  level after `setModel` (pi does clamp).
- **DeepSeek names:** `deepseek-chat` / `deepseek-reasoner` were discontinued
  2026-07-24 ([changelog 2026-04-24](https://api-docs.deepseek.com/updates)). The current
  names are `deepseek-flash` (V4.1 Flash, released 2026-09-10) and `deepseek-v4-pro`
  (still served after 2026-09-14, per the [changelog](https://api-docs.deepseek.com/updates)).
  `deepseek-v4-flash` is a temporary alias ([pricing](https://api-docs.deepseek.com/quick_start/pricing)).
  Peak/off-peak: off-peak is half price.

## 5. Risks and ToS

- **Anthropic subscription OAuth outside Claude Code is prohibited and enforced.**
  Anthropic's Claude Code legal page (fetched 2026-09-25) says OAuth "is intended
  exclusively for … ordinary use of Claude Code and other native Anthropic applications",
  and that Anthropic "may [enforce] without prior notice"
  ([legal-and-compliance](https://code.claude.com/docs/en/legal-and-compliance)). Timeline
  from secondary reporting: silent block on 2026-01-09 (reverted), ToS clarified in
  Feb 2026 ([The Register](https://www.theregister.com/2026/02/20/anthropic_clarifies_ban_third_party_claude_access)),
  enforcement for third-party harnesses from 2026-04-04
  ([dev.to summary](https://dev.to/mcrolly/anthropic-kills-claude-subscription-access-for-third-party-tools-like-openclaw-what-it-means-for-3ipc),
  citing The Verge/TNW; not independently re-fetched). pi's own binary warns: *"Third-party
  harness usage draws from extra usage and is billed per token, not your Claude plan
  limits"* (`dist/modes/interactive/interactive-mode.js:140`).
  - **Relevance here:** the current setup's `anthropic-oauth-claude-code-identity.ts`
    plus the Claude-Code beta/UA headers in the proxy's probe are the "client identity
    spoofing" mechanism the community reports as the enforcement target
    ([awesomeagents summary](https://awesomeagents.ai/news/claude-code-oauth-policy-third-party-crackdown/)).
    Every option here keeps or amplifies that exposure. (b) with CLIProxyAPI cloaking
    amplifies it most. Pooling **three** accounts held by one person also sits uneasily
    with "advertised limits assume ordinary, individual usage". **This is an operator
    risk decision, not something the proxy design can fix.** The design can avoid making
    it worse: no multi-tenant sharing, no new identity cloaking, and no resale/relay
    platforms.
- **OpenAI/Codex is more permissive, but not unlimited.** Third-party harnesses using the
  user's own ChatGPT OAuth are publicly supported (OpenCode added Codex auth in v1.1.11,
  Jan 2026, [devgenius](https://blog.devgenius.io/jump-ship-in-minutes-codex-oauth-now-works-in-opencode-d2708c32f571);
  pi ships it natively and identifies itself honestly with `originator: pi`).
  Multi-account rotation is an *open feature request* upstream
  ([openai/codex#9648](https://github.com/openai/codex/issues/9648),
  [#41610](https://github.com/openai/codex/issues/41610)), not a sanctioned behaviour.
  Unexplained Codex/Pro bans are anecdotally reported
  ([community.openai.com](https://community.openai.com/t/codex-chatgpt-pro-account-banned-with-no-warning-no-explanation-18-month-subscriber/1381906);
  one post, cause unknown). CLIProxyAPI ships `identity-confuse` and default Codex UA
  cloaking, which shows its users worry about fingerprinting. Keep pi's honest
  `originator` and don't pool Codex.
- **The `wham/usage` endpoint is undocumented.** Oracle readings can break silently, so
  mark them `unavailable`, never 0 % (sibling doc).
- **DeepSeek:** a metered, prepaid key. A silent fallback can burn balance, and a
  negative balance returns 402. The data goes to a different jurisdiction (PRC-hosted
  provider), so **cross-provider failover sends the whole conversation context to a new
  recipient**. Keep it opt-in, and consider per-repo deny-lists (e.g. work
  repos → no DeepSeek).
- **Localhost oracle security:** `:8788` has no client auth (existing). `/_observe` must
  accept only allow-listed `x-codex-*` rate-limit headers and never bodies or
  Authorization.
- **Prompt-cache economics:** every provider switch re-prefills the full context at
  uncached price. The router should switch only on hard unavailability, not on small
  pressure differences, which matches the proxy's existing stickiness philosophy.

## Open questions for the operator

1. Pick (a)/(b)/(c). Recommended: (c), steps 1→2, with 3 optional.
2. Should cross-provider failover in pi be **confirm-each-time**, **notify-only**, or
   **silent**? Any repos or paths that must never go to DeepSeek or OpenAI?
3. Enable the DeepSeek Anthropic passthrough for Claude Code sessions (option a-lite), and
   with what balance floor?
4. Are the §4 substitutes acceptable, especially Fable → `gpt-6-astra` and
   Opus → `gpt-6-sol` vs `gpt-5.6-sol`?
5. Given §5, does the operator want to keep the Claude-Code identity extension at all, or
   move pi's Anthropic traffic to an API key or extra-usage billing and keep OAuth only
   for the real Claude Code CLI?

## Method and sources

- Repo: `bin/claude-token-proxy`, `scripts/llm_usage.py`,
  `docs/research/{claude-token-rotation-oss,anthropic-ratelimit-buckets,claude-routing-investigation,pi-unified-providers-and-dotfiles,openai-deepseek-account-introspection}.md`.
- pi 0.85.x install: `docs/{custom-provider,models,extensions,settings,providers}.md`,
  `dist/core/extensions/types.d.ts` (`after_provider_response`, `model_select`,
  `setModel`), `pi-ai/dist/providers/data/{anthropic,openai-codex,deepseek}.json`,
  `pi-ai/dist/api/openai-codex-responses.js` (WebSocket transport, `originator: pi`).
- GitHub metadata via `gh api repos/*` and `search/repositories`. READMEs via
  `gh api repos/*/readme`, all 2026-09-25. CLIProxyAPI `config.example.yaml` fetched the
  same day.
- Web pages via `web-research/fetch.py` on 2026-09-25: DeepSeek anthropic_api, pricing and
  updates; LiteLLM routing, the Claude Max tutorial, issue #42170; Cloudflare AI Gateway
  fallbacks; OpenRouter provider selection; the Claude Code legal page; the dev.to ban
  summary. Search engines were mostly blocked (Brave 429, Ecosia 403). Remaining searches
  used DuckDuckGo HTML, and the ToS timeline relies on secondary articles for anything
  beyond Anthropic's own legal page.
- **Could not verify:** CCR/opencodex support for Claude/Codex subscription OAuth, Kong
  plugin details beyond search snippets, Helicone's project status, and model capability
  parity (no benchmarks run).
