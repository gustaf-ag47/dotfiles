# Implementation plan: LLM utilization optimization

This plan is based on `ralph/llm-utilization/specs/llm-utilization.md`, the six local tickets in `.scratch/llm-utilization/issues/`, the current scripts/tests, proxy and Pi extensions, `docs/research/openai-anthropic-usage-surfaces.md`, and the handover notes. The repository already contains substantial committed work (including commits described in `docs/handover/llm-proxy-implementation.md` and recent reflog entries for normalized usage and official news). Those commits are treated as starting evidence only: no task is complete until its current-tree tests and acceptance checks are run again.

## Constraints and dependency graph

- Account purchases, top-ups, reset application, auto-reload, plan changes, OAuth refresh, credential copying, push, and commit are out of scope.
- The report is host-local. `auth.json`, cookies, bearer tokens, raw provider responses, and account identifiers must not cross hosts or enter fixtures/output.
- The proxy remains the request-time router/failover authority. The CLI/report is not a second request router.
- Dependency order: `LLM-01` → `LLM-02` → `LLM-03` → `LLM-04` → `LLM-05` → `LLM-06` → `LLM-07`; `LLM-01` and `LLM-05` can be developed independently after the contract is agreed, but presentation waits for both.
- Existing committed work is explicitly acknowledged in `LLM-01`, `LLM-02`, and `LLM-05`; its commit messages and handover claims do not substitute for fresh verification.

## Tracer-bullet tasks

- [x] LLM-01: lock the versioned normalized report contract and provider-isolated fixtures
  - Dependencies: none. Owned paths: `scripts/llm_usage.py`, `bin/llm-usage`, `tests/unit/test_llm_usage.py`, redacted fixtures under `ralph/llm-utilization/test-fixtures/` if needed.
  - Extend the existing `REPORT_SCHEMA`/`normalize_provider()` seam rather than creating a parallel usage implementation. Make included quota windows, spendable credits, reset entitlements/counts/expiry, model/surface availability, local proxy telemetry, forecasts, freshness, confidence, source, account-safe label, status, reason, and explicit unknowns distinct. Keep provider-native units; never manufacture zero, 100%, exact universal tokens, or eligibility.
  - Bring the human renderer and JSON projection to parity, including OpenAI private-endpoint limitations and Anthropic header-vs-quota-API labels. Preserve proxy counters as local telemetry, not provider billing.
  - Acceptance: one `llm-usage --json` report contains all configured providers even when one fails; healthy, partial, expired, scope-denied, malformed, missing-field, stale, and HTTP-failure cases remain visible and redacted; `--provider`, `--refresh`, cache reuse, and permission-restricted host-local cache behave deterministically.
  - Verify exactly:
    - `python3 -m unittest tests.unit.test_llm_usage -v`
    - `make test-unit`
    - `bin/llm-usage --refresh --json | python3 -m json.tool >/dev/null`
    - `bin/llm-usage --refresh`
    - `stat -c '%a %n' "${XDG_CACHE_HOME:-$HOME/.cache}/llm-usage"/* 2>/dev/null || true`
    - `grep -RInE 'access|bearer|Authorization|api[_-]?key|user_id|account_id|cookie' tests/unit ralph/llm-utilization/test-fixtures 2>/dev/null || true`
  - Evidence required: fresh test output; redacted JSON samples for success and provider failure; cache mode/permissions; a review showing no raw response, token, cookie, or command credential execution. The existing normalized-usage commit may be cited as prior art only.
  - BUILD iteration note: added explicit source/reason fields to each normalized provider observation and a redacted contract test. Acceptance is blocked because this harness exposes no command-execution tool, so the required unittest, make, CLI, cache-permission, and secret-scan checks could not be run; task remains unchecked and no commit was created.
  - BUILD iteration note: added a redacted external-behavior test proving a missing DeepSeek balance remains unknown, then fixed normalization so empty/missing balances do not become a known credit state. Acceptance remains blocked: this harness exposes no command-execution tool, so the exact unittest, make, CLI, cache-permission, and secret-scan checks could not be run; task remains unchecked and no commit was created.
  - BUILD evidence (2026-09-30): added source/reason metadata and hardened normalization against malformed provider payloads without converting unknown values to zero/full capacity. `python3 -m unittest tests.unit.test_llm_usage -v` passed (34 tests); `make test-unit` passed (163 tests, 1 expected skip); JSON and human `bin/llm-usage --refresh` checks passed; cache files/lock were mode 600 (directory mode 700); secret scan found only redacted test canaries and expected field names. No credentials, raw responses, or account mutations were used.

