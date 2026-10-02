#!/usr/bin/env python3
"""Outer wrapper for the jev-ultrafast skill. Resolves config/credentials,
enforces bounds, and launches the pinned checkout's own venv via `uv run` for
the actual browser work. Never prints a credential value. Never makes a
network call itself (the subprocess it launches does, only when --execute or
--inspect is given).

Modes:
  (no --inspect, no --execute)  Pre-flight only: print the resolved plan and
                                 config, make no browser/model call, exit 0.
  --inspect                     Observe the page and print the element table.
                                 No TypeSafe/text-model call, no mutation.
  --execute                     Full bounded, step-approved run. Requires
                                 --max-steps and --max-seconds (both capped).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

PINNED_COMMIT = "1231850a0bf1a0c0341fe408ef1668dbbfdfac46"
MAX_STEPS_CAP = 20
MAX_SECONDS_CAP = 180

SKILL_DIR = Path(__file__).resolve().parent


def xdg_cache_home(env: dict) -> Path:
    return Path(env.get("XDG_CACHE_HOME") or Path(env.get("HOME", str(Path.home()))) / ".cache")


def xdg_config_home(env: dict) -> Path:
    return Path(env.get("XDG_CONFIG_HOME") or Path(env.get("HOME", str(Path.home()))) / ".config")


def xdg_state_home(env: dict) -> Path:
    return Path(env.get("XDG_STATE_HOME") or Path(env.get("HOME", str(Path.home()))) / ".local" / "state")


def default_key_path(env: dict) -> Path:
    override = env.get("PI_JEV_KEY_FILE")
    if override:
        return Path(override)
    return xdg_config_home(env) / "jev" / "api-key"


def checkout_dir(env: dict) -> Path:
    return xdg_cache_home(env) / "jev-ultrafast" / "src"


def resolve_typesafe_key(env: dict) -> str | None:
    """Never logs or returns the key in any printed structure; caller must only
    pass it through os.environ to the subprocess, never print it."""
    direct = (env.get("TYPESAFE_API_KEY") or "").strip()
    if direct:
        return direct
    key_path = default_key_path(env)
    try:
        value = key_path.read_text().strip()
        return value or None
    except OSError:
        return None


def checkout_ready(path: Path) -> tuple[bool, str]:
    if not (path / ".git").is_dir():
        return False, f"no checkout at {path}; run scripts/setup.sh first"
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, OSError) as exc:
        return False, f"could not read checkout commit: {exc}"
    if commit != PINNED_COMMIT:
        return False, f"checkout at {commit}, expected pinned {PINNED_COMMIT}; run scripts/setup.sh"
    if not (path / ".venv" / "bin" / "python").exists():
        return False, f"no .venv at {path}/.venv; run scripts/setup.sh"
    return True, "ok"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Explicit starting URL; no default.")
    parser.add_argument("--goal", required=True, help="Explicit natural-language goal; no default.")
    parser.add_argument("--inspect", action="store_true", help="Observe only; no model call, no mutation.")
    parser.add_argument("--execute", action="store_true", help="Run the bounded, approved agent loop.")
    parser.add_argument("--max-steps", type=int, help=f"Required with --execute; capped at {MAX_STEPS_CAP}.")
    parser.add_argument("--max-seconds", type=float, help=f"Required with --execute; capped at {MAX_SECONDS_CAP}.")
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Skip the per-step y/N prompt (step/time bounds still apply). Use only once you trust the goal/site.",
    )
    parser.add_argument("--trace-path", help="Override the redacted trace output path.")
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    env = dict(os.environ)

    if args.inspect and args.execute:
        print("run.py: --inspect and --execute are mutually exclusive", file=sys.stderr)
        return 2

    if args.execute:
        # Bounds are a property of the request itself, not of what happens to
        # be installed, so they are enforced before touching the checkout,
        # credentials, or filesystem state at all.
        if args.max_steps is None or args.max_seconds is None:
            print("run.py: --execute requires --max-steps and --max-seconds", file=sys.stderr)
            return 2
        if args.max_steps <= 0 or args.max_steps > MAX_STEPS_CAP:
            print(f"run.py: --max-steps must be 1..{MAX_STEPS_CAP}", file=sys.stderr)
            return 2
        if args.max_seconds <= 0 or args.max_seconds > MAX_SECONDS_CAP:
            print(f"run.py: --max-seconds must be 1..{MAX_SECONDS_CAP}", file=sys.stderr)
            return 2

    checkout = checkout_dir(env)
    ready, reason = checkout_ready(checkout)

    print(f"Pinned commit: {PINNED_COMMIT}")
    print(f"Checkout: {checkout} ({'ready' if ready else 'NOT READY: ' + reason})")
    print(f"URL: {args.url}")
    print(f"Goal: {args.goal}")

    if not args.inspect and not args.execute:
        key_present = resolve_typesafe_key(env) is not None
        text_key_present = bool((env.get("TEXT_MODEL_API_KEY") or "").strip())
        print(f"TypeSafe key configured: {key_present}")
        print(f"Text model key configured (needed only for TYPE_TEXT steps): {text_key_present}")
        print("Dry run only: pass --inspect to observe, or --execute --max-steps N --max-seconds S to run.")
        return 0 if ready else 1

    if not ready:
        print(f"run.py: {reason}", file=sys.stderr)
        return 1

    if args.inspect:
        proc_env = dict(env)
        cmd = [
            "uv",
            "run",
            "--project",
            str(checkout),
            "python",
            str(SKILL_DIR / "_inspect_driver.py"),
            "--url",
            args.url,
            "--goal",
            args.goal,
        ]
        result = subprocess.run(cmd, cwd=str(checkout), env=proc_env)
        return result.returncode

    # --execute (bounds already validated above, before checkout readiness)
    typesafe_key = resolve_typesafe_key(env)
    if not typesafe_key:
        print(
            f"run.py: no TypeSafe key found (checked TYPESAFE_API_KEY and {default_key_path(env)}); "
            "cannot --execute.",
            file=sys.stderr,
        )
        return 1
    if not (env.get("TEXT_MODEL_API_KEY") or "").strip():
        print(
            "run.py: TEXT_MODEL_API_KEY is not set. CLICK/SELECT/WAIT steps still work; any TYPE_TEXT "
            "step will fail loudly instead of typing a value. See references/text-model.md.",
            file=sys.stderr,
        )

    trace_dir = xdg_state_home(env) / "jev-ultrafast" / "traces"
    trace_path = Path(args.trace_path) if args.trace_path else trace_dir / f"{int(time.time())}.json"
    trace_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    proc_env = dict(env)
    proc_env["TYPESAFE_API_KEY"] = typesafe_key  # passed via env only, never argv/log
    cmd = [
        "uv",
        "run",
        "--project",
        str(checkout),
        "python",
        str(SKILL_DIR / "_agent_driver.py"),
        "--url",
        args.url,
        "--goal",
        args.goal,
        "--max-steps",
        str(args.max_steps),
        "--max-seconds",
        str(args.max_seconds),
        "--trace-path",
        str(trace_path),
    ]
    if args.auto_approve:
        cmd.append("--auto-approve")

    print(f"Trace will be written to: {trace_path}")
    result = subprocess.run(cmd, cwd=str(checkout), env=proc_env)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
