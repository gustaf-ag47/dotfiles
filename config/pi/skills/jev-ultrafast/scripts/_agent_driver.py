#!/usr/bin/env python3
"""Runs *inside* the pinned jev-ultrafast checkout's own venv (via `uv run`).

Not meant to be invoked directly; run.py launches this as a subprocess with
TYPESAFE_API_KEY / TEXT_MODEL_API_KEY inherited through the environment, never
through argv. Implements the step-by-step approval gate this skill requires on
top of upstream's Agent class: every CLICK/TYPE_TEXT/SELECT decision is printed
and confirmed (unless --auto-approve) before upstream's own .command("act") is
called. DONE/BLOCKED never mutate the page and are never prompted.

Only ever prints: operation, a truncated element label, confidence, latency,
URL/title. Never prints raw page text, the TypeSafe/text-model request or
response body, or any credential.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from jev_ultrafast import Agent  # noqa: E402  (installed in this venv by uv sync)


def truncate(label: str, limit: int = 80) -> str:
    label = label or ""
    return label if len(label) <= limit else label[: limit - 1] + "\u2026"


def redacted_step(step: dict) -> dict:
    return {
        "step": step.get("step"),
        "operation": step.get("operation"),
        "action_label": truncate(step.get("action")),
        "probability": step.get("probability"),
        "confidence": step.get("confidence"),
        "latency_ms": step.get("latency_ms"),
        "text_entered": step.get("text") is not None,  # presence only, never the value
        "page_changed": step.get("page_changed"),
        "elapsed_ms": step.get("elapsed_ms"),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--max-steps", type=int, required=True)
    parser.add_argument("--max-seconds", type=float, required=True)
    parser.add_argument("--auto-approve", action="store_true")
    parser.add_argument("--trace-path", required=True)
    args = parser.parse_args(argv)

    trace = {
        "schema": "jev-ultrafast-trace.v1",
        "url": args.url,
        "goal_sha256_only": None,  # goal text itself is not written to the trace
        "max_steps": args.max_steps,
        "max_seconds": args.max_seconds,
        "auto_approve": args.auto_approve,
        "steps": [],
        "final_status": None,
        "final_url": None,
        "final_title": None,
    }
    import hashlib

    trace["goal_sha256_only"] = hashlib.sha256(args.goal.encode("utf-8")).hexdigest()

    deadline = time.monotonic() + args.max_seconds
    try:
        with Agent(args.url, args.goal) as agent:
            print(f"Observed: {agent.state['page']['url']!r} ({agent.state['page']['title']!r})", file=sys.stderr)
            while True:
                if agent.state["status"] in {"done", "blocked"}:
                    break
                if len(agent.state["history"]) >= args.max_steps:
                    print(f"Stopped: reached --max-steps={args.max_steps}", file=sys.stderr)
                    break
                if time.monotonic() >= deadline:
                    print(f"Stopped: reached --max-seconds={args.max_seconds}", file=sys.stderr)
                    break

                agent.command("predict")
                decision = agent.state["decision"]
                if decision is None:
                    break
                op = decision["operation"]
                print(
                    f"Decision: operation={op} choice={decision['choice']!r} "
                    f"confidence={decision['confidence']:.3f} latency_ms={decision['latency_ms']}",
                    file=sys.stderr,
                )

                mutating = op not in {"DONE", "BLOCKED"}
                if mutating and not args.auto_approve:
                    reply = input(f"Approve {op} on {decision['choice']!r}? [y/N] ").strip().lower()
                    if reply != "y":
                        print("Not approved; stopping.", file=sys.stderr)
                        break

                agent.command("act", {"fingerprint": agent.state["page"]["fingerprint"]})
                if agent.state["history"]:
                    trace["steps"].append(redacted_step(agent.state["history"][-1]))

            trace["final_status"] = agent.state["status"]
            trace["final_url"] = agent.state["page"]["url"]
            trace["final_title"] = agent.state["page"]["title"]
            print(
                f"Final: status={agent.state['status']} url={agent.state['page']['url']!r} "
                f"title={agent.state['page']['title']!r}",
                file=sys.stderr,
            )
            print(
                "NOTE: a 'done' status is Jev's own belief, not independent proof. "
                "Verify the goal was actually achieved yourself.",
                file=sys.stderr,
            )
    finally:
        Path(args.trace_path).parent.mkdir(parents=True, exist_ok=True)
        Path(args.trace_path).write_text(json.dumps(trace, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
