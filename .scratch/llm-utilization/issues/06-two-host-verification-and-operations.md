# 06 — Two-host verification and operations

**What to build:** Independent operational verification on the laptop and `gud1@skrubben`, proving that credentials, caches, provider observations, refresh behavior, routing, presentation, and failure recovery work without copying secrets or making one host authoritative.

**Blocked by:** 01 — Normalized provider usage report; 02 — Quota-aware optimization and route explanations; 03 — Official provider news monitor; 04 — Pi and desktop usage presentation; 05 — Read-only authenticated account inspection

**Status:** ready-for-agent

- [ ] Both hosts run the redacted usage/news smoke suite independently.
- [ ] Host-local credentials, caches, proxy state, and report timestamps are verified.
- [ ] No credentials, cookies, or raw account responses cross hosts.
- [ ] Refresh timers, cache expiry, endpoint failures, and stale-state behavior are documented.
- [ ] Routing and Pi/desktop presentation are verified against synthetic and live-safe states.
- [ ] Recovery procedures exist for expired OAuth, unavailable feeds, proxy failure, and changed provider surfaces.
