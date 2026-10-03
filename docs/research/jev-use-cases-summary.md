# Jev use cases: consolidated decision record

Closeout: 2026-10-02. This reconciles the three independent research reports with
what was subsequently implemented. The original reports are research snapshots,
not the current installation status.

Sources:
- [Capabilities and limits](jev-use-cases-capabilities.md)
- [Concrete Pi workflows](jev-use-cases-workflows.md)
- [Evaluation and ROI](jev-use-cases-evaluation.md)
- [Reviewed reference implementation](jev-ten-levels-review.md)

## Decisions and current state

| Use case | Decision | Current state |
|---|---|---|
| Delegate task-class suggestion | Observe first; explicit class/model and quota gates win | Installed; `/jev`, `bin/jev-classify`, bounded delegate `--task` observation and local accounting |
| Duplicate reads | Use deterministic content hashes and context-retention checks, not a classifier | Installed in opt-in `read_context`; verified full read → compact reuse marker |
| Candidate-file triage | Useful when local search leaves ambiguity; keep uncertain candidates, protect source before upload | Installed in opt-in `scout_files`, with tracked-file, path/symlink, size, credential and binary guards; synthetic end-to-end test passed |
| Capability/model-tier routing or escalation | Requires labeled evaluation and downstream quality measurements before applying decisions | Not enabled; existing routing priorities, budgets, pins and cooldowns are unchanged |
| Goal-completion precheck / loop stalls | Prefer deterministic progress checks first; Jev must not declare work complete | Not changed |
| Bash/write authorization or prompt-injection defense | Jev is advisory, not a security boundary | Not implemented as a permission mechanism |
| Compaction cut-point selection | Needs a reliable outcome-quality evaluation | Not enabled |
| Browser operation/target selection | Separate opt-in browser skill, not a repurposed task classifier | Wrapper and Pi-backed typing adapter integrated; explicit model selection and host-local Chrome verification remain prerequisites; no browser-action end-to-end run claimed |

The file-triage recommendation was originally conditional. The user subsequently
requested its implementation, and the required privacy guards and opt-in surface
were built and tested. This does not establish superiority over `rg` on arbitrary
repositories. Use deterministic search first and Jev only where it adds judgment.

## What is measured, and what remains unknown

- Direct TypeSafe task classification worked through the installed Pi classifier.
  Early synthetic samples took 207–362 ms. This is not a latency SLA or calibration
  benchmark.
- Jev input pricing is explicitly estimated at $0.042/M tokens; output is free per
  the cited vendor documentation. The built-in zero-price catalog entry is not
  used for our local estimates.
- Scouting's live tool result carried native Pi usage: 2,049 input tokens, 98 output
  tokens, and $0.000086058 estimated cost across two synthetic-file requests.
  That resolves the narrow question of whether **this tool path** carries usage
  into Pi's session transcript; it does not validate accounting for every arbitrary
  direct registry call from every extension.
- Duplicate-read verification avoided 5,458 characters of repeated tool-result
  content (5,753 original versus a 295-character marker). Provider billed-token
  savings and end-to-end task-quality improvements were not measured.
- Confidence is not a permission grant or proof of correctness. Broader task/file
  relevance accuracy and false-negative rates remain uncalibrated.

## Promotion gates

Before automatic routing: compare suggestions with human-labeled tasks, track
abstentions/errors and downstream rework, preserve explicit user choices and the
proxy's hard eligibility gates. Misrouting high-stakes work downward is a stop
condition, not a reason to quietly lower a confidence threshold.

Before expanding file scouting: measure relevance recall against a deterministic
search baseline and main-model context avoided, including classifier latency/cost
and extra retries. Any privacy-guard bypass is a stop condition. Do not turn the
current explicit-candidate tool into an unattended whole-repository uploader.

Current usage: [Jev task pilot](../jev-pi.md), [context efficiency](../jev-context.md),
[browser skill](../jev-ultrafast.md).
