#!/usr/bin/env python3
"""Runs *inside* the pinned jev-ultrafast checkout's own venv (via `uv run`).

Not meant to be invoked directly; run.py launches this as a subprocess with
TYPESAFE_API_KEY / TEXT_MODEL_API_KEY inherited through the environment, never
through argv, and always under its own hard wall-clock timeout (see
_bounded.run_bounded) that kills this process's entire group on expiry --
this script's own loop-level bounds below are a second, inner layer, not the
only one.

Implements the step-by-step approval gate this skill requires on top of
upstream's Agent class: every CLICK/TYPE_TEXT/SELECT decision is printed and
confirmed (unless --auto-approve) before upstream's own .command("act") is
called. DONE/BLOCKED never mutate the page and are never prompted.

Every *prediction attempt* counts against --max-steps, not only an approved,
executed action -- an unapproved or non-mutating decision (DONE/BLOCKED,
disapproval) still costs one billed TypeSafe call and must not let the loop
keep calling predict() forever.

Exit code is never a bare 0/1 "success/fail": see _bounded.EXIT_* and
STATUS_FOR_EXIT_CODE. Only ever prints: operation, confidence, latency,
redacted URL. Never prints a raw traceback or an upstream exception's full
text (see _bounded.safe_error_text); never writes an element label, a raw
URL/title, or the goal text to the trace file (see _trace.py).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from _bounded import (
    EXIT_BLOCKED,
    EXIT_DONE,
    EXIT_ERROR,
    EXIT_NOT_APPROVED,
    EXIT_STEP_BUDGET_EXHAUSTED,
    EXIT_TIME_BUDGET_EXHAUSTED,
    safe_error_text,
)
import _trace

from jev_ultrafast import Agent  # noqa: E402  (installed in this venv by uv sync)
import jev_ultrafast.agent as agent_module
from _pi_text import configure_text_backend


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--max-steps", type=int, required=True)
    parser.add_argument("--max-seconds", type=float, required=True)
    parser.add_argument("--auto-approve", action="store_true")
    parser.add_argument("--trace-path", required=True)
    args = parser.parse_args(argv)

    trace = _trace.build_trace(
        url=args.url, goal=args.goal, max_steps=args.max_steps, max_seconds=args.max_seconds,
        auto_approve=args.auto_approve,
    )
    deadline = time.monotonic() + args.max_seconds
    predict_count = 0
    exit_code = EXIT_ERROR

    try:
        configure_text_backend(agent_module, os.environ)
        with Agent(args.url, args.goal) as agent:
            print(f"Observed: {_trace.redact_url(agent.state['page']['url'])!r}", file=sys.stderr)
            while True:
                if agent.state["status"] in {"done", "blocked"}:
                    exit_code = EXIT_DONE if agent.state["status"] == "done" else EXIT_BLOCKED
                    break
                if predict_count >= args.max_steps:
                    exit_code = EXIT_STEP_BUDGET_EXHAUSTED
                    break
                if time.monotonic() >= deadline:
                    exit_code = EXIT_TIME_BUDGET_EXHAUSTED
                    break

                # Count the attempt before dispatch: a TypeSafe call that was
                # sent still bounds the budget even if its result is never
                # approved or never becomes a mutating action.
                predict_count += 1
                agent.command("predict")
                decision = agent.state["decision"]
                if decision is None:
                    exit_code = EXIT_ERROR
                    break
                op = decision["operation"]
                print(
                    f"Decision {predict_count}/{args.max_steps}: operation={op} "
                    f"confidence={decision['confidence']:.3f} latency_ms={decision['latency_ms']}",
                    file=sys.stderr,
                )

                mutating = op not in {"DONE", "BLOCKED"}
                if mutating and not args.auto_approve:
                    # Shown only on the interactive terminal, never persisted
                    # to the trace file.
                    reply = input(f"Approve {op} on {decision['choice']!r}? [y/N] ").strip().lower()
                    if reply != "y":
                        exit_code = EXIT_NOT_APPROVED
                        break

                agent.command("act", {"fingerprint": agent.state["page"]["fingerprint"]})
                if agent.state["history"]:
                    trace["steps"].append(_trace.redact_step(agent.state["history"][-1], predict_count))

            trace["final_status"] = agent.state["status"]
            trace["final_url"] = _trace.redact_url(agent.state["page"]["url"])
            trace["exit_code"] = exit_code
            print(f"Final: status={agent.state['status']} predict_calls={predict_count}", file=sys.stderr)
            if agent.state["status"] == "done":
                print(
                    "NOTE: DONE is Jev's own belief, not independent proof. Verify the goal yourself.",
                    file=sys.stderr,
                )
            else:
                print("NOTE: run did not complete; treat as incomplete, not success.", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 -- must never leak a raw traceback/body
        trace["final_status"] = "error"
        trace["exit_code"] = EXIT_ERROR
        print(f"Error: {safe_error_text(exc)}", file=sys.stderr)
        exit_code = EXIT_ERROR
    finally:
        try:
            _trace.write_trace_atomic(Path(args.trace_path), trace)
        except OSError as exc:
            print(f"Warning: could not write trace: {safe_error_text(exc)}", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
