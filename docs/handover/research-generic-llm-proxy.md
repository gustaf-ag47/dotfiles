# Brief — Research: evolve claude-token-proxy into a general LLM proxy (anthropic / openai / deepseek)

**Agent:** delegated pi sub-agent (research only, no production code changes).
**Parent:** the orchestrator pi pane in the operator's tmux session. **Date:** 2026-09-25.
**Repo:** `$DOTFILES` = `/home/gud1/sync/src/dotfiles`, default branch `master`.

## Context

`bin/claude-token-proxy` (~1100 lines, single-file Python 3, stdlib only) is a local
HTTP proxy on `127.0.0.1:8788` that sits between pi / Claude Code and
`api.anthropic.com`. It:

- holds a pool of Anthropic **subscription OAuth tokens** (Claude Max accounts; token
  file rows labelled with the account email),
- reads the `anthropic-ratelimit-unified-*` response headers to track per-bucket
  utilisation (`5h`, `7d`, `7d_oi` = Fable weekly bucket, `7d_opus`, `7d_sonnet`),
- picks a token per request with a "pressure" policy (perishable headroom per second,
  see `pressure()` / `pick()`), sticky within a tolerance,
- classifies 429s as quota-vs-burst, applies **model-scoped** cooldowns
  (`quota_cooldown_scope`, `apply_cooldown`), fails over across tokens,
- exposes `GET /_status`, `GET /_usage` (with a read-only `routing` preview, added
  today in commit `59902e7`), persists counters to `$XDG_CACHE_HOME/cc-proxy/usage.json`,
- optionally polls `/api/oauth/usage` when the OAuth scope permits.

`scripts/llm_usage.py` (`bin/llm-usage`) is the read-only reporter. It already has
three adapters: `anthropic` (via the proxy `/_usage`), `openai-codex` (ChatGPT
subscription `wham/usage` endpoint, read from pi's `~/.pi/agent/auth.json`), `deepseek`
(`/user/balance`). Read both files fully before anything else. Also read the earlier
research in `docs/research/claude-token-rotation-oss.md`,
`docs/research/anthropic-ratelimit-buckets.md`, and
`docs/research/claude-routing-investigation.md` so you do not redo them.

pi is the primary client. It speaks provider-native APIs (Anthropic Messages, OpenAI
Responses/Chat Completions for `openai-codex` OAuth, OpenAI-compatible for DeepSeek).
pi's provider/model config lives under `~/.pi/agent/` (`auth.json`, `models.json`,
`settings.json`); see `docs/research/pi-unified-providers-and-dotfiles.md` and the pi docs at
`/home/gud1/.local/share/npm/lib/node_modules/@earendil-works/pi-coding-agent/docs/`
(`custom-provider.md`, `models.md`).

The operator's goal, verbatim: *"setup claude-token-proxy to be a llm-proxy in general
that can route between deepseek, openai, and anthropic."* The motivation is quota
exhaustion: today (2026-09-25) two of three Anthropic accounts are in cooldown, the
Codex 7-day window is at 100%, and DeepSeek balance is negative — the operator wants
ONE place that knows all quotas and can route/fail over across providers, plus one
reporter that shows what's left everywhere.

## Your job

This is **investigation-first. Do not modify `bin/claude-token-proxy`, `scripts/llm_usage.py`,
or any pi config.** Produce a design/research doc that the operator can decide from.

1. **Survey open-source LLM proxies/routers** that already do multi-provider routing
   with quota/cost awareness and failover. At minimum evaluate: LiteLLM proxy,
   Portkey gateway, OpenRouter (hosted), Bifrost (maximhq), Helicone gateway, Cloudflare
   AI Gateway, Kong AI gateway, `llm-router`-style projects, and anything found by
   searching GitHub for "claude code proxy", "anthropic to openai proxy", "oauth token
   rotation", "codex oauth proxy", "claude-code-router" (musistudio), "ccproxy",
   "claude-code-proxy" (1rgs / fuergaosi233), "y-router", "anyrouter". For each: what it
   routes on (cost, latency, quota headers, error codes), whether it can front
   **subscription OAuth** (not API keys) for Anthropic and ChatGPT/Codex, whether it
   translates between Anthropic Messages ⇄ OpenAI Chat/Responses wire formats, how it
   handles streaming + tool calls + thinking blocks, license, activity, and size.
   Cite URLs. Verdict per project: adopt / borrow ideas / ignore, with a one-line why.
