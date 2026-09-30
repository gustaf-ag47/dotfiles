# OpenAI and Anthropic usage surfaces

**Checked:** 2026-09-30

## Executive summary

There are three different kinds of information, and they should not be conflated:

1. **Account-specific quota:** private, authenticated, and currently available to `llm-usage` through the Codex `wham/usage` endpoint and Anthropic OAuth usage headers/proxy state.
2. **Account-specific billing/reset offers:** visible in ChatGPT/Claude settings, but not fully exposed by the machine-readable endpoints we currently use. These require an interactive authenticated browser or manual confirmation.
3. **Plan/model changes:** public vendor documentation and news feeds. These can be safely scraped and surfaced separately as `llm-news`; they should not automatically change routing or quota calculations.

## OpenAI / ChatGPT Codex

### Public policy and help pages

OpenAI documents the following distinctions:

- A **banked reset** is a one-time saved Codex limit reset. It refreshes the 5-hour and weekly windows when used, is consumed only when it successfully resets a window, and can expire. It is not API credit or a permanent plan increase. Eligibility and expiry are account/offer-specific.
  Source: https://help.openai.com/en/articles/20001498-how-banked-codex-resets-work
- A **purchased instant reset** immediately restores the 5-hour and weekly allowance, cannot be banked, and changes the subsequent weekly reset schedule. It is distinct from both a banked reset and usage credits. Availability varies by plan, account, and billing country.
  Source: https://help.openai.com/en/articles/20001507-paid-weekly-work-and-codex-rate-limit-resets
- **Usage credits** are a separate pay-as-you-go balance for supported features after included plan usage. They are not API credits, and the balance can go negative if concurrent work completes after the balance is depleted. Settings > Usage / Codex Usage & Billing is the authoritative UI.
  Source: https://help.openai.com/en/articles/12642688-using-credits-for-flexible-usage-in-chatgpt-personal-plans
- The desktop Usage & Billing view can show monthly limit, used/remaining allowance, reset information, usage history, models, and surfaces. It may show percentages rather than exact values and has reporting delay.
  Source: https://help.openai.com/en/articles/20001478-reviewing-work-and-codex-usage-and-using-personal-analytics-in-chatgpt-desktop

### What our endpoint already provides

The authenticated `https://chatgpt.com/backend-api/wham/usage` response gives us useful account data without refreshing OAuth:

- primary/secondary rate windows and reset timestamps;
- `allowed` and `limit_reached`;
- model availability and `available_at`;
- credit balance and flags (`has_credits`, `unlimited`, `overage_limit_reached`);
- available reset count (`rate_limit_reset_credits.available_count`).

It does **not** reliably expose:

- banked-reset expiration;
- whether an instant-reset purchase is currently offered, its price, or eligibility;
- complete billing history or recent usage transactions;
- all settings-page monthly/feature breakdowns.

Recommendation: rename/display `reset_credits` as **available reset count**, not as a generic credit balance. Keep it alongside the credit balance and mark the source as a private/undocumented endpoint. Do not infer reset expiry or purchase eligibility from its presence.

## Anthropic / Claude

Anthropic documents that Claude and Claude Code share usage limits across Claude surfaces, and that Pro/Max users may wait for reset, upgrade, or enable usage credits. Usage credits are separate from the subscription allocation and are billed at API rates when enabled.

Sources:

- https://support.anthropic.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan
- https://support.anthropic.com/en/articles/11647753-understanding-usage-and-length-limits
- https://support.anthropic.com/en/articles/12005970-extra-usage-for-claude-for-work-team-and-enterprise-plans

The public pages do not provide a supported account API for a personal Pro/Max user's remaining credit balance, reset offer, or one-time reset eligibility. Our current OAuth usage headers and proxy observations are therefore the best available non-browser signal for 5-hour, 7-day, model/bucket, and cooldown state. They should remain explicitly labelled as header observations when the OAuth quota endpoint is unavailable or scope-denied.

The Claude Console usage/reporting APIs are for API/Console or organizational reporting and should not be treated as personal Claude subscription quota. They may be useful only if we intentionally add a separate Console account adapter.

Sources:

- https://support.anthropic.com/en/articles/9534590-cost-and-usage-reporting-in-console
- https://docs.anthropic.com/en/release-notes/api

## Public news/release monitoring

Useful first-party surfaces:

- OpenAI News: https://openai.com/news/
- OpenAI API changelog: https://platform.openai.com/docs/changelog
- Anthropic Newsroom: https://www.anthropic.com/news
- Anthropic Platform release notes: https://docs.anthropic.com/en/release-notes/api

The vendor RSS URLs sometimes cited for OpenAI (`/news/rss.xml`, `/blog/rss.xml`) and a guessed Anthropic `/news/rss.xml` returned HTTP 403 or no extractable feed from this host. A scraper should therefore use the official HTML listing pages and release-note pages as the primary source, with conditional requests and a conservative interval, rather than depend on RSS.

A news item should be classified by keywords before being shown:

- `quota`: limit, usage, rate limit, reset, credits, overage, plan;
- `model`: launch, deprecation, retirement, availability, model name;
- `billing`: price, credit, wallet, auto-reload, refund;
- `routing`: model availability or compatibility changes relevant to `routes.json`.

News must be informational by default. A model retirement can generate a warning, but must not rewrite routes automatically.

## Proposed implementation

Add a read-only `bin/llm-news` and `scripts/llm_news.py`:

- fetch the four official HTML/Markdown surfaces above every 6–12 hours;
- store a 0600 cache under `$XDG_CACHE_HOME/llm-usage/news.json`;
- use URL + title + published date/content hash as the item identity;
- retain only a bounded number of items and the last-fetch/error metadata;
- support `--refresh`, `--json`, `--since`, and `--provider`;
- show only new/high-confidence quota, billing, model, and routing items in `llm-usage --news`;
- never send auth headers, read `auth.json`, refresh tokens, or use browser cookies;
- make HTTP 403/429 and parser failures visible as stale/unavailable rather than silently deleting the feed.

For account-specific missing fields, add an optional separate browser adapter later:

- use an already authenticated, user-approved Chromium CDP session;
- read-only navigate to ChatGPT Settings > Usage and Claude account usage pages;
- extract visible reset expiry/offer/credit fields;
- cache only redacted values and page timestamp;
- never automate checkout, reset confirmation, or account mutation.

This browser adapter should remain opt-in and separate from the daemon/proxy. It is the only realistic route to OpenAI banked-reset expiry and purchase-offer details unless OpenAI adds a supported endpoint.