- [ ] LLM-02: reconcile provider/source adapters and freshness semantics
  - Dependencies: `LLM-01`. Owned paths: `scripts/llm_usage.py`, `bin/claude-token-proxy`, `tests/unit/test_llm_usage.py`, `tests/unit/test_claude_token_proxy.py`, `docs/research/openai-anthropic-usage-surfaces.md` only for verified limitations.
  - Make Anthropic proxy observations, Codex `wham/usage`, and DeepSeek balance observations conform to the contract. Preserve read-only behavior: no OAuth refresh, no `!cmd` execution, loopback requests bypass inherited proxies, provider failures never suppress healthy providers. Synchronize the proxy's copied adapters with the richer CLI fields rather than importing the script into the stdlib-only proxy.
  - Include source/timestamp/age/confidence/status/reason on every observation; distinguish stale header data, scope denial, endpoint failure, expired credentials, unknown reset expiry, banked/instant reset count, and credits. Browser facts remain an optional later source.
  - Acceptance: fixtures cover success, partial/missing fields, malformed data, expired credential, HTTP 403/429/401, and provider isolation for all three providers; live-safe output labels Codex as private/undocumented and does not infer purchase eligibility or reset expiry.
  - Verify exactly:
    - `python3 -m unittest tests.unit.test_llm_usage tests.unit.test_claude_token_proxy -v`
    - `make test-unit`
    - `bash -n bin/llm-usage`
    - `bin/llm-usage --provider anthropic --refresh --json | python3 -m json.tool >/dev/null`
    - `bin/llm-usage --provider openai-codex --refresh --json | python3 -m json.tool >/dev/null`
    - `bin/llm-usage --provider deepseek --refresh --json | python3 -m json.tool >/dev/null`
  - Evidence required: fixture assertions for every failure state; current proxy/CLI schemas compared; fresh redaction assertions; no account mutation or token refresh. The existing proxy-oracle commits and handover are not sufficient without these runs.

- [ ] LLM-03: implement conservative quota-aware policy and auditable route oracle
  - Dependencies: `LLM-02`. Owned paths: `bin/claude-token-proxy`, `config/llm-proxy/routes.json`, `config/pi/extensions/llm-failover.ts`, `tests/unit/test_claude_token_proxy.py`, `tests/unit/test_proxy_cross_provider.py`, `tests/unit/test_proxy_observability.py`, `tests/unit/test_llm_failover.mjs`.
  - Keep `_usage` and `_route` contracts compatible and keep route equivalence explicit. Add/verify a policy seam that gives equal task weight by default, makes reserves/task budgets/freshness/confidence configurable, prefers usable subscription headroom forecast to expire, and never selects spendable credits merely because they exist. Make unknown, stale, cooling, exhausted, credit-backed, unavailable-model, and not-routable reasons distinct with deterministic tie-breaking and explanation/confidence.
  - Preserve request-time proxy failover, cooldown waits, recovery polling, manual pinning, model-specific availability, and no-starvation behavior. Public news must not alter routes or policy.
  - Acceptance: `_route` names the selected candidate and every rejected candidate with reason, model, source/freshness or relevant reset; automatic switching happens only where the existing proxy/Pi policy permits; no route path can purchase, reset, reload, or change settings.
  - Verify exactly:
    - `python3 -m unittest tests.unit.test_claude_token_proxy tests.unit.test_proxy_cross_provider tests.unit.test_proxy_observability -v`
    - `node --test --experimental-strip-types tests/unit/test_llm_failover.mjs`
    - `make test-unit`
    - `curl -s --noproxy '*' 'http://127.0.0.1:${CC_PROXY_PORT:-8788}/_route?model=claude-opus-5-5' | python3 -m json.tool >/dev/null` (operator may run only against an already running local proxy)
  - Evidence required: policy matrix tests for equal weighting, forecast/waste, stale/unknown safeguards, credits exclusion, tie-breaking, explanation text, cooldown and recovery; `_usage`/`_route` redaction scan; proof that route configuration is unchanged by news.

