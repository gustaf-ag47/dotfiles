# OpenAI (ChatGPT/Codex OAuth) and DeepSeek account introspection

Status: decided 2026-09-25 — implement §4 as proposed; DeepSeek label order is env
`DEEPSEEK_ACCOUNT_LABEL` → `auth.json` `label` → last-4 of key. Tracked in
`docs/handover/llm-proxy-implementation.md`

Probed live 2026-09-25 ~07:50 UTC from this PC with the credentials pi already
holds in `~/.pi/agent/auth.json`. GET requests only. No token refresh, no login, no
POST. Tokens and keys were never printed. Ids are cut to their first 6 characters.
The phone number returned by `/backend-api/me` is left out on purpose.

## TL;DR

| | Which account | How much left | Where to top up / when it resets |
|---|---|---|---|
| **openai-codex** | ✅ **Available now with no network call.** The pi `access` token is a JWT that carries `email`, `name`, `chatgpt_plan_type` and `chatgpt_account_id`. `wham/usage` also returns `email` and `plan_type`. The current adapter already fetches both and throws them away. | ✅ `wham/usage`: the weekly window, **per-model availability (`model_usage`)**, `credits.balance`, and `rate_limit_reached_type`. The "additional" per-model windows are present in the schema but were `null` for this account. | ✅ `reset_at`, `model_usage.*.available_at`, `rate_limit_upsell` (tells you whether credits would help), and `rate_limit_reset_credits.available_count`. The top-up URL is **not** in the response and has to be hard-coded (unverified, see Open questions). |
| **deepseek** | ❌ **You can't get it from an API key.** No public endpoint returns the email or name. The label has to come from local config (see §3.3). | ✅ `/user/balance`: the balance per currency and `is_available`. The documented API has **no usage history** (only the private dashboard API has it, and that needs a browser session token). | ✅ This is prepaid: nothing resets. Top up at `https://platform.deepseek.com/top_up` (URL taken from the dashboard nav, not checked live). The API returns 402 when the balance runs out. |

**Live state at probe time.** Codex (Pro plan, `gs@gustafsilver.se`) was at **100 %
of the 7-day window, `allowed:false`**, resetting 2026-09-30 14:38 UTC. `model_usage`
showed `gpt-6-astra` unavailable and `credits_would_enable: true`. DeepSeek had a
balance of **−0.12 USD, `is_available:false`**. Both limits being out explains why
this sub-agent is running on Anthropic.

Every ChatGPT endpoint below is **undocumented/internal** (`chatgpt.com/backend-api`).
The official Codex CLI calls them, so they are fairly stable in practice, but OpenAI
gives no contract for them. The DeepSeek `/user/balance` and `/models` endpoints are
documented and public.

---

## 1. OpenAI — ChatGPT/Codex OAuth

### 1.1 What pi stores (`auth.json["openai-codex"]`)

The fields are `type:"oauth"`, `access` (JWT, ~1.8 kB), `refresh` (opaque), `expires`
(ms epoch) and `accountId` (UUID, `bf7340…`). **pi does not keep an `id_token`.** pi's
login requests `id_token_add_organizations=true`, but it keeps only the access token
and gets `accountId` from the access token's `https://api.openai.com/auth` claim
(`pi-ai/dist/auth/oauth/openai-codex.js:323`,
`pi-ai/dist/api/openai-codex-responses.js:1256`). pi calls **no** account or usage
endpoint. Its only quota handling is to match `usage_limit_reached|rate_limit_exceeded`
on 429s (`openai-codex-responses.js:1233`).

### 1.2 Access-token JWT claims (local base64 decode, free, no network)

These were decoded from the real token. Values are redacted.

