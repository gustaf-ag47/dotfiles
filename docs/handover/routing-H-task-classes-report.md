# Routing H — task classes and per-entry defaults

Implemented on `feat/routing-h-task-classes`. Task classes are in `config/llm-proxy/classes.json`; `CC_PROXY_CLASSES` overrides the path. The proxy reloads by mtime and retains its last valid table on read/parse errors. Class routing is separate from unchanged `?model=` routing. `/_route?class=` ranks configured class entries, includes `class`, observes `current=`, and prefers routable DeepSeek for `mechanical`; other classes select the highest-pressure eligible non-DeepSeek candidate. Per-class Anthropic ceilings are enforced in `pick()` and represented as `class ceiling` in rankings. Explicit escalation lifts one step (`mechanical → research → build → interactive`) and logs an `escalate` route event; per-request class events include class/model/session, never tokens.

`anthropic-pool.ts` sends class and optional escalation headers for Anthropic only. `delegate.sh --class` defaults to build, selects the oracle's preferred model unless `--model` is explicit, and exports `PI_LLM_CLASS`; repo and live installed copies match. Ralph guidance configures `RALPH_CLASS`/`PI_LLM_CLASS`; the DeepSeek guide directs cheap delegated work to `--class mechanical`.

## Verification

- `python3 -m unittest tests.unit.test_proxy_task_classes tests.unit.test_claude_token_proxy tests.unit.test_proxy_cross_provider` — PASS (87 tests).
- `node --test --experimental-strip-types tests/unit/test_anthropic_pool.mjs tests/unit/test_llm_failover.mjs` — PASS (35 tests).
- `make test-unit` — PASS (135 tests, one existing skipped provider integration).
- `python3 -m py_compile bin/claude-token-proxy`, Bash syntax, ShellCheck for delegate script, and `git diff --check` — PASS.

Second instance ran on port 8790 with `XDG_CACHE_HOME` isolated and `CCTOKEN_FILE=$HOME/cctoken`; no service on 8788 was used. Live oracle results at check time:

```text
build preferred: openai-codex/gpt-6-sol (routable)
  anthropic/claude-sonnet-5: routable
  anthropic/claude-opus-5-5: routable
  openai-codex/gpt-6-luna: routable
  openai-codex/gpt-6-sol: routable
  deepseek/deepseek-v4-pro: unavailable
mechanical preferred: openai-codex/gpt-6-luna (routable)
  deepseek/deepseek-flash: unavailable
  anthropic/claude-haiku-4-5: routable
  openai-codex/gpt-6-luna: routable
```

DeepSeek was unavailable according to its live balance state, so mechanical correctly fell through to the highest-pressure eligible subscription candidate. Live inference checks:

```text
POST /v1/messages; x-cc-proxy-class: mechanical; claude-haiku-4-5; max_tokens=1
HTTP 200; response text "OK"; output_tokens=1

POST /v1/messages; x-cc-proxy-class: build; claude-fable-5-1; max_tokens=1
HTTP 503; class build may not use claude-fable-5-1
```

The first attempt without required `anthropic-version` returned HTTP 400 without inference; the successful retry included the header. The blocked fable request was rejected before forwarding; no quota was spent on it. The successful haiku check used one output token.

## P4 weekly measurement recipe

For delegate/loop work, sum `input_tokens + output_tokens` in `usage.json` `by_model`, limiting the numerator to opus/fable model keys and the denominator to all delegate/loop model keys. Use class route events (`kind=class`, carrying class/model/session) to identify non-interactive work and exclude `interactive` sessions; count each session/model usage interval once to avoid counting repeated class events. Compute `100 × opus/fable delegate+loop tokens / all delegate+loop tokens`. The target is `<10%`. If weekly telemetry does not retain per-session token attribution, usage totals cannot be accurately joined to class events; retain per-session usage attribution in the weekly report implementation rather than inferring it from aggregate model totals.
