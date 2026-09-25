---
name: ralph-loop
description: Generate a Ralph PLAN/BUILD loop from an idea or specification. Use when asked to prepare a Ralph loop, scaffold autonomous implementation, or replan an existing loop. Clarify decisions one question at a time, generate reviewable specs and prompts, and launch only the explicitly authorized mode.
---

# Ralph loop

## Clarify

Read repository guidance, current git status, existing Ralph runners, architecture docs, and relevant implementation before choosing paths or commands. Treat previous conversation decisions as answered questions.

Ask exactly one clarification per message. Offer a recommendation and wait for the answer. Resolve only consequential gaps: outcome and acceptance criteria, module/deployment boundaries, integration and failure policies, pilot/rollout, repository scope, commit/push/draft-PR authority, deployment authority, completion behavior, and whether to launch PLAN or BUILD. Record unresolved choices as proposals for review rather than inventing approval.

## Generate the review bundle

Use `ralph/<initiative>/` unless the user selects another location. Preserve other lanes. Produce:

- `specs/*.md`: business outcomes, vocabulary, responsibilities, contracts, policy, invariants, failure behavior, acceptance scenarios, rollout, and explicit non-goals. Separate confirmed choices from proposed defaults. Map cross-repository work and permissions explicitly.
- `PROMPT_PLAN.md`: inspect every spec against actual code and tests; create an evidence-grounded `IMPLEMENTATION_PLAN.md`. Planning edits only that plan; no implementation, commits, push, or deployment. Every task needs a stable ID, dependency order, paths, acceptance criteria, exact verification commands, and evidence requirements. Include an exhaustive spec-to-task map and a final verification task. Existing code is not evidence of passing acceptance tests.
- `IMPLEMENTATION_PLAN.md`: initially a pending-plan placeholder, replaced by PLAN. Use exactly `- [ ] ID: title` and `- [x] ID: title` for top-level tasks; use non-checkbox bullets for details. Blocked work stays unchecked. Separate implementation tasks from operator rollout instructions.
- `PROMPT_BUILD.md`: take one dependency-ready task, write a failing test, implement the smallest change, run repository-required checks, record evidence, then check it off. Discover discrepancies by inspecting code, not trusting the plan. Keep failed/blocked tasks unchecked. Only perform git/network/deployment actions explicitly authorized by the user. One completed task per fresh pi invocation.
- `loop.sh`: a small Bash driver selecting PLAN or BUILD prompts and feeding them to a fresh `pi` process through stdin with `-p --no-session`. Use plain `pi` for every provider with a configurable qualified `--model provider/model` for each PLAN or BUILD invocation. Anthropic uses the globally installed local proxy integration, ChatGPT subscription access uses `openai-codex`, and DeepSeek uses `deepseek`. Separately billed `openai` API access is outside this operator's approved setup; never silently fall back to it. Use lowercase pi tool names; restrict PLAN to `read,grep,find,ls,write,edit`. Pi has no permission sandbox; never pass Claude CLI-only flags such as `--dangerously-skip-permissions` or `--output-format`. PLAN runs once and exits for review. BUILD repeatedly runs one task until the entire nonempty checklist plus final verification is complete. Include single-run locking, signal handling, logs, failure status, configurable per-iteration timeout, and an explicit BUILD approval gate. Never interpret a missing, empty, malformed, or blocked checklist as success. Preserve operator interruption even when the requested automatic stop is completion only.
- `README.md`: review order, exact PLAN/BUILD commands, stop/resume behavior, permissions, log paths, branch/PR flow, and known limitations.

Reuse a compatible existing runner. If its semantics conflict with the requested lifecycle, explain why a separate small driver is needed rather than silently modifying active loops. Keep policy in prompts/specs rather than embedding business decisions in Bash. Respect repository no-comments rules.

## Validate and launch

Read installed Pi CLI docs and check `pi --help` before selecting flags. Require an explicit qualified model in a reproducible loop configuration so changing interactive defaults cannot silently change a lane's provider or billing. Run Bash syntax validation and isolated fake-agent smoke tests for PLAN, BUILD gate, incomplete and malformed plans, task completion, process failure, locking, provider-to-executable routing, explicit model forwarding, tool restrictions, and rejection of invalid provider/model configuration. Put fake `claude`, `pi`, and `pi-claude-sub` binaries ahead of PATH so a regression cannot accidentally invoke a real agent. Tests must not invoke a real BUILD agent or push. Validate skill frontmatter and paths when changing this skill.

Launch only the mode the user authorized. For PLAN, inspect its resulting checklist for spec coverage, concrete paths, feasible checks, cross-repository gates, and preservation of prior decisions. Correct omissions or rerun PLAN as necessary; disclose remaining uncertainties. Do not quietly launch BUILD after PLAN.

Return links to the specs, generated plan, loop, and BUILD prompt, plus actual process status and validation results. Ask for review before BUILD. Installing a global skill does not mean the currently running pi session has rediscovered it; a new session discovers it, or load its path explicitly.
