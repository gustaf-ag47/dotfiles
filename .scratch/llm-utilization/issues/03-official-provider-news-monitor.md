# 03 — Official provider news monitor

**What to build:** A cached, read-only news view for official OpenAI and Anthropic news, changelog, release-note, and status surfaces. It reports freshness and parser/network failures, deduplicates entries, and classifies quota, billing, model, routing, and general changes without modifying routes.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [x] Official OpenAI and Anthropic sources are polled conservatively and cached locally.
- [x] RSS is optional; HTML/release-note sources remain supported.
- [x] Items are deduplicated and retain source, title, date, category, and content identity.
- [x] Quota, billing, model, routing, and general classifications are exposed in text and JSON.
- [x] HTTP 403/429, parser errors, stale cache, and unavailable feeds are visible.
- [x] News cannot rewrite routes, policy, credentials, or account settings.
- [x] Fixture tests cover source changes, duplication, failures, and stale data.