```jsonc
{
  "iss": "https://auth.openai.com", "aud": ["https://api.openai.com/v1"],
  "client_id": "app_EM…", "scp": ["openid","profile","email","offline_access"],
  "iat": 1789917392, "exp": 1790781392,          // ~10-day lifetime
  "https://api.openai.com/auth": {
    "chatgpt_account_id": "bf7340…",            // == auth.json accountId
    "chatgpt_plan_type": "pro",                  // free|plus|pro|team|business|enterprise|edu…
    "chatgpt_user_id": "user-9…", "chatgpt_account_user_id": "user-9…",
    "user_id": "user-9…", "poid": "org-kg…",
    "chatgpt_compute_residency": "no_con…", "amr": ["pwd","otp","mfa",…], "localhost": true
  },
  "https://api.openai.com/profile": { "email": "gs@gustafsilver.se", "email_verified": true, "name": "Gustaf Silver" },
  "https://api.openai.com/mfa": { "required": "yes" }
}
```

The official Codex CLI parses the same claim paths from its `id_token`
(`codex-rs/login/src/token_data.rs`: `IdClaims.email`, falling back to
`profile.email`, and `AuthClaims.chatgpt_plan_type`). oh-my-pi reads
`https://api.openai.com/profile.email` from the **access** token
(`can1357/oh-my-pi packages/ai/src/usage/openai-codex.ts:26,147`). **This alone
answers "which account" and "what plan" at zero cost.** The plan claim is stamped when
the token is issued, so it can be up to ~10 days stale after an upgrade or downgrade.
`wham/usage.plan_type` is the live value.

### 1.3 Endpoints (all `GET`, headers `Authorization: Bearer <access>`, `ChatGPT-Account-Id: <accountId>`)

Source for the paths is `openai/codex` @ `d7b07d4` (2026-09-25),
`codex-rs/backend-client/src/client.rs` and `client/*.rs`. Codex uses
`https://chatgpt.com/backend-api/wham/...` (ChatGPT path style) or `/api/codex/...`
(Codex API path style). `/backend-api/codex/usage` also answered with the identical
payload.

| Endpoint | Status | Answers | Codex source |
|---|---|---|---|
| `/backend-api/wham/usage` | 200 | **everything the adapter needs**: email, plan, windows, per-model availability, credits, upsell | `rate_limit_resets.rs:127` |
| `/backend-api/wham/usage` + header `x-openai-codex-luna-reserve: 1` | 200, same body here | asks the server to include the "luna reserve" limit in `additional_rate_limits` (returned `null` for this account) | `rate_limit_resets.rs:74-76` |
| `/backend-api/wham/rate-limit-reset-credits` | 200 | count and expiry of free "reset my window" credits. **Do not** call `…/consume` (POST, mutating) | `rate_limit_resets.rs:137` |
| `/backend-api/wham/usage/plan_limit_history?days=7` | 200 | previous and current weekly periods with **per-model basis-point breakdown**. Daily lag (`data_as_of` = yesterday 00:00Z), `approximate:true` | `plan_history.rs:68` |
| `/backend-api/wham/profiles/me` | 200 | `display_name`, `username`, lifetime and daily token stats | `client.rs:420` |
| `/backend-api/me` | 200 | email, name, orgs, **phone number**. Too much PII for a status bar; don't use | — (web app) |
| `/backend-api/accounts/check/v4-2023-04-27` | 200 | `plan_display_name:"Pro"`, `entitlement.renews_at/expires_at`, `billing_currency:"SEK"`, `is_delinquent`, `has_active_subscription` | — (web app) |
| `/backend-api/wham/profile` | 404 | — | — |
| `https://auth.openai.com/userinfo` | 200 **HTML** (login SPA, not OIDC JSON) | nothing | — |
| POST `…/usage/thread_usage/query_v2`, `…/thread-estimates/query` | not probed (POST) | per-thread cost. Out of scope | `task_usage.rs:99` |

Codex CLI also reads the same data **passively from response headers** on each
`/responses` call (`codex-rs/codex-api/src/rate_limits.rs`):
`x-codex-primary-used-percent`, `-window-minutes`, `-reset-at`, `x-codex-secondary-*`,
per-limit `x-codex-<limit_id>-*` + `-limit-name`, `x-codex-credits-has-credits`,
`-unlimited`, `-balance`, `x-codex-rate-limit-reached-type`, `x-codex-promo-message`.
pi doesn't expose these headers today. That makes them a possible future
"observed" source, like the Anthropic `u5/u7` header fallback. It's not needed now.

### 1.4 `wham/usage` field meanings (sample in Appendix A)

