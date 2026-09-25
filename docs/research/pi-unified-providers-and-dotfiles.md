# Unified Pi providers and dotfiles adoption

## Verdict

Use **plain `pi` for every provider**, with global, provider-scoped Anthropic integration. Keep the existing Claude proxy specialized; do not turn it into an OpenAI/DeepSeek protocol translator. Add a separate provider-aware usage command.

**Confirmed scope:** OpenAI means the existing ChatGPT/Codex subscription (`openai-codex`) only. Separately billed OpenAI API access is excluded. DeepSeek retains its existing API-key billing.

This is an investigation and proposed migration, not an applied configuration change. Existing dirty changes to the proxy, Waybar renderer and tests were inspected but left untouched. No inference requests, credential refresh commands, service restarts or live configuration migrations were performed.

## Verified on this PC

- Pi is `0.85.1`, installed as `@earendil-works/pi-coding-agent`; executable: `~/.local/share/npm/bin/pi`.
- `pi-claude-sub`, `claude-token-proxy`, `claude-token-refresh`, `claude-usage` and `waybar-claude-usage` already live in this repository's `bin/`.
- `config/pi/` already contains two Anthropic extensions, but `scripts/install.sh` does **not** install global Pi settings/resources.
- `~/.pi/agent/auth.json` contains `openai-codex` OAuth and a `deepseek` API key. No stored `anthropic` or ordinary `openai` credential was present. Only provider names/types were emitted during inspection.
- Anthropic OAuth credentials and `ANTHROPIC_BASE_URL` are inherited from shell startup. Pi's native Anthropic provider supports `ANTHROPIC_OAUTH_TOKEN`.
- Global settings select `anthropic/claude-fable-5`, medium thinking, hidden thinking blocks, dark theme; the Anthropic extra-usage warning is disabled.
- `models.json` overrides `openai-codex/gpt-6-astra` to a 1,100,000-token context window.
- Offline model listing exposes Anthropic, Codex and DeepSeek. This verifies configured availability, **not** current upstream inference success or billing balance.
- The local proxy was active with three valid tokens, two currently available. All three detailed quota queries had HTTP 403 and scope-denied flags. These are point-in-time observations, not permanent account properties.

## How the current system works

### Shell setup and token selection

`config/zsh/.zshenv` sources `config/claude-code/env.sh`. That helper invokes `claude-token-refresh`, prefers its cached selection, and falls back to private cache/token files. It exports the selected OAuth token and, when the service is active, the local Anthropic base URL.

Despite its name, **`claude-token-refresh` does not perform OAuth refresh-token exchange**. It selects among existing tokens in `~/cctoken`, probes them with small Haiku requests, and caches the successful token with lowest observed weekly utilization for five minutes. The cache contains a real secret and is written with mode 0600.

Consequences:

- Shell startup can trigger network requests and consume a small amount of quota, even when starting a shell for unrelated work.
- This duplicates some proxy selection/probing responsibility.
- The refresh helper expects shell-export syntax; the proxy accepts token matches more generally. Their accepted file formats are not identical.

### Claude proxy

`config/systemd/user/claude-token-proxy.service` runs a Python stdlib HTTP proxy bound to `127.0.0.1:8788`, forwarding to `api.anthropic.com`.

It:

1. Loads/reloads tokens from `~/cctoken`, retaining state for unchanged tokens.
2. Chooses an eligible account per request. Current default policy favors remaining weekly quota that expires soon, with stickiness to preserve prompt caches; it is no longer simply “most headroom” as some comments claim.
3. Distinguishes model-specific quota cooldowns from shared/account cooldowns.
4. Replaces incoming Authorization with its selected Bearer token.
5. Retries failed upstream requests across accounts for 401/403/429/529; short burst 429s get a bounded wait before failover.
6. Streams the accepted response and extracts reported token usage.
7. Exposes local `/_status` and `/_usage` documents and persists counters in `~/.cache/cc-proxy/usage.json`.
8. Polls detailed OAuth usage and periodically probes parked tokens.

Failover occurs **before forwarding an accepted response**, not by resuming a partly delivered SSE response on another account. There is no OAuth refresh-token exchange here either.

This implementation embeds Anthropic-specific quota buckets, headers, payloads, identity/probe details and SSE events. Codex OAuth/Responses and DeepSeek Chat Completions are different protocols and credential lifecycles.

Security boundary: localhost only, but no client authentication. Local processes able to connect can use the pool. A remote proxy URL would require separate authentication, TLS and endpoint validation; do not casually expose this service.

### Usage reporting

`claude-usage` executes `waybar-claude-usage | jq -r .tooltip`. The Waybar renderer fetches `/_usage`, preferring detailed account quota and falling back to response-header observations. Missing utilization is displayed as unknown, not zero.

