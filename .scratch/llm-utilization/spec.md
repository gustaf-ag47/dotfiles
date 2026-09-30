# LLM utilization optimization

**Tracker label:** `ready-for-agent`
**Status:** Ready for ticket decomposition

## Problem Statement

The dotfiles expose useful but fragmented LLM information. Anthropic quota windows come from proxy observations, ChatGPT/Codex usage comes from a private usage endpoint, DeepSeek exposes a balance, and Pi/proxy routing has separate state and explanations. The current `llm-usage` report does not consistently distinguish included quota, spendable credits, one-time reset entitlements, model availability, stale observations, forecasts, and local traffic.

The user needs to maximize useful work across the laptop and `gud1@skrubben` without unexpectedly exhausting an account or spending money. Public provider changes can also affect model availability and interpretation, but must remain informational and must not silently alter routing.

## Solution

Build a host-local, read-only usage intelligence layer centered on a normalized usage report. Provider adapters collect redacted snapshots; optional browser and news adapters enrich them; a policy layer evaluates freshness, confidence, remaining capacity, and forecast-to-expire capacity; and existing proxy request-time routing remains responsible for live failover.

The system must show a complete, honest overview in `llm-usage`, Waybar, and Pi, while keeping account mutations behind explicit confirmation. It must operate independently on each host without copying credentials or treating one host's proxy state as authoritative for the other.

## User Stories

1. As a developer, I want to see every configured provider in one report, so that I know where useful capacity remains.
2. As a developer, I want included subscription quota separated from spendable credits, so that I do not mistake one for the other.
3. As a developer, I want one-time/banked reset entitlements shown separately from credits, so that I understand what can be consumed and what can be purchased.
4. As a developer, I want every quota window's remaining percentage and reset time, so that I can plan work.
5. As a developer, I want model-specific availability and cooldowns, so that a provider marked generally available does not mislead me about a particular model.
6. As a developer, I want the source and age of every observation, so that stale header data is not mistaken for live account truth.
7. As a developer, I want unknown values shown as unknown, so that unavailable endpoints never appear as zero or full capacity.
8. As a developer, I want forecast confidence and assumptions displayed, so that estimated future capacity is not confused with an entitlement.
9. As a developer, I want capacity likely to expire before reset highlighted, so that I can use otherwise-wasted subscription capacity.
10. As a developer, I want the optimizer to treat tasks equally by default, so that routing does not silently prioritize one task class.
11. As a developer, I want optimization policy configurable, so that I can later introduce reserves or task budgets without redesigning the report.
12. As a developer, I want no provider purchase or reload performed automatically, so that quota optimization cannot create unexpected charges.
13. As a developer, I want local routing changes to happen automatically when policy permits, so that a request can use an available equivalent provider without manual intervention.
14. As a developer, I want route decisions to explain why a provider was selected or rejected, so that failover is auditable.
15. As a developer, I want provider credentials to stay on their host, so that the laptop and `skrubben` cannot leak or overwrite one another's accounts.
16. As a developer, I want each host to report its own freshness and proxy state, so that a stale remote reading cannot affect local routing.
17. As a developer, I want OpenAI credit balance, reset count, reset windows, and model availability displayed together, so that I can distinguish available credits from included usage.
18. As a developer, I want the limitations of OpenAI's private usage endpoint visible, so that missing reset expiry or purchase eligibility is not inferred.
19. As a developer, I want Anthropic subscription quota observations labelled as headers or account API data, so that I know when scope limitations reduce accuracy.
20. As a developer, I want optional authenticated browser inspection of provider settings, so that account-specific reset expiry and offers can be observed when no public endpoint exposes them.
21. As a developer, I want browser inspection to read rendered pages and page network responses without mutating state, so that account data can be enriched safely.
22. As a developer, I want purchases, reset application, auto-reload, plan changes, and other account mutations to require explicit confirmation, so that automation cannot spend money or consume a one-time entitlement unexpectedly.
23. As a developer, I want provider news and release notes collected from official sources, so that model and plan changes are visible without relying on third-party summaries.
24. As a developer, I want news items classified as quota, billing, model, routing, or general, so that relevant changes are easy to find.
25. As a developer, I want news freshness, parser failures, HTTP blocking, and stale cache state shown, so that an empty feed is not mistaken for no changes.
26. As a developer, I want public news to remain informational, so that a vendor announcement cannot silently rewrite routing or spend policy.
27. As a developer, I want `llm-usage` to support human-readable and JSON output, so that Waybar, Pi, scripts, and me can consume the same report.
28. As a Pi user, I want `/usage` to show the same redacted report without sending private account data to the selected model, so that usage information remains local.
29. As a developer, I want cached reports with explicit refresh controls, so that status commands are responsive without hiding freshness.
30. As a developer, I want the report schema versioned, so that future adapters and consumers can evolve safely.
31. As a developer, I want failures isolated per provider, so that one unavailable vendor endpoint does not hide healthy providers.
32. As a developer, I want local proxy telemetry kept separate from provider-wide billing, so that request counters are not mistaken for account usage.
33. As a developer, I want current routing and forecast metrics retained, so that I can evaluate whether optimization actually reduces starvation and waste.
34. As a developer, I want tests to use redacted fixtures, so that provider credentials and account identifiers never enter test output.
35. As a developer, I want both hosts verified independently, so that installation and credential differences are visible before relying on the overview.

## Implementation Decisions

