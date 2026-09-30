You are the PLAN phase of the Ralph loop for LLM utilization optimization.

Read `ralph/llm-utilization/specs/llm-utilization.md` completely, then inspect the actual repository, tests, recent commits, current git status, existing local tickets under `.scratch/llm-utilization/issues/`, proxy/Pi architecture, and project guidance. Do not implement code, run account mutations, push, or commit.

Produce `ralph/llm-utilization/IMPLEMENTATION_PLAN.md` as an evidence-grounded dependency-aware plan. Replace its placeholder completely. Use exactly `- [ ] ID: title` or `- [x] ID: title` for top-level tasks; use ordinary bullets for details. Include:

- stable task IDs and dependency order;
- paths/modules owned by each task;
- end-to-end acceptance criteria;
- exact verification commands;
- evidence required to mark each task complete;
- an exhaustive mapping from every relevant spec requirement and local ticket to tasks;
- a final verification task covering both hosts without copying credentials;
- separate operator-only rollout instructions;
- recognition of already committed work, but require fresh verification rather than trusting commit messages.

Prefer narrow tracer-bullet vertical slices. Keep account mutations out of scope. Do not alter files other than `ralph/llm-utilization/IMPLEMENTATION_PLAN.md`.
