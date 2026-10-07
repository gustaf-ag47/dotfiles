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

## Evidence and operations

`python3 -m unittest discover -s tests/unit -t tests/unit`: 351 passed, 1 skipped.
Pre-commit shellcheck, bash syntax, secret checks; `py_compile`; JSON parse;
rendered Compose config and `git diff --check` passed.

End-to-end verification ran without copying into or restarting the production
proxy. A temporary systemd user unit ran this branch from the worktree at
127.0.0.1:8791; a temporary gateway bridge exposed it to Paperless at
192.168.144.1:8792. LiteLLM and paperless-gpt were restarted for the test and
restored to the normal proxy port 8788 afterward. Synthetic one-page document
#1065 completed both vision OCR and Claude metadata; the output was title
“Demo Kiosk – kvitto kaffe”, Receipt, correspondent Demo Kiosk, date 2026-10-07,
and custom fields Total SEK42.00, VAT SEK8.40, purchase date, reference, and
payment method. It remains in Paperless tagged `ai-skip`; nothing was deleted.
Branch proxy journal showed `client='litellm/1.104.0' class=documents ... status
200`. A 5,986-character system prompt also returned 200. No inference 429 detail
was observed (the read-only usage endpoint did return an HTTP 429 at startup).

Back-pressure: inspected paperless-gpt v0.28.0 `llm_client.go`/`main.go`; its
retry wrapper is bounded and `LLM_MAX_RETRIES=1` is now active. LiteLLM
`num_retries: 0`; ai-pipeline parks final failures in `ai-retry-wait` for 180
minutes, at most three delayed retries. During the test a separate queued scan
#1066 exceeded Anthropic's 8,000-pixel image-side limit, exhausted its bounded
OCR attempts, and was parked in `ai-retry-wait`; current Compose now uses local
Ollama vision. No ongoing retry loop or pool cooldown resulted.

The production proxy executable still resolves to the operator's main checkout;
it was deliberately not modified or restarted, per Gustaf's explicit “for the
live test copy nothing” direction. The isolated branch test meets live E2E
without copying. Deployment of the PR to the production proxy remains an
operator-controlled follow-up; PR #30 is open, not merged.

CI passed at head `08769299f1ef34d4b95c0f3bcb566fa680df2464`; target `master`
latest run #37458990418 at `e9991c4` succeeded. PR remains OPEN/MERGEABLE, with no
review decision or merge authorization.
