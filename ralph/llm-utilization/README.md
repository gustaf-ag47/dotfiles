# Ralph loop: LLM utilization optimization

This loop turns the reviewed LLM utilization spec into an evidence-backed implementation plan, then can build one dependency-ready task per fresh Pi process.

## Review order

1. Read `specs/llm-utilization.md`.
2. Run PLAN once: `./loop.sh plan`.
3. Review `IMPLEMENTATION_PLAN.md` and adjust it manually if needed.
4. Only after approving the plan, run BUILD: `./loop.sh build`.

## Commands

```bash
./loop.sh plan
./loop.sh build
./loop.sh status
```

`PLAN` is one run and never implements code. `BUILD` is gated by `BUILD_APPROVED=1` and repeatedly runs one task per fresh Pi invocation until every nonempty checklist task and the final verification task are checked.

## Safety

The loop waits for the selected provider with `llm-wait`, sets `RALPH_CLASS=build` and exports `PI_LLM_CLASS=build`, uses an explicit qualified model, and never silently falls back to separately billed OpenAI API access. It never pushes. Account purchases, resets, reloads, plan changes, and browser mutations are prohibited.

## State and logs

- Plan: `IMPLEMENTATION_PLAN.md`
- Prompts: `PROMPT_PLAN.md`, `PROMPT_BUILD.md`
- Logs: `logs/`
- Lock: `.lock`

The working tree may contain unrelated pre-existing changes. Each task must stage only its own files.
