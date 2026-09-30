# 02 — Quota-aware optimization and route explanations

**What to build:** The proxy/Pi route oracle uses the normalized usage concepts to prefer subscription capacity forecast to expire, avoids automatic spending, treats tasks equally by default, handles stale/unknown data conservatively, and explains every provider/model decision.

**Blocked by:** 01 — Normalized provider usage report

**Status:** ready-for-agent

- [ ] Routing prefers usable subscription capacity likely to expire without treating estimates as guarantees.
- [ ] Stale, unknown, exhausted, cooling, and credit-backed states produce distinct decisions.
- [ ] No route decision purchases credits, applies resets, enables reloads, or changes account settings.
- [ ] Equal task weighting is the default and policy controls are explicit/configurable.
- [ ] `_route`, Pi failover, cooldown waiting, and recovery behavior remain compatible.
- [ ] Human-readable route explanations identify the selected candidate and rejected candidates.
- [ ] Policy, stale-data, and failover regression tests pass.
