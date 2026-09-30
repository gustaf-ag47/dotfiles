# 05 — Read-only authenticated account inspection

**What to build:** An opt-in browser/CDP adapter reads authenticated provider settings pages and their network responses to enrich the report with account-specific reset expiry, offers, and details unavailable through public or existing private endpoints.

**Blocked by:** 01 — Normalized provider usage report

**Status:** ready-for-agent

- [ ] Browser inspection is explicitly opt-in and independent of normal `llm-usage` operation.
- [ ] Rendered usage pages and page network responses can provide redacted account facts.
- [ ] Cookies, bearer tokens, raw response bodies, and sensitive identifiers are never persisted.
- [ ] Purchase, reset application, reload, plan, and settings mutation actions are denied by default.
- [ ] Browser-derived facts include source, timestamp, freshness, and confidence.
- [ ] Browser absence, login expiry, blocked pages, and changed page structure degrade clearly.
- [ ] CDP fixtures test parsing and mutation denial without a live account session.
