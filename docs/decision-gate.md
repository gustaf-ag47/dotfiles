# decision-gate: a cheap, typed decision layer

decision-gate answers short typed questions ("what kind of document is
this?", "is this a financial record?") with calibrated probabilities, fast
and cheap, so callers only escalate the unsure cases to an expensive model
(Opus) or a human. It is **not** a classifier pilot like [Jev](jev-pi.md) --
it's the shared service other pipelines are built against, and it can use
Jev as one of its two backends.

## What runs

- `bin/decision-gate`: the HTTP service (`scripts/decision_gate/{core,backends,service}.py`).
  Python stdlib only, no third-party dependencies. Binds `127.0.0.1:8796`.
- `config/decision-gate/decision_gate_client.py`: a single-file, stdlib-only
  Python client. Copy it into any project, or `import` it directly -- it has
  no dependency on the rest of this repo.
- `bin/decide`: a CLI for manual calls (`decide ask`, `decide outcome`,
  `decide report`, `decide health`).
- systemd user unit `decision-gate.service`, installed by `make install` like
  the other units in `config/systemd/user/`; enabled per-host in
  `system/hosts/<host>/user-services` (see `system/README.md`).

## Contract (v1 -- do not change without bumping the version)

`POST /v1/decide`
```json
{"purpose": "finance-attachment-kind", "sensitivity": "private|internal|public",
 "state": "<string or JSON>",
 "questions": [{"id": "kind", "kind": "choice", "prompt": "What kind of document is this?",
                "options": ["receipt","invoice","order_confirmation","credit_note","statement","marketing","terms","other"]},
               {"id": "financial", "kind": "bool", "prompt": "Is this a financial record?"}]}
```
&rarr;
```json
{"decision_id": "dg_...", "backend": "jev|ollama", "latency_ms": 212, "cached": false,
 "answers": {"kind": {"choice": "receipt", "p": 0.94, "probs": {"receipt": 0.94, "invoice": 0.04, "...": 0.02}, "abstained": false},
             "financial": {"choice": true, "p": 0.99, "probs": {"true": 0.99, "false": 0.01}, "abstained": false}}}
```
Question `kind` is `choice` (2-32 unique string options) or `bool`. Up to 16
questions per request. `choice` answers carry a `choice` string; `bool`
answers carry a native JSON boolean.

`POST /v1/outcome`: `{"decision_id": "...", "truth": {"kind": "invoice"}, "source": "opus|human|agent"}`.
Records what actually happened, for shadow evaluation. Best-effort from the
caller's point of view -- the client library never raises on a failed
outcome post unless `strict=True`.

`GET /v1/report?purpose=...`: per purpose `n`, `abstain_rate`, `agreement`
(answered-only), and `coverage`/`precision` at thresholds 0.8/0.9/0.95, both
overall and broken down `by_question`. Omit `purpose` to get every purpose.
CLI: `decide report [--purpose X]`.

`GET /healthz`: `{"status": "ok", "version": "v1"}`.

## Backends and policy

- **jev**: direct HTTP to TypeSafe System One (`POST https://api.typesafe.ai/v1/systemone`),
  the same provider the [Jev pilot](jev-pi.md) uses, called directly from
  Python rather than through Pi. `choice` questions map to TypeSafe's wire
  `choice` type; `bool` questions map to TypeSafe's `noul` type (response
  field is `{"type": "noul", "noul": <p_true>}`, verified live
  2026-10-07 -- `docs.typesafe.ai/api.md` alone implied a `probability` field
  name that the real response does not use). Default timeout 3s.
