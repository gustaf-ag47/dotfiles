# Testing

This directory contains tests for the dotfiles system.

```
tests/
├── e2e/                    # Opt-in live tests (real inference/browsers; never run in CI)
├── unit/                   # Python + Node unit tests (offline, CI-gated)
├── bootstrap-kit.sh        # age bootstrap kit round-trip (CI bootstrap-kit job)
├── bootstrap-preflight.sh  # bootstrap kit preconditions
├── install-assertions.sh   # post-install state assertions (CI install job)
└── idempotency.sh          # re-run safety + non-destructiveness (CI install job)
```

## Unit tests

Offline; no services, credentials or network. CI gates on both suites
(`.github/workflows/dotfiles.yml`, `unit` job).

```bash
make test-unit    # Python: unittest discovery over tests/unit/test_*.py
make test-node    # Node:   node --test over tests/unit/*.mjs (node >= 22.6)
make test         # both

# Single module
python3 -m unittest tests.unit.test_llm_usage -v
node --test --experimental-strip-types tests/unit/test_anthropic_pool.mjs
```

Naming: `tests/unit/test_<script-name-with-underscores>.py` / `.mjs`.

Conventions:
- Scripts in `bin/` have no `.py` extension; load them with `SourceFileLoader`
  (see `test_claude_token_proxy.py` for the pattern).
- Modules that load `bin/claude-token-proxy` must keep its cache writes inside
  a redirected `XDG_CACHE_HOME`; `test_proxy_isolation.py` discovers and
  re-runs every such module to enforce this.
- Node tests that depend on class routing must save/restore `PI_LLM_CLASS` —
  agent shells export it (`make test-node` strips it for the whole run).

## Install tests

```bash
make test-install   # real installer + assertions + idempotency in an Arch container
make test-bootstrap # bootstrap kit round-trip (needs `age`)
```

Same commands as the CI `install` and `bootstrap-kit` jobs, so a CI failure
reproduces locally.

## E2E (opt-in, paid/live)

`tests/e2e/` holds tests that drive real models or browsers. Each one is
documented where its feature lives (e.g. `jev-ultrafast-fixture.py` in
`docs/jev-ultrafast.md`) and requires explicit CLI opt-in flags. CI never runs
them.