Important distinctions:

- Quota percentages are not calculated from token counters.
- Header observations can become stale while an account is idle.
- Counters cover requests observed by this proxy, not all account activity, and include retry attempts.
- The Waybar percentage is the **maximum observed account weekly utilization**, not total pool capacity or remaining capacity on the selected account.
- Detailed-usage scope denial must not invalidate otherwise usable inference credentials.

### `pi-claude-sub`

The wrapper:

- Loads `anthropic-oauth-claude-code-identity.ts` explicitly.
- Uses the local proxy when reachable (`auto`), requires it with mode `1`, or uses direct credentials with mode `0`.
- Adds `anthropic-token-proxy.ts` in proxy mode to override Anthropic's base URL.
- Passes an OAuth-shaped placeholder via `--api-key` in proxy mode; the proxy injects the real credential.
- Defaults to `claude-opus-4-8`, unless a model flag is supplied.

The identity extension keeps the Claude Code system identity and moves Pi's harness instructions into the first message. This is an upstream-sensitive compatibility workaround, not a generic multi-provider feature.

The wrapper defaults conflict with global settings (`claude-fable-5`) and delegation defaults (`claude-opus-5`). Supplying a model also skips its explicit Anthropic provider selection, so a qualified non-Anthropic model can receive the wrong CLI credential. Current Pi binds `--api-key` to the initially selected provider; it is not a universal credential for later `/model` switches.

**Plain Pi already supports Anthropic OAuth**, but currently does not load these wrapper-only extensions. Do not assume inherited `ANTHROPIC_BASE_URL` provides identical routing: the installed Anthropic implementation explicitly supplies `model.baseUrl` to its SDK.

Billing caution: installed Pi documentation says native Claude subscription usage in third-party harnesses draws from paid extra usage. The local identity workaround attempts different behavior; this investigation does not establish current billing treatment or contractual support. Do not replace the working route with native login silently or assume subscription requests are free because estimated session cost is zero.

## Recommended unified experience

Target behavior after implementation:

```bash
pi                                             # one global default
pi --model anthropic/claude-fable-5
pi --model openai-codex/gpt-6-astra             # existing ChatGPT subscription
pi --model deepseek/deepseek-v4-pro            # existing metered API key
pi -c
pi -r
```

Within a session: `/model` switches providers; `/scoped-models` selects a small cross-provider set for cycling. Provider switching sends the conversation context to the newly selected provider; it is not just a UI change.

**`openai-codex` is ChatGPT subscription access. `openai` is separately billed OpenAI API access.** Do not alias one to the other or silently fall back between them. Ordinary `openai` can be enabled later with its own credential.

### Implementation boundaries

1. Install the Anthropic routing integration globally so plain Pi, print mode, delegates and loops all use it.
2. Make endpoint and credential selection provider-scoped. Pair the local endpoint with its placeholder through supported provider configuration/auth resolution, rather than an unconditional CLI `--api-key`. Preserve built-in model metadata/catalog refresh.
3. Scope the existing payload compatibility hook explicitly to the Anthropic route. Update old `@mariozechner` type imports to the installed `@earendil-works` namespace and test against the installed SDK.
4. Fail closed when a selected proxy route is unavailable; allow Codex/DeepSeek sessions to start without a healthy Claude proxy. Direct Anthropic should be an explicit, clearly labelled opt-in, not an unnoticed billing/routing change.
5. Keep `pi-claude-sub` temporarily as a backward-compatible launcher. Inventory existing callers and preserve documented legacy flags before simplifying it.
6. Update `delegate/scripts/delegate.sh` and relevant loop configurations to use `pi`; remove the need to override both launcher and provider. Use explicit qualified models for reproducible scripted tasks.
7. Use one normal Pi agent directory and session history. Profiles should be intentional isolation, not a provider-selection requirement.
8. No automatic cross-provider failover by default: changing provider changes pricing, capabilities and the recipient of potentially private context.

A shell alias alone is insufficient: subprocesses may bypass it, CLI precedence remains awkward, and interactive `/model` switching still needs correctly registered providers.

### Unified usage, not a universal proxy

Add `pi-usage` with text and JSON output, backed by independent adapters; optionally expose `/usage` in Pi and a matching Waybar view.

| Provider | Credential owner | Proposed reporting |
|---|---|---|
| Anthropic pool | Existing proxy/token file | Existing local `/_usage`, quota freshness, account/model cooldowns, observed counters |
| OpenAI Codex | Pi OAuth store/runtime | Subscription windows/reset times if a read-only account-usage endpoint can be verified; otherwise explicit unavailable status plus locally observed session usage |
| DeepSeek | Pi credential store | Verified read-only balance API, currency, observation time; local token/cost estimates separately |
| OpenAI API, optional | Separate API credential | Local usage estimates; account-wide billing only with suitable separately authorized reporting access |

