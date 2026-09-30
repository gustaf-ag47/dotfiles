# Wayfinder: optimize LLM utilization

**Label:** `wayfinder:map`

## Destination

An implementation-ready design for a read-only, multi-provider LLM usage system that maximizes useful work without unexpectedly exhausting subscription quota or spending money. It should combine quota, credits, reset entitlements, model availability, local telemetry, and public provider changes; support automatic local routing; and keep account mutations behind explicit confirmation.

## Notes

- Domain: local dotfiles, Pi, token-proxy, provider usage, and routing.
- Consult: domain modeling, research, prototype, and grilling skills as ticket types require.
- Hosts are independent: laptop and `gud1@skrubben` report their own credentials and proxy state.
- Default policy: no automatic spending; consume subscription capacity forecast to expire; preserve no special provider reserve unless configured later.
- Tasks are treated equally for routing initially.
- Browser/CDP inspection may read rendered pages and page network responses, but billing/reset/account mutations require confirmation.
- Public news is informational only and cannot silently modify routes.

## Decisions so far

<!-- Closed decision tickets will be indexed here. Initial policy decisions were made while charting and are recorded in Notes above. -->

## Not yet specified

- Exact canonical usage model across quota, credits, reset entitlements, availability, and telemetry.
- Which authenticated browser/network surfaces are safe and stable enough to add.
- Optimization algorithm, forecasting confidence, and route-selection explanations.
- News source parser, freshness policy, change classification, and alert presentation.
- CLI/Waybar/Pi presentation and cache/state boundaries.
- Verification strategy across both hosts without copying credentials.

## Out of scope

- Automatic purchases, credit reloads, plan upgrades, or consuming one-time resets without confirmation.
- Copying provider credentials or tokens between hosts.
- Letting public news automatically rewrite routing configuration.
- Building a central cross-host credential or usage authority.

## Open children

- [Define the canonical usage and optimization model](tickets/define-canonical-usage-model.md)
- [Research authenticated provider account surfaces](tickets/research-authenticated-provider-surfaces.md)
- [Research official provider news and release feeds](tickets/research-provider-news-feeds.md)
- [Prototype quota-aware routing decisions](tickets/prototype-quota-aware-routing.md)
- [Prototype the complete usage overview](tickets/prototype-complete-usage-overview.md)
