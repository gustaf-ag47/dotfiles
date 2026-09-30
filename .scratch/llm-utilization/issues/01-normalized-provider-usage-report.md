# 01 — Normalized provider usage report

**What to build:** A complete `llm-usage` report that presents Anthropic, ChatGPT/Codex, and DeepSeek through one versioned model, separating quota, credits, reset entitlements, model availability, local telemetry, freshness, confidence, and unknown values. It must support human-readable and JSON output, caching, redaction, and provider-isolated failures.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Anthropic, Codex, and DeepSeek observations normalize into one versioned report.
- [ ] Quota, credits, reset entitlements, availability, telemetry, derived forecasts, freshness, and confidence remain distinct.
- [ ] Missing, stale, scope-denied, and failed observations remain explicit unknown states.
- [ ] Human-readable and JSON output expose the same information without secrets.
- [ ] Cache and refresh behavior is host-local and permission-restricted.
- [ ] Existing and new redaction/provider-fixture tests pass.