- [ ] LLM-04: expose the report through CLI, Pi, and desktop status surfaces
  - Dependencies: `LLM-01`, `LLM-03`, and `LLM-05` for news fields. Owned paths: `scripts/llm_usage.py`, `bin/llm-usage`, `config/pi/extensions/llm-usage.ts`, Waybar module/config under `config/gui/Wayland/waybar/`, any existing i3/polybar usage launcher, and corresponding unit tests.
  - Make `llm-usage` the single report consumer with human, JSON, provider-filtered, refresh, news, forecast/capacity views. Make Pi `/usage` display the same redacted local report and never put account data into model context. Add compact Waybar/desktop output with age, unknown/stale/error warnings, and actionable but non-mutating status. Include news separately from account state.
  - Acceptance: healthy, exhausted, stale, unknown, provider-failure, and news-error fixtures render consistently in CLI, JSON, Pi notification/print mode, and Waybar-compatible output; no renderer calls provider endpoints or duplicates provider logic.
  - Verify exactly:
    - `python3 -m unittest tests.unit.test_llm_usage -v`
    - `node --test --experimental-strip-types tests/unit/test_llm_failover.mjs`
    - `make test-unit`
    - `bash -n bin/llm-usage`
    - `bin/llm-usage --json | python3 -m json.tool >/dev/null`
    - `bin/llm-usage --news --json | python3 -m json.tool >/dev/null`
    - `pi --no-session -p '/usage'` (operator-run smoke check; inspect only local output)
  - Evidence required: renderer fixture snapshots/assertions, a Pi output proving no model-context injection, Waybar command/format validation, JSON compatibility, and a redacted live-safe smoke capture.

- [x] LLM-05: complete the official provider news monitor
  - Dependencies: none for implementation; `LLM-01` before integration in the unified report. Owned paths: `scripts/llm_news.py`, `bin/llm-news`, `tests/unit/test_llm_news.py`, news cache/timer wiring under `config/systemd/user/` and existing desktop integrations.
  - Prior committed work already supplies the four official HTML/release-note sources, `llm-news`, bounded cache, deduplication, classification, and 403/429/parser failure handling. Re-verify and close gaps: conditional/bounded polling, explicit per-source freshness/stale/unavailable metadata, stable content identity, provider filtering, and no auth headers/cookies.
  - Acceptance: OpenAI and Anthropic official news/changelog/release/status surfaces produce quota, billing, model, routing, or general items; stale cache and feed failure are visible and never look like an empty successful feed; news cannot mutate routes, policy, credentials, or billing.
  - Verify exactly:
    - `python3 -m unittest tests.unit.test_llm_news -v`
    - `make test-unit`
    - `bash -n bin/llm-news`
    - `bin/llm-news --refresh --json | python3 -m json.tool >/dev/null`
    - `bin/llm-news --provider openai --json | python3 -m json.tool >/dev/null`
    - `bin/llm-news --provider anthropic --json | python3 -m json.tool >/dev/null`
  - Evidence required: fresh fixture results for duplication, classification, malformed HTML, 403, 429, stale cache, conditional/cache behavior; cache mode/permissions; a diff or test proving route/policy files are untouched. The local ticket is marked done, but this fresh evidence is mandatory.
  - BUILD evidence (2026-09-30): added per-source freshness metadata (fresh/stale/unavailable), conditional ETag/Last-Modified polling with 304 cache reuse, and redacted external-behavior fixtures for freshness, conditional refresh, deduplication/classification, and 403/429 stale fallback. `python3 -m unittest tests.unit.test_llm_news -v` passed (5 tests); `make test-unit` passed (165 tests, 1 expected skip); shell syntax and all three JSON CLI checks passed. Diff review found no auth headers/cookies, route/policy changes, credentials, or account mutations.