Codex account-quota and DeepSeek balance endpoint contracts were **not live-tested in this pass**. Treat those as implementation research tasks, not established support.

The shared report should distinguish `quota`, `balance`, `observed usage`, `estimated cost`, `unknown`, `stale` and `error`. Never convert balance into a subscription percentage or imply session estimates equal provider invoices. One unavailable provider must not break the report. Readers must not race Pi's OAuth refresh or log credential-bearing responses.

## What should move into dotfiles

Keep `~/.pi/agent` a real directory. **Do not symlink the whole directory into Git or set `PI_CODING_AGENT_DIR` to the tracked source tree.** It mixes configuration, secrets and runtime state.

### Portable, first-party resources

Recommended tracked location: `config/pi/skills/`, with related extensions in `config/pi/extensions/`.

Candidates after content/dependency review:

- `browse-shop`, `co-browser`, `website-screenshot`
- `web-research`, `tcg-store-search`
- `delegate`, `deepseek`, `ralph-loop`
- `context-maps`, `event-storming`, `event-storming-process-modelling`, `event-storming-software-design`
- Shared `_excalidraw/` runtime, tests and reference examples
- `~/.pi/agent/extensions/goal.ts`

Preserve `_excalidraw` as a sibling: several diagram skills reference `../_excalidraw/WORKFLOW.md`, scripts and example images. Its approximately 5 MB is mostly intentional visual reference material, unlike installed dependencies.

The DeepSeek skill needs minor factual maintenance: its “no models means key absent from environment” advice conflicts with its own later auth-store setup. Price/model advice should not become timeless hardcoded truth.

### Private resources

Default to `$SYNC/dotfiles-local/config/pi/skills/` for:

- `betterstack-logs`, `linear`
- `<company>-prod-db`, `<company>-sandbox` (work-account skills)
- `instockachu-catalogue-verify`, `instockachu-lgtm`

These encode work/project-specific infrastructure and access workflows, even when actual passwords are read externally. That matches `docs/LOCAL_CONFIG.md`. Public versions require deliberate extraction of generic tooling from private account/host/project configuration.

A bounded credential-pattern scan of skill sources found placeholder-looking token examples, including Linear examples confirmed to be placeholders. **This was not a comprehensive security audit and does not certify the trees safe to publish.** Review screenshots, examples, embedded addresses, scripts, lockfiles and private documentation before staging.

### Third-party skills

`~/.agents/skills` already contains three independent Git clones:

| Repository directory | Inspected commit | Local changes |
|---|---|---|
| `mattpocock` | `84fdeffd12f2ee307994d1eb6feb48173b6e0502` | Clean |
| `pi-skills` | `90bb51cae36515a648515b633a81c0c6efc8c74d` | Modified browser-tools lockfile; untracked youtube-transcript lockfile |
| `vladikk-modularity` | `bcdca9a595764b9aa88d5d8d6020f52e7f5f1f52` | Clean |

Track an explicit upstream URL/commit manifest and bootstrap pinned checkouts, rather than copying their `.git` histories and dependencies into dotfiles. Preserve/review local lockfile changes first. Pi packages are suitable where their resource layout fits; do not assume arbitrary repositories have package-compatible layouts.

`Scrapling-Skill` has no `.git` directory in the inspected tree. Establish its exact upstream/version and local modifications before replacing it with a fresh pinned download. Its non-environment source is only about 288 KB.

### Dependency bulk

Measured disk usage includes approximately:

- `Scrapling-Skill`: 411 MB, mostly `.venv`.
- `web-research`: 114 MB, mostly `.venv`; source is about 15 KB.
- Third-party `pi-skills`: 156 MB, largely `node_modules`; source excluding Git/dependencies is about 159 KB.

Version source and dependency manifests/locks, not `.venv`, `node_modules`, `.git`, `__pycache__` or generated browser state. Rebuild Python environments at their final paths; copied/moved venv launchers can retain absolute interpreter paths. Existing web-research instructions explicitly expect a skill-local `.venv`, so either preserve an ignored environment at that location or update its launcher and docs together.

### Settings and local state

