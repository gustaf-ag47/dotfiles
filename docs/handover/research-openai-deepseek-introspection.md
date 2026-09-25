# Brief — Research: richer account & usage introspection for OpenAI (ChatGPT/Codex OAuth) and DeepSeek

**Agent:** delegated pi sub-agent (research only, no production code changes).
**Parent:** the orchestrator pi pane in the operator's tmux session. **Date:** 2026-09-25.
**Repo:** `$DOTFILES` = `/home/gud1/sync/src/dotfiles`, default branch `master`.

## Context

`scripts/llm_usage.py` (`bin/llm-usage`) is a read-only quota reporter with three
adapters. Read it fully first (it is ~330 lines). What each adapter knows today:

- **anthropic** — via the local `claude-token-proxy` (`GET /_usage`): per-account
  email label, 5h/7d/7d-fable utilisation, cooldowns, routing choice. This is the
  "gold standard" the other two should approach.
- **openai-codex** — reads pi's OAuth credential from `~/.pi/agent/auth.json`
  (`type: oauth`, `access`, `expires`, `accountId`) and calls
  `GET https://chatgpt.com/backend-api/wham/usage` with `Authorization: Bearer` +
  `ChatGPT-Account-Id`. It gets back `rate_limit.primary_window` /
  `secondary_window` (`used_percent`, `limit_window_seconds`, `reset_at`),
  `allowed`, `limit_reached`. It does NOT know: **which account/email** this is, the
  plan tier (Plus/Pro/Team), the per-model breakdown, whether there are separate
  windows per model family, credits/overage, or anything about the org.
- **deepseek** — `GET https://api.deepseek.com/user/balance` with the API key from
  `auth.json` or `DEEPSEEK_API_KEY`. Gets `balance_infos[]` (`currency`,
  `total_balance`, `granted_balance`, `topped_up_balance`) and `is_available`. Does
  NOT know: account email/name, usage history, per-model spend, rate limits, whether
  the key is scoped, or when the balance changed.

The operator wants, verbatim: *"expand and get more information on openai, like account
name and similar. Same for deepseek."* The purpose is the same as the Anthropic side:
when a quota is out, the report should tell the operator **which account to log into**
and **what exactly is exhausted / when it resets / what it costs to top up.**

Hard rules the existing reader enforces and you must respect in any recommendation:
read-only; **never refresh OAuth tokens** (pi owns that); never execute credential
commands (`!cmd` keys); never log or print tokens; never send local traffic through an
inherited HTTP proxy for loopback. See the docstring at the top of `llm_usage.py`.

Related prior research to read so you do not duplicate it:
`docs/research/pi-unified-providers-and-dotfiles.md`,
`docs/research/claude-token-rotation-oss.md`.

## Your job

Investigation-first. **Do not modify `scripts/llm_usage.py` or any pi config.** You MAY
run read-only `curl`/`python` probes against the endpoints using the credentials pi
already holds, as long as you never print the bearer token / key and never call any
endpoint that mutates or refreshes anything. Redact ids in the doc.

1. **OpenAI / ChatGPT / Codex OAuth account introspection.** Find every read-only
   endpoint reachable with the ChatGPT OAuth access token that returns identity or
   quota information. Start from: how `openai/codex` (the official Codex CLI, GitHub
   `openai/codex`) itself displays account/usage — read its source for the endpoints
   it calls (`/backend-api/wham/usage`, `/backend-api/me`, `/api/accounts/check`,
   `/backend-api/accounts/check/v4-2023-04-27`, `auth.openai.com` userinfo /
   `id_token` claims, anything else). The **id_token JWT** pi stores may already carry
   `email`, `chatgpt_plan_type`, `chatgpt_account_id` claims — decode it (base64,
   locally, no network) and document exactly which claims are present. Also check what
   pi's `openai-codex` provider itself stores (`auth.json` fields) and whether pi's
   source (`/home/gud1/.local/share/npm/lib/node_modules/@earendil-works/`) calls any
   account endpoint. Then survey OSS: projects that show ChatGPT/Codex quota in a status
   bar or CLI (search GitHub for "codex usage", "chatgpt rate limit status bar", "wham/usage",
   "codex-cli usage widget", "ccusage"-style tools for Codex, `sst/opencode` openai
   provider, `block/goose`). Document: endpoint, method, required headers, response
   schema (redacted real sample from a probe), what each field means, refresh cadence
   the community uses, and which fields answer "which account" / "what plan" /
   "how much left per model" / "when does it reset".
