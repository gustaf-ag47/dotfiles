# Research brief: open-source Claude multi-account rotation/proxy solutions

## Context

We run a homegrown local proxy (`bin/claude-token-proxy` in this repo, ~900
lines, Python stdlib only) that rotates Anthropic subscription OAuth tokens
across 3 accounts by live weekly-quota headroom, with mid-request failover on
429/401/403/529. We are about to redesign the selection policy:

- today: pick token with lowest `7d` utilization (most headroom)
- proposed: earliest-deadline-first — prefer the token whose weekly window
  resets soonest (perishable quota first), with a headroom safety margin,
  and model-aware bucket selection (`claude-fable-*` models seem to be metered
  on a separate `7d_oi` bucket).

Before building, survey prior art. Research only — do NOT modify any code.

## Job (numbered, checkable)

1. Review github.com/KarpelesLab/teamclaude (our proxy cites it as inspiration).
   What selection policy does it use today? Failover behavior? Anything about
   reset-time-aware or model/bucket-aware routing? Has it changed recently?
2. Find other open-source projects that rotate/pool multiple Claude
   subscription accounts or Claude Code OAuth tokens behind one endpoint.
   Search terms to try: "claude token rotation proxy", "claude code multi
   account", "sk-ant-oat proxy", "anthropic oauth pool", "claude subscription
   load balancer", GitHub code search for `anthropic-ratelimit-unified-7d`.
   For each: link, language, selection policy (round-robin / least-used /
   deadline-aware / sticky), failover handling, how they read quota, activity.
3. Specifically: has ANYONE implemented reset-time-aware (EDF-style) selection
   for perishable weekly quotas? If yes, how do they handle the hot-spotting
   problem (one account absorbing all load until it 429s)?
4. Note any clever mechanisms worth stealing regardless of policy: sticky
   sessions per conversation (prompt-cache affinity!), request cost estimation,
   per-model routing, health probing, token refresh handling.
5. Give a short recommendation: adopt/borrow vs keep building our own, and the
   2–3 concrete ideas most worth porting into `bin/claude-token-proxy`.

## Constraints

- Use the web-research skill: /home/gud1/.pi/agent/skills/web-research/SKILL.md
  (read it first). GitHub code search and repo READMEs are primary sources.
- You may read `bin/claude-token-proxy` and
  `tests/unit/test_claude_token_proxy.py` for comparison. Do NOT edit any file
  except your findings file. Do NOT commit; the parent commits.
- Do not read `~/cctoken` or print any credential material.
- Every claim about a project needs a URL; note last-commit dates (abandonware
  matters).

## Where to record findings

Write `docs/research/claude-token-rotation-oss.md` in this repo (create the dir
if missing; a sibling agent writes a DIFFERENT file in the same dir —
`anthropic-ratelimit-buckets.md` — do not touch it). Structure: Summary +
recommendation first, then per-project table, then details. Do not commit.

## Cost guidance

Budget roughly 30–45 min. Prioritize breadth (find the projects) over depth;
deep-dive only the 2–3 most relevant. If blocked (e.g. search engines
unusable), record what you tried in the findings file and stop.

## Parent

Report is picked up by the parent session that spawned you. When done, finish
your turn; the watcher notifies the parent.