- The highest seam is a normalized usage-report boundary in the existing usage-reporting layer. Provider adapters produce a common redacted snapshot; renderers consume the normalized report.
- The live Anthropic proxy remains responsible for request-time token selection, failover, cooldowns, and the existing route oracle. The usage report may consume its redacted state but must not become a second request router.
- Pi remains a presentation/integration consumer. Its usage command invokes the local report and never injects account details into model context.
- Every provider observation carries at least: provider, account label/fingerprint where safe, observation timestamp, source, freshness/age, confidence, status, and reason when unavailable.
- The domain model distinguishes:
  - included quota windows;
  - spendable credit balances;
  - reset entitlements/counts and, when available, expiry;
  - model/surface availability;
  - local request/token telemetry;
  - derived forecasts and estimated capacity.
- Quota and credits are never collapsed into a single “tokens left” value. Literal token counters remain telemetry; quota and balance remain provider-native units.
- Missing, stale, scope-denied, and endpoint-unavailable values remain explicit. The system must not synthesize zero, 100%, or eligibility from absence.
- The default optimization policy performs no automatic spending. It prefers using subscription capacity forecast to expire, subject to configurable freshness/confidence and safety controls. Tasks are equally weighted by default.
- Policy decisions return an explanation and confidence, not only a provider/model choice. They must distinguish “not routable,” “unknown,” “cooling down,” “quota exhausted,” “credits available,” and “would waste capacity.”
- Local routing may switch providers/models automatically when the existing proxy/Pi failover policy permits it. Account mutations require interactive confirmation.
- Browser/CDP inspection is an optional adapter. It may read authenticated rendered usage pages and page network responses, but must not click purchase, reset, reload, plan, or settings mutation controls without confirmation.
- Browser-derived values are cached as redacted data with source URL category and timestamp; cookies, bearer tokens, raw response bodies, and account identifiers are never persisted in the report.
- The OpenAI adapter continues using the private Codex usage surface only as an explicitly labelled source. It exposes windows, resets, credits, reset count, and model availability when present; it does not infer reset expiry, purchase eligibility, or prices.
- The Anthropic adapter consumes proxy/account observations and labels header-derived quota as potentially stale when the quota endpoint is unavailable or scope-denied.
- Public news uses official OpenAI and Anthropic news, changelog, release-note, and status surfaces. RSS is optional, not required.
- News polling is read-only, bounded, cached, conditional where possible, and resilient to HTTP 403/429 and parser failures. A stale or failed feed is reported explicitly.
- News items are deduplicated by provider, canonical URL, title/date, and content hash; classified into quota, billing, model, routing, or general categories; and exposed separately from account state.
- News never modifies routes, policy, credentials, or account settings automatically.
- The report supports human-readable, JSON, provider-filtered, refresh, news, and forecast/capacity views while preserving a versioned schema.
- Cache files are host-local, permission-restricted, and separate from credentials. Each host's report is independent; no cross-host merge or credential replication is required.
- Existing proxy state, routing logs, and counters remain the source for local telemetry and historical routing metrics. Provider adapters remain the source for current account observations.
- Existing route-equivalence configuration remains explicit and reviewable. News may warn about model changes but cannot rewrite it.

## Testing Decisions

Tests should assert externally visible normalized data, policy outcomes, redaction, freshness semantics, and rendered output—not helper implementation details.

Test the following modules and behaviors:

- Provider adapters: representative success, partial response, expired credential, HTTP failure, malformed response, and missing-field fixtures for Anthropic, OpenAI/Codex, and DeepSeek.
- Normalization: quota, credits, reset entitlements, model availability, telemetry, freshness, confidence, and unknown-state handling.
- Policy: equal-task routing, forecast-to-expire preference, stale/unknown safeguards, no automatic spending, explanation text, and deterministic tie-breaking.
- Browser adapter: synthetic CDP/page fixtures, redaction, read-only behavior, network-response parsing, mutation denial, and cache expiry. No live account session belongs in automated tests.
- News adapter: official fixture pages, deduplication, classification, conditional/cache behavior, malformed HTML, HTTP 403/429, stale cache, and feed-unavailable output.
- Report/renderers: JSON schema, CLI output, Waybar-compatible output, Pi notification behavior, and provider isolation.
- Proxy integration: preserve current `_usage` and `_route` contracts, failover behavior, cooldown waits, route explanations, and no credential leakage.
- Two-host verification: run the same redacted smoke suite on the laptop and `gud1@skrubben`; verify independent auth/cache paths and no copied secrets.

Prior art to extend includes `tests/unit/test_llm_usage.py`, proxy observability/cross-provider/routing tests, Pi provider integration tests, and existing redaction tests around `_usage` and Codex fixtures.

## Out of Scope

- Automatic purchases, auto-reload, plan upgrades, applying banked/instant resets, or changing provider billing settings.
- Copying credentials, cookies, or account state between hosts.
- A central fleet-wide usage authority or cross-host merged credential store.
- Silent route/config changes based on public news.
- Treating public announcements as authoritative account quota.
- Converting provider-native quotas into an exact universal token or task count.
- Replacing the existing request-time proxy/failover architecture with a CLI-only router.
- General third-party news aggregation in the first version.
- API billing/accounting for providers not configured in the existing environment.

## Further Notes

The current repository already has a useful foundation: provider adapters and caching in the usage script, Anthropic proxy observability, a cross-provider route oracle, Pi failover, and redaction-focused tests. Implementation should deepen these seams rather than create a parallel router.

The implementation should be decomposed into tracer-bullet tickets in this order: normalized report contract; provider/source adapters and freshness; policy/oracle explanations; CLI/Pi/Waybar presentation; official news monitor; optional browser adapter; independent two-host verification.

The research note `docs/research/openai-anthropic-usage-surfaces.md` records the currently verified public/provider surfaces and their limitations.