| Resource | Recommendation |
|---|---|
| `settings.json` | Track a reviewed bootstrap template; seed only when absent, explicitly merge managed resource paths for existing installations |
| `models.json` | Track reviewed non-secret model overrides; per-file link is reasonable |
| `extensions/goal.ts` | Track and link this individual resource |
| `prompts/` | Currently empty; add tracked prompts when useful |
| Themes/keybindings/global context | No corresponding custom files found in the inspected agent root; do not invent a migration |
| `auth.json`, all auth backups | Keep outside public Git; protect permissions; re-login on a fresh machine or use a deliberate encrypted backup |
| `~/cctoken`, cached token env | Secrets; keep excluded, outside tracked config |
| `sessions/`, `delegate-mailbox/`, `locks/` | Machine-local runtime state; backup separately if desired |
| `trust.json` | Local trust decisions; do not propagate trust by installing dotfiles |
| `models-store.json` | Generated model catalog/cache, not curated configuration |
| `profiles/driver-day-20260907/` | One-off profile with local sessions and shared auth/resource links; retain locally unless deliberately generalized |
| `*.bak*` | Do not migrate wholesale; some contain credentials or stale private settings |

### Tested symlink behavior

A disposable test called the installed `FileSettingsStorage.withLock()` against a temporary `settings.json` symlink. The symlink survived and the target was updated. Source uses `writeFileSync`, not rename-over-target.

Thus per-file settings links work on **this version**, but they also put incidental writes such as `lastChangelogVersion`, UI preferences and package changes into Git. Prefer a bootstrap template with runtime settings local. This test does not establish behavior of external editors, future Pi versions, or other mutable stores.

## Migration sequence and acceptance tests

1. Record current executable/config/resource resolution and make private backups; do not copy auth into public staging.
2. Add ignore rules for Pi secrets/runtime/dependencies **before** importing files. Current repository ignores `cctoken`, but do not rely on generic ignores to cover `auth.json` and its backups.
3. Import reviewed first-party source; place work-specific source in the private tree; preserve third-party local changes and pin upstream versions.
4. Extend `scripts/install.sh` using its existing non-destructive `link_config` convention for **individual** resources. Keep unrelated live skills/files intact. Add private skill links alongside public ones without duplicate discovery.
5. Provide a Pi-only adoption/check path so this migration does not require replaying the entire desktop installer or restarting the active proxy.
6. In an isolated temporary agent directory, verify global routing, model visibility, settings merge/idempotence, no duplicate skill names and all sibling/reference paths. Use fake credentials and local mock servers for protocol/auth assertions.
7. Confirm Claude-only request rewriting and routing; Codex/DeepSeek retain their own credentials and endpoints. Proxy-down must not block other providers. Test `--help`, `--list-models`, qualified models, `--`, print mode, JSON/RPC, continuation/resume and compatibility launcher behavior.
8. Test Anthropic-to-Codex-to-DeepSeek and reverse session handoffs, including tool-result replay and compaction. Test `/goal` evaluator calls separately: they use the model registry directly, and an ordinary turn succeeding does not prove the evaluator route works.
9. With explicit allowance for small provider charges, run minimal live inference/usage probes. Check actual billing behavior rather than inferring it from token-shaped credentials or local cost estimates.
10. Adopt for newly launched sessions first; retain rollback links/backups. Update delegates/loops incrementally; do not rewrite existing session JSONL provider IDs.

The user confirmed that OpenAI support means only the **already configured ChatGPT/Codex subscription**. Do not implement ordinary `openai` API access or automatic fallback to it. Multi-account Codex rotation is not requested; existing Codex access plus existing DeepSeek API access is sufficient for the unified workflow.

## Sources

Repository primary sources:

- `bin/claude-token-proxy` (working-tree version), `bin/claude-token-refresh`
- `bin/pi-claude-sub`, `bin/claude-usage`, `bin/waybar-claude-usage`
- `config/pi/anthropic-token-proxy.ts`, `config/pi/anthropic-oauth-claude-code-identity.ts`
- `config/claude-code/env.sh`, `config/zsh/.zshenv`
- `config/systemd/user/claude-token-proxy.service`, `scripts/install.sh`
- `docs/LOCAL_CONFIG.md`, `docs/handover/2026-08-30_wire-pi-into-dotfiles-brief.md`

Installed Pi primary sources, under `~/.local/share/npm/lib/node_modules/@earendil-works/pi-coding-agent/`:

- `README.md`; `docs/providers.md`, `models.md`, `settings.md`, `skills.md`, `packages.md`, `custom-provider.md`
- `dist/main.js`: initial-provider scoping of CLI API keys
- `dist/core/settings-manager.js`: actual settings-write behavior
- `node_modules/@earendil-works/pi-ai/dist/providers/{anthropic,openai-codex,deepseek}.js`
- `node_modules/@earendil-works/pi-ai/dist/api/anthropic-messages.js`
- `examples/extensions/custom-provider-anthropic/index.ts`

Local source/config inspection: `~/.pi/agent/{settings.json,models.json,extensions/goal.ts}`, skill/source inventories in both discovery roots, and `delegate/scripts/delegate.sh`. Live inspection used only local proxy status/usage and offline model listing; no credential values are included here.