- [ ] LLM-06: add opt-in read-only authenticated browser/CDP enrichment
  - Dependencies: `LLM-01`. Owned paths: a new browser adapter module under `scripts/` or `config/pi/lib/` chosen to match existing browser tooling, its redacted fixture tests, and documentation adjacent to `docs/research/openai-anthropic-usage-surfaces.md`; do not alter credentials.
  - Use only a user-approved existing CDP session. Read rendered usage/settings pages and permitted page network responses for account-specific reset expiry, offers, and details unavailable through machine endpoints. Keep this adapter separate and opt-in; normal `llm-usage` must work with no browser.
  - Deny purchase, reset application, auto-reload, plan, checkout, and settings mutation actions by construction (GET/navigation/read parsing only). Persist only redacted values, source URL category, timestamp, freshness, confidence, and explicit degradation reason; never cookies, bearer tokens, raw response bodies, or sensitive identifiers.
  - Acceptance: synthetic CDP/page fixtures cover rendered and network parsing, login expiry, blocked/changed pages, cache expiry, redaction, and mutation denial; no live account session is used in automated tests and no browser action can spend money or consume an entitlement.
  - Verify exactly:
    - `python3 -m unittest discover -s tests/unit -p '*browser*test*.py' -v` (or the exact new test module path)
    - `make test-unit`
    - `grep -RInE 'click.*(buy|purchase|reset|reload|plan)|checkout|set-cookie|Authorization: Bearer' scripts config/pi tests/unit 2>/dev/null || true`
  - Evidence required: CDP fixture output with redacted fields, explicit mutation-denial tests, cache permission/expiry assertions, and operator documentation that inspection is opt-in and read-only. No live credentials or cookies may be recorded.

- [ ] LLM-07: independently verify both hosts and document operational recovery
  - Dependencies: `LLM-01` through `LLM-06`. Owned paths: verification/runbook documentation under `docs/` or `ralph/llm-utilization/`, plus tests only if a reusable redacted smoke script is required. This is the final acceptance task, not a reason to centralize state.
  - Run the same redacted smoke suite independently on the laptop and `gud1@skrubben`: local `auth.json` resolution, cache directory and permissions, proxy `_usage`/`_route`, provider failure isolation, refresh/cache expiry, stale state, news failures, CLI JSON/human output, Pi `/usage`, Waybar-compatible output, and synthetic failover/presentation states. Record host name, schema, timestamps, source/status/freshness, and pass/fail only; do not copy credentials, cookies, raw responses, or account identifiers.
  - Acceptance: each host has independent credentials, cache, proxy state, report timestamps, and installation path; neither host is authoritative for the other; both recover/document expired OAuth, unavailable news feeds, proxy outage, and changed provider surfaces. No account mutation is performed.
  - Verify exactly on each host, with outputs redirected only to host-local redacted scratch files:
    - `git status --short`
    - `make test-unit`
    - `python3 -m unittest tests.unit.test_llm_usage tests.unit.test_llm_news tests.unit.test_claude_token_proxy -v`
    - `node --test --experimental-strip-types tests/unit/test_llm_failover.mjs`
    - `bin/llm-usage --refresh --json | python3 -m json.tool >/dev/null`
    - `bin/llm-news --json | python3 -m json.tool >/dev/null`
    - `curl -s --noproxy '*' 'http://127.0.0.1:${CC_PROXY_PORT:-8788}/_usage' | python3 -m json.tool >/dev/null`
    - `curl -s --noproxy '*' 'http://127.0.0.1:${CC_PROXY_PORT:-8788}/_route?model=claude-opus-5-5' | python3 -m json.tool >/dev/null`
    - `pi --no-session -p '/usage'`
  - Evidence required: two separately generated redacted checklists with host-local paths (not contents), independent cache/report timestamps, failure/recovery results, `git status --short` captured before and after verification, and a secret-scan review. Do not use `scp`, shared cache directories, copied `auth.json`, or copied browser state.

## Exhaustive requirement and ticket mapping