- **ollama**: local `http://127.0.0.1:11434/api/chat`, one call per question,
  `logprobs: true`, `num_predict: 1`, options mapped to single letters
  (A/B/C...), the answer's probability distribution is a softmax over the
  option letters' logprobs from the single generated token. Verified live on
  Ollama 0.35.1 with `qwen2.5vl:7b` (2026-10-07). **`top_logprobs` must stay
  <= 20** -- Ollama 0.35.1 returns `400 {"error":"top_logprobs must be
  between 0 and 20"}` above that, found during live smoke testing. Default
  timeout 8s, `keep_alive: 30s` (the GPU is shared with other local
  inference workloads, so the model isn't pinned in VRAM between calls).

Policy file: `~/.config/decision-gate/policy.json` (0600, **not in git**; see
the shipped example at `config/decision-gate/policy.example.json`). Per
purpose: `backend`, `allow_external`, `allowed_sensitivity`, `min_p`,
`cache_ttl_s`, `daily_call_cap`. A purpose not listed falls back to
`default`. A policy file that fails to parse or validate makes every call
abstain (never silently falls back to defaults).

**Hard rule, enforced in code (`core.enforce_privacy`), not just
documented**: `sensitivity: "private"` never reaches `jev` unless that
purpose's policy entry explicitly sets `"allow_external": true`. If the
resolved policy would otherwise route a private call to jev, decision-gate
reroutes it to ollama instead (`overridden_for_privacy: true` in the ledger)
rather than abstaining -- it stays usable, it just never sends private state
externally. Everything `private` defaults to `ollama`.

`allowed_sensitivity` is a separate, purpose-level allowlist: if the
request's sensitivity isn't in it, the call abstains outright (reason
`sensitivity_not_allowed`) rather than silently rerouting.

### Adding a purpose

1. Add an entry under `"purposes"` in `~/.config/decision-gate/policy.json`
   (see `policy.example.json`). Pick `backend` (ollama for anything that
   might be sensitive and doesn't need jev's accuracy; jev only for
   `internal`/`public` data, or `private` with `allow_external: true` after
   you've actually decided that's acceptable), `min_p`, and `daily_call_cap`.
2. Call `/v1/decide` from your pipeline. Treat every `abstained: true`
   exactly like a cache miss: fall through to the expensive model or a
   human.
3. Record what actually happened with `/v1/outcome` whenever you find out
   (from the expensive model's own answer, a human correction, or another
   agent's confirmation).
4. Watch `decide report --purpose <name>` (or `GET /v1/report`). **Promote a
   purpose from shadow to live (i.e. start skipping the expensive model on
   confident answers) only after >= 200 shadow outcomes with >= 95%
   precision at the threshold you chose, and zero high-cost misses** (a
   "high-cost miss" is a confident-and-wrong answer whose downstream cost of
   being wrong is expensive -- e.g. silently discarding something that
   mattered). This is a human judgment call per purpose, not something
   decision-gate enforces automatically.

## Caching, budget, ledger

- Cache key: `sha256(purpose + state + questions + "{backend}:{model}")`.
  Changing the backend or its model invalidates the cache automatically. TTL
  is per-purpose (`cache_ttl_s`).
- Budget: `daily_call_cap` per purpose per UTC day, counted against actual
  dispatched backend calls (cache hits don't count). Exhausted budget
  abstains (reason `budget_exhausted`) rather than silently queuing or
  erroring.
- Abstain triggers: backend timeout, backend error, budget exhausted, policy
  invalid/unreadable, sensitivity not allowed for the purpose, or the top
  probability for a question falling below that purpose's `min_p`. An
  abstained answer always has `"choice": null, "p": 0.0, "probs": {}`.
- Ledger: `~/.local/state/decision-gate/events.jsonl`, one JSON object per
  `decide`/`outcome` call, **metadata only** -- purpose, sensitivity,
  backend, model, latency, cached/abstained flags, token counts, estimated
  cost, `overridden_for_privacy`. It never contains `state`, prompts,
  options, or answer text. `bin/llm-usage` reads this ledger (alongside
  Jev's own, separate ledger) and prints a "decision-gate activity" section
  with per-purpose/per-backend counts and estimated cost; see
  `scripts/llm_usage.py`'s `decision_gate_activity()`/`decision_gate_lines()`.
- Decisions and outcomes themselves (needed to compute `/v1/report`) live in
  `~/.local/state/decision-gate/store.sqlite3` (0600): structured
  `{choice, p, probs, abstained}` per question, never the raw `state` text
  that was classified.

## Running it

```sh
cd "$DOTFILES"
make install                      # symlinks bin/decision-gate, bin/decide, the systemd unit
cp config/decision-gate/policy.example.json ~/.config/decision-gate/policy.json
chmod 600 ~/.config/decision-gate/policy.json   # edit purposes for your pipelines
systemctl --user daemon-reload
systemctl --user enable --now decision-gate.service   # or add it to your host's user-services list first
curl 127.0.0.1:8796/healthz
decide ask --purpose example-document-kind --sensitivity internal \
  --state "Thanks for your order, total $24.99" \
  --question 'kind:choice:What kind of document is this?:receipt,invoice,marketing' \
  --question 'financial:bool:Is this a financial record?'
decide report --purpose example-document-kind
```

The jev backend needs `~/.config/jev/api-key` (0600; shared with the Jev
pilot, see [docs/jev-pi.md](jev-pi.md)) -- it is never printed, logged, or
passed as an argument. The ollama backend needs a local Ollama server
reachable at `127.0.0.1:11434` with a chat-capable model pulled (the default
`qwen2.5vl:7b`, or override `backends.OLLAMA_MODEL`/the env equivalent if a
smaller text-only model is installed instead).

## Verification on this host (2026-10-07)

- 500/500 local Python unit tests pass (`python3 -m unittest discover -s
  tests/unit -t tests/unit`), including 60 new decision-gate tests (core
  logic with fakes, HTTP service routing/policy/privacy/cache/budget with
  fake backends over real loopback HTTP, the vendorable client's fail-open
  behavior, and the new `llm-usage` ledger section) and the pre-existing Jev
  suite unchanged.
- Live smoke, jev backend: a `choice` question ("what kind of software
  task?" on a variable-rename description) returned `mechanical` at
  `p=1.0`; a `bool` question ("is this trivial?") returned `true` at
  `p=0.88`. This is what caught the real wire field name for `noul`
  answers (`noul`, not `probability`) -- fixed in `backends.py` after
  reproducing the raw TypeSafe response directly.
- Live smoke, ollama backend: a multi-question request (`choice` + `bool`)
  against `qwen2.5vl:7b` returned `order_confirmation` at `p=0.90` and
  `financial: true` at `p=0.99` for a synthetic order-confirmation text, both
  plausible. This caught Ollama 0.35.1's `top_logprobs <= 20` ceiling (fixed
  in `backends.py`).
- Verified end-to-end over real loopback HTTP: cache hit on a repeated
  request, the hard privacy override (private + jev-configured purpose
  without `allow_external` reroutes to ollama), `sensitivity_not_allowed`
  abstention, `/v1/outcome` recording, `/v1/report` aggregation, and that the
  ledger file contains only the documented metadata fields (no `state` or
  `answers` keys).
- Not yet done: `decision-gate.service` is not yet installed/enabled on
  skrubben in this working tree (it only ran as a bare `python3 -m` process
  during the smoke test above); see the open items below.
