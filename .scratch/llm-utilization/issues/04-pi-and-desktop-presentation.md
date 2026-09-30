# 04 — Pi and desktop usage presentation

**What to build:** Pi `/usage`, Waybar, and desktop CLI views present the complete normalized usage report and relevant provider news while ensuring private account information stays local and is never sent to the selected model.

**Blocked by:** 01 — Normalized provider usage report; 03 — Official provider news monitor

**Status:** ready-for-agent

- [ ] Pi `/usage` exposes the same redacted report as the CLI.
- [ ] Waybar shows useful compact status with freshness and actionable warnings.
- [ ] CLI supports usage/news views without duplicating provider logic.
- [ ] JSON output remains suitable for scripts and integrations.
- [ ] Account details are displayed only through local UI notifications/output.
- [ ] Presentation tests cover healthy, exhausted, stale, unknown, and news-error states.