2. **Wire-format translation feasibility.** The hard part of "route an Anthropic-shaped
   request to DeepSeek/OpenAI" is translating Messages API ⇄ Chat Completions /
   Responses API (system prompts, tool_use/tool_result, streaming SSE event shapes,
   thinking/reasoning content, cache_control, stop reasons). Document the mapping and
   the known lossy corners. Identify which OSS projects already implement it well enough
   to vendor or shell out to. Consider the alternative: **do not translate** — make the
   proxy a *policy oracle* that pi consults (or that rewrites pi's `models.json`
   / provider selection) instead of a wire-level router. Weigh both.
3. **Architecture proposal** for the dotfiles proxy, three options with trade-offs:
   (a) extend the single-file Python proxy with provider adapters (keep stdlib-only?),
   (b) adopt an OSS gateway (e.g. LiteLLM/Bifrost) and reduce `claude-token-proxy` to
   an Anthropic-OAuth "credential backend" behind it,
   (c) keep provider-native proxies per provider + a thin router/oracle in front.
   For each: what pi config changes, how `llm-usage` gets its data, how OAuth token
   pools for Anthropic AND Codex would be handled, how failover across providers is
   decided (quota %, cooldown, cost, model capability equivalence — e.g. which DeepSeek
   / OpenAI model is an acceptable substitute for `claude-opus-5`?), and rough effort.
   Recommend one, with the smallest first step that delivers value (likely: make the
   proxy's `/_usage` the single quota oracle across all three, before touching routing).
4. **Model-equivalence table**: for each Claude model the operator uses
   (`claude-opus-5-5`, `claude-fable-5-1`, `claude-sonnet-5`, `claude-haiku-4-5`), the
   candidate substitute on OpenAI (Codex OAuth models — check `~/.pi/agent/models.json`
   and the pi model list for what's actually available, e.g. `gpt-6-luna`, `gpt-5.6-sol`)
   and DeepSeek (`deepseek-chat` / `deepseek-reasoner` — verify current names on
   api-docs.deepseek.com), with notes on tool-calling and reasoning support.
5. **Risks and ToS**: note anything about proxying subscription OAuth traffic for
   Anthropic/OpenAI that the OSS community has flagged (bans, header fingerprinting,
   `User-Agent`/beta-header requirements). Cite.

## Scope fence

- **You own:** `docs/research/generic-llm-proxy.md` (new) — and nothing else.
- **Do NOT touch:** `bin/`, `scripts/`, `config/`, `tests/`, `~/.pi/agent/*`, the
  running `claude-token-proxy.service`. Do not restart services. Do not log in anywhere.
- Sibling running in parallel: a research agent on **OpenAI + DeepSeek account/usage
  introspection** owning `docs/research/openai-deepseek-account-introspection.md`. Do not
  duplicate that: you cover *routing*; it covers *what account/usage info each provider
  can expose*. You may reference its file path.

## Constraints

- Read the repo's `CLAUDE.md`/`README.md` first. Conventional-commit format is
  enforced by a hook: `type(scope): subject`, lowercase, ≤50 chars, imperative.
- Research quality: primary sources (official docs, project READMEs/source) over blog
  posts. Every non-obvious claim carries a URL. Note fetch dates. Say "could not
  verify" where you could not.
- Use the `web-research` / `brave-search` skills for searching; `gh api` for GitHub
  metadata (stars, last commit, license).
- Scratch files go under `$(pi-scratch dir llm-proxy-research)`, never `/tmp`.
- Never paste tokens, keys, or account ids from `auth.json` or the token file into the
  doc. Emails (account labels) are fine.

## Where to record findings

`docs/research/generic-llm-proxy.md` in `$DOTFILES`, with a `Status:` line at the top
(`Status: research — awaiting operator decision on option (a)/(b)/(c)`). Commit on
`master` and push (`git push origin master`). Structure: TL;DR + recommendation first;
then the survey table; then wire-format section; then the three options; then the
equivalence table; then risks; then sources. Keep it under ~400 lines; put long tables
in appendices.

Also drop the raw run output to the operator vault:
`$NOTES/<project>/driver/agent-runs/2026-09-25/<HHMM>_generic-llm-proxy-output.md`
(`$NOTES=/home/gud1/sync/Vault`) with YAML front-matter `model`, `cost_usd`, `branch`,
`landed_in`.

## When blocked

If a site is unreachable or a fact cannot be verified, say so in the doc and move on.
Do not ask the operator questions mid-run; record them in a "Open questions" section.

## Cost guidance

Target ~$8. Stop at $15 with what you have, written up.