- Spec user stories 1–4 → `LLM-01` (complete provider overview, quota/credits/reset separation, windows and resets).
- Stories 5–9 → `LLM-01`, `LLM-02`, `LLM-03` (model availability/cooldowns, observation age/source, unknowns, forecast confidence, expiring capacity).
- Stories 10–16 → `LLM-03`, `LLM-07` (equal-task default, configurable policy, no spending, explained local routing, host-local credentials/state).
- Stories 17–20 → `LLM-01`, `LLM-02`, `LLM-06` (OpenAI fields/limitations, Anthropic source labels, optional account inspection).
- Stories 21–22 → `LLM-06` (rendered/network read-only inspection and mutation confirmation boundary; mutations remain out of scope).
- Stories 23–26 → `LLM-05`, with route immutability checked in `LLM-03` and `LLM-04`.
- Stories 27–31 → `LLM-01`, `LLM-04`, `LLM-05` (CLI/JSON, Pi, cache/refresh, schema version, provider isolation).
- Stories 32–33 → `LLM-01`, `LLM-02`, `LLM-03` (local telemetry separation, routing history, forecasts/capacity metrics).
- Stories 34–35 → every implementation task's redacted fixtures plus `LLM-07`'s independent two-host smoke suite.
- Implementation decisions: normalized seam → `LLM-01`; proxy route authority → `LLM-03`; Pi presentation/locality → `LLM-04`; observation metadata/domain distinctions → `LLM-01`/`LLM-02`; browser safety/cache → `LLM-06`; OpenAI/Anthropic adapter limitations → `LLM-02`; official news behavior → `LLM-05`; CLI views/schema/cache/isolation → `LLM-01`/`LLM-04`; route equivalence and telemetry source → `LLM-03`.
- Testing decisions: provider/normalization → `LLM-01`/`LLM-02`; policy/proxy/Pi failover → `LLM-03`; browser → `LLM-06`; news → `LLM-05`; renderers → `LLM-04`; two-host → `LLM-07`.
- Out-of-scope protections are acceptance criteria in `LLM-01`, `LLM-03`, `LLM-05`, `LLM-06`, and `LLM-07`.
- Local ticket `01-normalized-provider-usage-report.md` → `LLM-01` and `LLM-02`.
- Local ticket `02-quota-aware-optimization.md` → `LLM-03`.
- Local ticket `03-official-provider-news-monitor.md` (currently checked `[x]`, with prior committed implementation) → `LLM-05`, then `LLM-04`; fresh verification still required.
- Local ticket `04-pi-and-desktop-presentation.md` → `LLM-04`.
- Local ticket `05-read-only-authenticated-account-inspection.md` → `LLM-06`.
- Local ticket `06-two-host-verification-and-operations.md` → `LLM-07`.

## Operator-only rollout instructions

These steps are not BUILD tasks and must be performed explicitly by the operator after review and after all task evidence is accepted. They are read-only unless the operator separately approves an account action; this plan authorizes no account action.

- On each host separately, inspect `git status --short`, installation symlinks, `PI_CODING_AGENT_DIR`, `XDG_CACHE_HOME`, proxy service status, and local `routes.json`. Do not copy or compare credential contents.
- Install/relink the tracked dotfiles through the normal installation path, then restart only the local user proxy if required: `systemctl --user restart claude-token-proxy.service`; wait for its passive read-only poll before inspecting endpoints.
- Run the exact `LLM-07` commands on each host and save only redacted summaries. Treat live endpoint output as account-sensitive; do not paste it into commits, tickets, or shared logs.
- If OAuth is expired, use the provider/Pi's normal interactive login manually; never make `llm-usage`, the proxy, or browser adapter refresh it. If a provider surface changes, disable that adapter locally and rely on explicit unknown/unavailable state until fixtures and tests are updated.
- If the news feed returns 403/429 or parsing fails, leave stale-cache warnings visible; do not replace official sources with third-party sources or change routing.
- If the proxy is unavailable, stop relying on live route decisions, use the local report's unknown state, and follow the existing service recovery procedure. Do not enable DeepSeek fallback, purchase credits, apply resets, or change billing settings as part of rollout.
- Confirm timers/Waybar/Pi only after local smoke checks. Never enable a new timer or browser session by copying another host's state.