| Field | Meaning / question it answers |
|---|---|
| `email`, `plan_type`, `user_id`, `account_id` | **which account / what plan** (live) |
| `rate_limit.allowed`, `limit_reached` | whether ordinary plan usage is allowed right now |
| `rate_limit.primary_window` / `secondary_window` | `used_percent`, `limit_window_seconds` (604800 = 7d; 18000 = 5h on Plus), `reset_after_seconds`, `reset_at` (epoch s). **Pro showed only a 7-day primary; secondary was `null`.** Don't assume primary means 5h. Label the window by `limit_window_seconds`, which the renderer already does |
| `additional_rate_limits[]` | per-model/feature windows: `{limit_name, metered_feature, rate_limit:{primary_window,…}, normal_model_slug}` (Codex `client.rs:630-677`, CodexBar maps "Codex Spark" 5h/weekly). `null` here |
| `code_review_rate_limit` | separate window for code-review runs. `null` here |
| `model_usage.{slug}` | `{available, available_at (ISO), credits_would_enable}`. **This is the per-model "is X usable" answer.** Only models that are restricted appear. `gpt-6-luna` was absent while `gpt-6-astra` was blocked (see Open questions) |
| `credits` | `has_credits`, `unlimited`, `balance` (string), `overage_limit_reached`, `approx_local_messages/approx_cloud_messages` [min,max]. oh-my-pi treats "can continue on credits" as `(has_credits‖unlimited) && !overage_limit_reached` |
| `spend_control` | `reached`, `individual_limit`. Workspace spend caps |
| `rate_limit_reached_type` | `{type:"rate_limit_reached", details:"default"}`. Why it is blocked |
| `rate_limit_upsell` | `banner_type`, `title` ("You're out of Codex messages"), `ctas[].action` (`add_credits`), `reset_at`. Useful as the human verdict string |
| `rate_limit_reset_credits` | `available_count` of free window resets |

**Refresh cadence the community uses.** CodexBar polls on its menu-bar refresh
(minutes) and calls `rate-limit-reset-credits` "once per refresh". oh-my-pi caches
usage per account. Keep the existing **60 s** report cache. `plan_limit_history` only
changes daily, so it can be cached for 1 h or more.

### 1.5 OSS prior art (fetched 2026-09-25)

- **openai/codex** (primary): the endpoints above, and the `/status` rate-limit display is built from them.
- **can1357/oh-my-pi** `packages/ai/src/usage/openai-codex.ts` (33k★, pushed 2026-09-25): a pi fork with a full Codex usage adapter. It reads email from the JWT, parses `additional_rate_limits`, `credits` and `rate_limit_reset_credits`, and decides "credits fund overage".
- **steipete/CodexBar** `docs/codex.md`: uses `wham/usage` and `wham/rate-limit-reset-credits`, maps `additional_rate_limits` to named extra windows, and **never writes refreshed tokens back into a shared auth.json**. That matches our rule.
- pi extensions: `andreagrandi/pi-codex-usage`, `narumiruna/pi-extensions` (deprecated `pi-codex-usage`), and `Epsilondelta-ai/pi-web .pi/extensions/src/codex-quota.ts`. All read `wham/usage`.
- Others: `Licoy/CodexRunway`, `midhunmonachan/codex-profiles`, `f-is-h/Usage4Claude`, `MacSteini/Codex-Usage`.

(Found with `gh search code '"wham/usage"'`. GitHub code search then hit its rate
limit, so the survey stopped at that point.)

## 2. OpenAI Platform API keys (brief — no key configured today)