2. **OpenAI Platform API keys** (if the operator ever adds one): what
   `api.openai.com` exposes for a key — `/v1/organization/usage/*`,
   `/v1/organization/costs`, `/v1/models`, `/dashboard/billing/*` (deprecated?),
   admin-key requirements, and the `x-ratelimit-*` response headers. One section, brief.
3. **DeepSeek account introspection.** From api-docs.deepseek.com and OSS clients:
   what besides `/user/balance` exists (usage/billing history, key listing, model
   listing, rate-limit headers on responses, `x-ratelimit-*`?). Is there any way to
   learn the account email/name from the API key, or must the label come from local
   config (e.g. a comment in auth/env like the Anthropic token file does)? Recommend a
   labelling convention that fits how `llm_usage.py` reads credentials today. Also check
   whether the DeepSeek platform web dashboard has an internal JSON API that the
   community reads (like ChatGPT's `backend-api`), and whether that is worth the
   fragility. Note top-up mechanics (minimum amount, currency) so the report can say
   "top up at <url>".
4. **Proposal for `llm_usage.py`**: for each provider, the concrete new fields the
   adapter would return and the rendered lines they'd produce (mock the output in the
   doc in the same style as the current anthropic section: bold account name, status
   verdict, bars). Include what needs to change in `auth.json`/env for labels, and any
   new caching rules (e.g. id_token decode is free; `wham/usage` should stay at the
   existing 60s cache). Keep the security posture above. Flag any endpoint that is
   undocumented/internal and could break.
5. **Unit-test plan**: `tests/unit/test_llm_usage.py` exists — list the fixtures
   (redacted real responses) the implementation PR should add.

## Scope fence

- **You own:** `docs/research/openai-deepseek-account-introspection.md` (new) — and
  nothing else.
- **Do NOT touch:** `bin/`, `scripts/`, `config/`, `tests/`, `~/.pi/agent/*`, the
  running `claude-token-proxy.service`. Do not log in anywhere, do not refresh tokens,
  do not top up anything.
- Sibling running in parallel: a research agent on **multi-provider routing / generic
  LLM proxy** owning `docs/research/generic-llm-proxy.md`. Do not cover routing; it
  covers routing. You cover what each provider can *tell us about the account*.

## Constraints

- Read the repo's `CLAUDE.md`/`README.md` first. Conventional-commit format is
  enforced by a hook: `type(scope): subject`, lowercase, ≤50 chars, imperative.
- Primary sources over blogs; every non-obvious claim carries a URL and fetch date.
  Mark anything from an internal/undocumented endpoint as such.
- Use `web-research` / `brave-search` skills for search; `gh api` for repo metadata.
- Scratch under `$(pi-scratch dir openai-deepseek-research)`, never `/tmp`.
- **Never** print or commit a bearer token, API key, refresh token, or full account id.
  Redact to first 6 chars. Emails are fine.

## Where to record findings

`docs/research/openai-deepseek-account-introspection.md` in `$DOTFILES`, `Status:`
line at the top (`Status: research — implementation PR to follow in scripts/llm_usage.py`).
Commit on `master`, `git push origin master`. TL;DR first: for each provider, the
three lines "which account", "how much left", "where to top up / reset" and whether
each is achievable read-only today. Keep it under ~350 lines; raw samples in appendices.

Also drop the raw run output to the operator vault:
`$NOTES/<project>/driver/agent-runs/2026-09-25/<HHMM>_openai-deepseek-introspection-output.md`
(`$NOTES=/home/gud1/sync/Vault`) with YAML front-matter `model`, `cost_usd`, `branch`,
`landed_in`.

## When blocked

If an endpoint 401/403s or a doc is unreachable, record the exact status and move on.
Do not ask the operator questions mid-run; collect them in "Open questions".

## Cost guidance

Target ~$6. Stop at $12 with what you have, written up.
