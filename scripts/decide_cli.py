#!/usr/bin/env python3
"""`decide` CLI: talk to a running decision-gate service.

Usage:
    decide ask --purpose P --sensitivity private|internal|public --state TEXT \\
        --question id:kind:prompt[:opt1,opt2,...]   (repeatable)
    decide outcome --decision-id ID --truth '{"kind":"invoice"}' --source opus|human|agent
    decide report [--purpose P]
    decide health
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "config" / "decision-gate"))
import decision_gate_client as client  # noqa: E402


def parse_question(spec: str) -> dict:
    parts = spec.split(":", 3)
    if len(parts) < 3:
        raise argparse.ArgumentTypeError("question must be id:kind:prompt[:opt1,opt2,...]")
    qid, kind, prompt = parts[0], parts[1], parts[2]
    q = {"id": qid, "kind": kind, "prompt": prompt}
    if kind == "choice":
        if len(parts) != 4 or not parts[3]:
            raise argparse.ArgumentTypeError("choice questions need :opt1,opt2,... options")
        q["options"] = parts[3].split(",")
    return q


def cmd_ask(args):
    questions = [parse_question(q) for q in args.question]
    result = client.decide(args.purpose, args.sensitivity, args.state, questions,
                            base_url=args.base_url, timeout_s=args.timeout, strict=True)
    print(json.dumps(result, indent=2))
    return 0


def cmd_outcome(args):
    try:
        truth = json.loads(args.truth)
    except ValueError:
        print("decide: --truth must be valid JSON", file=sys.stderr)
        return 2
    result = client.outcome(args.decision_id, truth, args.source, base_url=args.base_url,
                             timeout_s=args.timeout, strict=True)
    print(json.dumps(result, indent=2))
    return 0


def cmd_report(args):
    result = client.report(args.purpose, base_url=args.base_url, timeout_s=args.timeout, strict=True)
    print(json.dumps(result, indent=2))
    return 0


def cmd_health(args):
    ok = client.healthz(base_url=args.base_url)
    print(json.dumps({"healthy": ok}))
    return 0 if ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="decide")
    parser.add_argument("--base-url", default=client.DEFAULT_BASE_URL)
    parser.add_argument("--timeout", type=float, default=client.DEFAULT_TIMEOUT_S)
    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask")
    ask.add_argument("--purpose", required=True)
    ask.add_argument("--sensitivity", required=True, choices=["private", "internal", "public"])
    ask.add_argument("--state", required=True)
    ask.add_argument("--question", action="append", required=True)
    ask.set_defaults(func=cmd_ask)

    outcome = sub.add_parser("outcome")
    outcome.add_argument("--decision-id", required=True)
    outcome.add_argument("--truth", required=True)
    outcome.add_argument("--source", required=True, choices=["opus", "human", "agent"])
    outcome.set_defaults(func=cmd_outcome)

    report = sub.add_parser("report")
    report.add_argument("--purpose", default=None)
    report.set_defaults(func=cmd_report)

    health = sub.add_parser("health")
    health.set_defaults(func=cmd_health)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except client.DecisionGateError as exc:
        print(f"decide: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