- **Identity.** A normal project key cannot read org or account identity. `GET /v1/models` only proves the key is valid.
- **Usage/costs.** `GET /v1/organization/usage/{completions,embeddings,…}` and `GET /v1/organization/costs` (`bucket_width=1d`, `limit` 1–180, filter by project/key/model). These **require an Admin key** (`sk-admin-…`, created at platform.openai.com/settings/organization/admin-keys). Sources: [Costs reference](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/costs), [Usage API cookbook](https://developers.openai.com/cookbook/examples/completions_usage_api), fetched 2026-09-25.
- **No balance endpoint.** Prepaid credit balance has no public API. The old `/dashboard/billing/*` routes were session-only and are deprecated.
- **Per-request limits** come back as response headers: `x-ratelimit-{limit,remaining,reset}-{requests,tokens}` and `x-ratelimit-*-project-tokens` ([rate-limits guide](https://platform.openai.com/docs/guides/rate-limits), fetched 2026-09-25).
- **Recommendation.** If a key is ever added, make it a separate `openai-api` adapter that is costs-only and needs an admin key. Don't merge it with the subscription adapter.

## 3. DeepSeek

### 3.1 Public API (documented, [api-docs.deepseek.com](https://api-docs.deepseek.com), fetched 2026-09-25)

| Endpoint | Status | Content |
|---|---|---|
| `GET /user/balance` | 200 | `is_available`, `balance_infos[{currency (CNY\|USD), total_balance, granted_balance, topped_up_balance}]`, as strings. **Can be negative** (−0.12 live). Granted balance is spent first ([pricing](https://api-docs.deepseek.com/quick_start/pricing/)) |
| `GET /models` | 200 | `deepseek-flash` (V4.1-Flash, 1M ctx), `deepseek-v4-pro`, with `context_window`, `max_output_tokens`, `effort` |
| `/user/info`, `/user/usage`, `/v1/dashboard/billing/usage` | 404 | nonexistent |
| `platform.deepseek.com/api/v0/users/current` (with API key) | 404 | — |

- **Rate limits.** There are no `x-ratelimit-*` headers. The response headers were only `x-ds-trace-id` plus CloudFront headers. Limits are **per-account concurrency** (flash 2500, v4-pro 500) and return 429 when exceeded ([rate limit](https://api-docs.deepseek.com/quick_start/rate_limit)). They can't be queried, so there is nothing to show.
- **Errors.** `402 Insufficient Balance` means "go to the Top up page" ([error codes](https://api-docs.deepseek.com/quick_start/error_codes)).
- **Pricing** is per 1M tokens and USD off-peak/peak. Peak hours are 01–04 and 06–10 UTC on weekdays. Flash costs $0.15/$0.6 off-peak (miss/out) and v4-pro $0.66/$1.98 ([pricing](https://api-docs.deepseek.com/quick_start/pricing/)).
- **Top-up.** This is done in the dashboard at platform.deepseek.com ("Top up"). The payment methods reported are card, PayPal, Alipay and WeChat, depending on region ([solcard blog, 2026-08](https://www.solcard.cc/blog/pay-deepseek-with-crypto), low trust). The minimum is reported as **$2** ([2025 blog](https://blog.dataengineerthings.org/web-scraping-for-2-day-build-a-cheap-powerful-bot-with-deepseek-v3-python-546572c97617), low trust). The official FAQ is a JS app (`static.deepseek.com/faq`) and wasn't read.

### 3.2 Private dashboard API (undocumented, needs a browser session — not recommended)

Per [steipete/CodexBar docs/deepseek.md](https://github.com/steipete/CodexBar/blob/main/docs/deepseek.md)
and [dsh-deepseek-usage](https://dsh-plugin.org/plugins/azurehalcyon/dsh-deepseek-usage),
fetched 2026-09-25:

- `GET platform.deepseek.com/api/v0/users/get_user_summary`: balance and, presumably, account identity.
- `GET …/api/v0/usage/by_api_key/amount|cost?start=&end=&tz=`, falling back to `…/usage/amount|cost?month=&year=`. These give per-key daily token and cost buckets.
- Auth is `Authorization: Bearer <platform userToken>` from the browser's `localStorage`, plus `x-client-platform: web`. **An API key cannot authenticate these endpoints.** CodexBar and the plugin both warn that they are private and may break.

**Verdict: not worth it.** It would mean pulling a session token out of Chrome
localStorage. That crosses a credential boundary, the token expires, and it goes
against the "no new secrets" posture. The one extra thing it gives us is usage history.
For burn rate, pi's own session JSONL `usage` records are a better local source.

### 3.3 Labelling convention (identity has to be local)

The key can't tell us whose account it is, so the label has to live beside the key.
Options that fit `deepseek_key()`, which already reads `auth.json["deepseek"]` with
`type`, `key` and `env`:

1. **Recommended:** add a non-secret sibling field in `auth.json`:
   `"deepseek": {"type":"api_key","key":"…","label":"gs@gustafsilver.se"}`.
   pi ignores unknown fields, but that should be checked in an implementation-PR test
   by running `pi --list-models` after adding the field. The adapter would read
   `credential.get('label')`.
2. For the env-var path, use `DEEPSEEK_ACCOUNT_LABEL`, next to `DEEPSEEK_API_KEY` in
   `local/env/.env`.
3. Fallback: show `key …<last4>`. Printing the last 4 characters of an `sk-` key is
   the common dashboard convention and doesn't leak enough to matter. Never print the
   first characters.

## 4. Proposal for `scripts/llm_usage.py`

### 4.1 `codex()` — new returned fields (all whitelisted, no raw passthrough)

```python
{'status':'ok','kind':'subscription quota',
 'account': {'email': data.get('email') or jwt_email, 'plan': data.get('plan_type') or jwt_plan,
             'account_id': (credential.get('accountId') or '')[:6]},       # prefix only
 'windows': [...],                                   # as today, plus additional_rate_limits → name=limit_name
 'allowed':…, 'limit_reached':…,
 'reached_type': (data.get('rate_limit_reached_type') or {}).get('type'),
 'models': {slug: {'available': bool, 'available_at': iso, 'credits_would_enable': bool}},
 'credits': {'balance': str, 'has_credits': bool, 'unlimited': bool, 'overage_limit_reached': bool},
 'reset_credits': int,                               # rate_limit_reset_credits.available_count
 'topup_url': 'https://chatgpt.com/codex/settings/usage'}   # hard-coded, unverified
```

- **Decode the JWT locally.** Use a helper `jwt_claims(token)` that base64-decodes the
  payload segment only (no signature check, since we only need it for display) and
  returns just `email` and `chatgpt_plan_type`. Use it (a) as a fallback when
  `wham/usage` fails, so the "unavailable" line can still name the account, and (b) in
  the expired-token branch: "OAuth for gs@… expired; log in with pi".
- Don't call `/me` (PII) or `accounts/check` (large, and `renews_at` is the only extra).
  `plan_limit_history` could be an opt-in `--detail` with a 1 h cache. It's not in the
  default path.

Mock rendering, matching the Anthropic style:

```
openai-codex
  gs@gustafsilver.se (pro)  EXHAUSTED
    7d        ░░░░░░░░░░░░░░░░░░░░   0% left   resets in 5d 06h
    gpt-6-astra unavailable until 5d 06h — credits would enable (balance 0)
    top up: https://chatgpt.com/codex/settings/usage   reset credits: 0
```

When the account is healthy, only the header line and the bars show, e.g.
`gs@gustafsilver.se (plus)  READY`. Status rules: `allowed is False` or
`limit_reached` gives EXHAUSTED. If credits can fund overage, show
`EXHAUSTED · running on credits` in yellow.

### 4.2 `deepseek()` — new fields

```python
{'status':'ok','kind':'prepaid balance','label': credential.get('label') or os.environ.get('DEEPSEEK_ACCOUNT_LABEL') or f'key …{key[-4:]}',
 'available':…, 'balances':[… as today …], 'topup_url':'https://platform.deepseek.com/top_up'}
```

```
deepseek
  gs@gustafsilver.se  EXHAUSTED
    balance -0.12 USD   UNAVAILABLE   (granted 0.00 · topped-up -0.12)
    top up: https://platform.deepseek.com/top_up
```

Optional: `/models` for a "models: deepseek-flash, deepseek-v4-pro" line. It's cheap,
documented and public, but low value, so it's not in the default path.

### 4.3 Caching and security

- JWT decode is free and runs on every invocation. `wham/usage` and `/user/balance` stay behind the existing 60 s report cache. Any opt-in `plan_limit_history` gets a separate 1 h cache.
- Keep the existing rules: no refresh, no `!cmd`, no redirects (`NoRedirect`), and error text is never echoed back. The result dict stays **whitelisted**, so `user_id` and the full `account_id` must never be copied in. Email and label are fine to print. The phone number must never be, which is one more reason to skip `/me`.
- Keep the `User-Agent: pi-llm-usage`. It worked. Codex sends `codex_cli_rs/…` + `originator`, but that isn't required.
- **Fragility flags.** Everything under `chatgpt.com/backend-api` is internal (`wham/usage` is the most stable because the Codex CLI depends on it). The `x-openai-codex-luna-reserve` header is new and undocumented. The top-up URLs are hard-coded.

## 5. Unit-test plan (`tests/unit/test_llm_usage.py`)

Fixtures should be redacted copies of Appendix A/B. Tokens must be fake JWTs built in
the test, with payload `{"https://api.openai.com/profile":{"email":"a@b"},
"https://api.openai.com/auth":{"chatgpt_plan_type":"plus","chatgpt_account_id":"abcdef-…"}}`.

1. `wham_usage_pro_exhausted.json`: primary 7d at 100, `secondary:null`, `model_usage` astra blocked, `credits.balance "0"`. Expect EXHAUSTED, the email and plan in the output, and the model line.
2. `wham_usage_plus_5h_7d.json`: two windows (18000 s and 604800 s) and `allowed:true`. Expect labels `5h`/`7d` derived from the seconds.
3. `wham_usage_additional_limits.json`: `additional_rate_limits:[{limit_name:"codex-spark",…}]`. Expect a named extra window.
4. `wham_usage_credits_overage.json`: `limit_reached:true`, `has_credits:true`, `overage_limit_reached:false`. Expect the "running on credits" variant.
5. Leak test: `user_id`, full `account_id` and `rate_limit_upsell.referral` values must be absent from `str(result)`. The output may contain only the 6-char `account_id` prefix.
6. JWT fallback: `get_json` raises `HTTPError(401)`. The result is still labelled with the email from the JWT, and `get_json` isn't retried or refreshed.
7. Expired token: the "unavailable" reason contains the JWT email, and `get_json` is not called (extends the existing test).
8. Malformed JWT (not three segments, bad base64): the email is `None` and nothing raises.
9. `deepseek_balance_negative.json` (`-0.12 USD`, `is_available:false`): expect UNAVAILABLE and the top-up URL.
10. DeepSeek label precedence: `auth.json` `label`, then `DEEPSEEK_ACCOUNT_LABEL`, then `key …last4`. The first characters of the key must never appear.

## Open questions

1. **Does `gpt-6-luna` still work while the 7-day window is at 100 %?** `model_usage` only listed `gpt-6-astra` as blocked. The `luna-reserve` header suggests luna has its own reserve, but `additional_rate_limits` was `null`. One real luna request would answer it, but that means inference, which is outside this read-only brief. This matters for the `delegate` skill's Codex→Opus fallback check.
2. What is the correct Codex **add-credits URL**? The response gives only `ctas[].action:"add_credits"`, and the guess `chatgpt.com/codex/settings/usage` hasn't been verified.
3. Does pi keep unknown fields (`label`) in `auth.json` when it rewrites the file on refresh? If it drops them, fall back to the env var.
   **Answered 2026-09-25 (pi 0.87.1, read from source, Step 1).** Yes for the `deepseek`
   entry, with one caveat:
   - Every write goes through `FileCredentialStorage.modify(provider, fn)` in
     `pi-coding-agent/dist/core/auth-storage.js:378-392`, which re-reads the file under
     a lock and writes `{ ...currentData, [provider]: next }` (line 389). Only the
     provider being modified is replaced; every other provider's object is copied
     through untouched. An OAuth refresh of `openai-codex` or `anthropic` therefore
     never touches `deepseek.label`.
   - The refresh path itself (`pi-ai/dist/auth/resolve.js:77-87` →
     `pi-ai/dist/auth/oauth/openai-codex.js:326-338` `credentialsFromToken`) rebuilds the
     **refreshed provider's** entry from scratch (`type/access/refresh/expires/accountId`),
     so extra fields on an *oauth* entry would be dropped. `deepseek` is `api_key` and is
     never refreshed, so this does not apply.
   - Caveat: `/login deepseek` (`pi-ai/dist/models.js:310-314`) replaces the whole entry
     with the freshly entered credential, so `label` must be re-added after a re-login.
   - `load()` validation (`auth-storage.js:185-193`) only checks `key`/`env` types on
     `api_key` entries; extra keys are accepted, so pi keeps starting normally.
   The adapter uses env → `auth.json` `label` → `key …<last4>` (decision #6) and renders a
   `set DEEPSEEK_ACCOUNT_LABEL (or "label" in auth.json)` hint only on the last tier.
4. Is `platform.deepseek.com/top_up` the right deep link for the operator's (non-CN) account?

## Appendix A — `GET /backend-api/wham/usage` (live, redacted)

```json
{"user_id":"user-972WKY…","account_id":"bf7340…","email":"gs@gustafsilver.se","plan_type":"pro",
 "rate_limit":{"allowed":false,"limit_reached":true,
   "primary_window":{"used_percent":100,"limit_window_seconds":604800,"reset_after_seconds":456647,"reset_at":1790779102},
   "secondary_window":null},
 "code_review_rate_limit":null,"additional_rate_limits":null,
 "model_usage":{"gpt-6-astra":{"available":false,"available_at":"2026-09-30T14:38:22.363903Z","credits_would_enable":true}},
 "credits":{"has_credits":false,"unlimited":false,"overage_limit_reached":false,"balance":"0",
            "approx_local_messages":[0,0],"approx_cloud_messages":[0,0]},
 "spend_control":{"reached":false,"individual_limit":null},
 "rate_limit_reached_type":{"type":"rate_limit_reached","details":"default"},
 "rate_limit_upsell":{"banner_type":"pro_rate_limit_reached","title":"You're out of Codex messages",
   "description":"Your rate limit resets on {time}. Add credits to continue using Codex now.",
   "ctas":[{"action":"add_credits","label":"Add Credits"}],"reset_at":1790779102,"referral":null,"request_url":null},
 "promo":null,"rate_limit_reset_credits":{"available_count":0,"applicable_available_count":0}}
```

`wham/rate-limit-reset-credits`:
`{"credits":[],"available_count":0,"total_earned_count":0,"immediate_reset_purchase_eligible":false,"history_enabled":true}`

`wham/usage/plan_limit_history?days=7` (current period, trimmed):
`{"data_as_of":"2026-09-24T00:00:00Z","approximate":true,"periods":[{"window_minutes":10080,"plan_type":"pro","starts_at":"2026-09-23T14:38:21Z","ends_at":"2026-09-30T14:38:21Z","used_basis_points":31.66,"breakdowns":[{"dimension":"model","rows":[{"key":"gpt-6-astra","basis_points":27.97},{"key":"gpt-6-luna","basis_points":3.68}]},…]},{…previous period used_basis_points 10001.02…}]}`.
Because of the daily lag, the history showed the current period as 0.3 % used while
live `wham/usage` said 100 %. **Never use history to show how much is left.**

`accounts/check/v4-2023-04-27` (useful subset): `plan_type:"pro"`,
`plan_display_name:"Pro"`, `structure:"personal"`,
`entitlement:{subscription_plan:"chatgptpro", has_active_subscription:true,
renews_at:"2026-10-10T13:17:19+00:00", billing_period:"monthly",
billing_currency:"SEK", is_delinquent:false}`.

`wham/profiles/me` (subset): `profile:{username:"gs-b055", display_name:"Gustaf Silver"}`,
`stats:{lifetime_tokens:4425384285, current_streak_days:5, daily_usage_buckets:[…]}`.

## Appendix B — DeepSeek (live)

```json
GET /user/balance → {"is_available":false,"balance_infos":[{"currency":"USD","total_balance":"-0.12","granted_balance":"0.00","topped_up_balance":"-0.12"}]}
GET /models → {"object":"list","data":[{"id":"deepseek-flash","name":"DeepSeek-V4.1-Flash","context_window":1048576,"max_output_tokens":393216,…},{"id":"deepseek-v4-pro","name":"DeepSeek-V4-Pro",…}]}
response headers: Content-Type, x-ds-trace-id, X-Cache, X-Amz-Cf-* (no rate-limit headers)
```
