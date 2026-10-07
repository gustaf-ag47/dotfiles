# Paperless Claude OAuth shape — implementation notes

Repository guidance was read in full from `CLAUDE.md`: follow the unit test and
lint gates, keep scripts/test coverage, and do not edit live system files. No
`AGENTS.md` exists in this checkout. `DELEGATE_BRIEF.md` defines the task and
explicitly distinguishes source changes from the untracked paperless stack.

The checkout began at `origin/master`; the three proxy hotfixes were added as
commits `6f4a8dc`, `6c9e62b`, and `cf5d2dc`. The live proxy executable resolves
to the operator's main checkout, which was not modified. Changes here are not
deployed until copied/installed by the operator.

## Implemented

`bin/claude-token-proxy` now normalizes identity-free Messages requests into the
Claude Code subscription shape: system is only the identity, while original
system text is prepended to the first user message. Image-only content blocks
are preserved by inserting a separate user message. Requests already containing
the identity remain byte-for-byte unchanged. This preserves existing behavior
for real Claude Code and Pi clients.

Added `documents` routing class (Opus, then Sonnet; no Fable) and added
LiteLLM `extra_headers` for stable session `paperless`, class `documents`,
`fallback: none`, and explicit shape opt-in. The external paperless stack config
was backed up as `litellm.yaml.bak-20261007` before editing.

## Evidence and remaining verification

`python3 -m unittest discover -s tests/unit -t tests/unit`: passed (350 tests,
1 skipped). Docker showed the paperless services running, but they were not
restarted and no document was submitted. Therefore there is no end-to-end
Anthropic response/log or document metadata proof yet. The live proxy must first
receive this proxy code and class file; then restart LiteLLM/paperless-gpt and
run a safe existing test document. The current deployed proxy was deliberately
not copied or restarted because doing so would target the operator's main
checkout and interrupt active agents.

`ai-pipeline.py` contains bounded delayed retries via `ai-retry-wait`; LiteLLM
has `num_retries: 0`. This should prevent request retry amplification, though a
live 429/503 exercise remains outstanding.
