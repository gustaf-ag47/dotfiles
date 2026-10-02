# Limitations and privacy (upstream + this wrapper)

## Upstream (browser-use/jev-ultrafast, as of the pinned commit)

Stated directly in its README/AGENTS.md:

- No frames, shadow DOM, canvas, file uploads, pop-up tabs, nested scrolling, or arbitrary
  keyboard-only widgets. The DOM reader "handles common HTML and ARIA controls, not the full
  accessible-name specification."
- `DONE` requires independent outcome verification; it is Jev's own belief, not proof.
- No site-specific action scripts or hardcoded field strings — every run is goal-driven.
- `TYPE_TEXT` only ever comes from the configured text model's JSON `{"text": ...}` output, parsed and
  length-bounded (max 2000 chars); page content is explicitly documented upstream as **untrusted data,
  never instructions**.
- Browser connects through Browser Harness to a real installed Chrome. Owned tabs are created in the
  background (`Target.createTarget ... background=True`) and do not activate/steal the user's visible
  tab, but **they share the existing Chrome profile** — cookies, logged-in sessions, extensions, and
  history are visible to whatever the agent navigates to. Do not point this at sites where you are
  logged into an account you don't want the agent touching, unless you've verified via `--inspect`
  first and approve every mutating step individually.
- Upstream's own example `.env.example` suggests OpenRouter's `inception/mercury-2.5` for the text
  model. This skill does not assume that, require it, or configure it by default — see
  [text-model.md](text-model.md).

## This wrapper's additional bounds (not upstream defaults)

- `run.py --execute` always requires an explicit `--goal` and `--url`; there is no default goal.
- Step/time budgets are mandatory and hard-capped (20 prediction attempts / 180 seconds).
  The wall-clock deadline includes model calls and approval waits. A timeout stops automation;
  it cannot undo completed browser actions or guarantee cleanup of a tab in a shared browser.
- Every mutating decision (`CLICK`, `TYPE_TEXT`, `SELECT`) is printed and asks for approval before
  execution unless `--auto-approve` is passed; `DONE`/`BLOCKED` never mutate and never prompt.
- No automatic retry of a browser mutation; a stale-page retry only reuses an already-generated
  `TYPE_TEXT` value if the entire text-helper input (goal, field, page title, recent history) is
  byte-identical, matching the upstream guard.
- Traces written by this wrapper never include raw DOM/page text, the TypeSafe/text-model request or
  response bodies, labels, titles, full URLs, or goal text; only operation/confidence/timing
  metadata, URL origins, and a goal hash. Upstream's own recording/demo tooling (which does capture screenshots) is intentionally
  not wrapped here.
- This wrapper never writes to `config/pi/lib/jev.mjs`'s ledger, cache, or budget files — the two Jev
  integrations (task classifier vs. browser agent) are accounted for completely separately.
