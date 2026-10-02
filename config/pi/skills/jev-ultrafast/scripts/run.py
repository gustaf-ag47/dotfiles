#!/usr/bin/env python3
"""Outer wrapper for the jev-ultrafast skill. Resolves config/credentials,
enforces bounds, and launches the pinned checkout's own venv via `uv run` for
the actual browser work. Never prints a credential value. Never makes a
network call itself (the subprocess it launches does, only when --execute or
--inspect is given), and always enforces its own hard wall-clock timeout on
that subprocess -- independent of the subprocess's own internal bounds --
killing the subprocess's entire process group on expiry so a blocked
predict()/input() call or a stuck --inspect observation cannot hang forever
or leak an orphaned browser/uv process.

Modes:
  (no --inspect, no --execute)  Pre-flight only: print the resolved plan and
                                 config, make no browser/model call, exit 0.
  --inspect                     Observe the page and print the element table.
                                 No TypeSafe/text-model call, no mutation.
                                 Bounded by a fixed outer timeout.
  --execute                     Full bounded, step-approved run. Requires
                                 --max-steps and --max-seconds (both capped,
                                 both rejected if non-finite/NaN/out of
                                 range).

Exit codes are never treated as "0 = success, nonzero = error": see
_bounded.STATUS_FOR_EXIT_CODE. A `DONE` exit (0) is still not independent
proof the goal was achieved -- verify it yourself.
"""
from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
import time
from pathlib import Path

from _bounded import (
    EXIT_DONE,
    EXIT_ERROR,
    EXIT_USAGE,
    STATUS_FOR_EXIT_CODE,
    TEXT_MODEL_CONFIGURED,
    TEXT_MODEL_INVALID_BASE_URL,
    TEXT_MODEL_PARTIAL,
    InvalidUrlError,
    resolve_text_model_config,
    run_bounded,
    validate_url,
)
import _trace

PINNED_COMMIT = "1231850a0bf1a0c0341fe408ef1668dbbfdfac46"
MAX_STEPS_CAP = 20
MAX_SECONDS_CAP = 180
INSPECT_TIMEOUT_SECONDS = 60

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
    """Pin match on HEAD alone is not sufficient: a dirty working tree at the
    pinned commit can still run code that doesn't match the pin, so local
    changes are rejected the same as a wrong commit."""
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
    try:
        dirty = bool(
            subprocess.check_output(
                ["git", "-C", str(path), "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        return False, f"could not read checkout status: {exc}"
    if dirty:
        return False, f"{path} has local changes despite matching the pinned commit; refusing to run"
    if not (path / ".venv" / "bin" / "python").exists():
        return False, f"no .venv at {path}/.venv; run scripts/setup.sh"
    return True, "ok"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Explicit starting URL; http(s) only, no embedded credentials.")
    parser.add_argument("--goal", required=True, help="Explicit natural-language goal; no default.")
    parser.add_argument("--inspect", action="store_true", help="Observe only; no model call, no mutation.")
    parser.add_argument("--execute", action="store_true", help="Run the bounded, approved agent loop.")
    parser.add_argument("--max-steps", type=int, help=f"Required with --execute; capped at {MAX_STEPS_CAP}.")
    parser.add_argument("--max-seconds", type=float, help=f"Required with --execute; capped at {MAX_SECONDS_CAP}.")
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Skip the per-step y/N prompt (step/time bounds still apply). Default is per-step approval.",
    )
    parser.add_argument("--trace-path", help="Override the redacted trace output path.")
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    env = dict(os.environ)

    try:
        validate_url(args.url)
    except InvalidUrlError as exc:
        # Never echo the raw URL back here: if it was rejected for embedding
        # credentials, the credential would be echoed right along with it.
        print(f"run.py: invalid --url: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if args.inspect and args.execute:
        print("run.py: --inspect and --execute are mutually exclusive", file=sys.stderr)
        return EXIT_USAGE

    if args.execute:
        # Bounds are a property of the request itself, not of what happens to
        # be installed, so they are enforced before touching the checkout,
        # credentials, or filesystem state at all. math.isfinite rejects NaN
        # and +/-inf, which `x <= 0 or x > CAP` alone does not (NaN compares
        # false to everything, so a NaN --max-seconds would otherwise sail
        # through both range checks).
        if args.max_steps is None or args.max_seconds is None:
            print("run.py: --execute requires --max-steps and --max-seconds", file=sys.stderr)
            return EXIT_USAGE
        if not math.isfinite(args.max_steps) or args.max_steps <= 0 or args.max_steps > MAX_STEPS_CAP:
            print(f"run.py: --max-steps must be a finite integer 1..{MAX_STEPS_CAP}", file=sys.stderr)
            return EXIT_USAGE
        if not math.isfinite(args.max_seconds) or args.max_seconds <= 0 or args.max_seconds > MAX_SECONDS_CAP:
            print(f"run.py: --max-seconds must be a finite number 1..{MAX_SECONDS_CAP}", file=sys.stderr)
            return EXIT_USAGE
        # Also a property of the request itself, checked before the checkout:
        # upstream's field_text() (model.py) defaults TEXT_MODEL_BASE_URL/
        # TEXT_MODEL the moment TEXT_MODEL_API_KEY alone is set, silently
        # reaching https://api.deepseek.com/v1 (deepseek-chat). Refuse a
        # partial config outright -- all three or none, never a silent
        # partial default -- and require HTTPS with no embedded credentials.
        text_status, text_detail = resolve_text_model_config(env)
        if text_status == TEXT_MODEL_PARTIAL:
            print(
                "run.py: TEXT_MODEL_API_KEY / TEXT_MODEL_BASE_URL / TEXT_MODEL must all be set together, or "
                "none at all -- refusing to --execute rather than let a partial config silently fall back to "
                "upstream's default endpoint (https://api.deepseek.com/v1). See references/text-model.md.",
                file=sys.stderr,
            )
            return EXIT_ERROR
        if text_status == TEXT_MODEL_INVALID_BASE_URL:
            print(f"run.py: invalid TEXT_MODEL_BASE_URL: {text_detail}", file=sys.stderr)
            return EXIT_ERROR

    checkout = checkout_dir(env)
    ready, reason = checkout_ready(checkout)

    print(f"Pinned commit: {PINNED_COMMIT}")
    print(f"Checkout: {checkout} ({'ready' if ready else 'NOT READY: ' + reason})")
    print(f"URL: {_trace.redact_url(args.url)}")
    print(f"Goal: {len(args.goal)} characters (not printed)")

    if not args.inspect and not args.execute:
        key_present = resolve_typesafe_key(env) is not None
        text_status, _ = resolve_text_model_config(env)
        print(f"TypeSafe key configured: {key_present}")
        print(
            f"Text-model backend status: {text_status} (TEXT_MODEL_API_KEY + TEXT_MODEL_BASE_URL + TEXT_MODEL "
            "must all be set together, or none at all; required for TYPE_TEXT steps only, no default backend "
            "is ever chosen for you)"
        )
        print("Dry run only: pass --inspect to observe, or --execute --max-steps N --max-seconds S to run.")
        return 0 if ready else EXIT_ERROR

    if not ready:
        print(f"run.py: {reason}", file=sys.stderr)
        return EXIT_ERROR

    if args.inspect:
        proc_env = dict(env)
        cmd = [
            "uv", "run", "--project", str(checkout), "python",
            str(SKILL_DIR / "_inspect_driver.py"),
            "--url", args.url, "--goal", args.goal,
        ]
        result = run_bounded(cmd, cwd=str(checkout), env=proc_env, timeout_seconds=INSPECT_TIMEOUT_SECONDS)
        _report_final(result.returncode, inspect_mode=True)
        return result.returncode

    # --execute (bounds already validated above, before checkout readiness)
    typesafe_key = resolve_typesafe_key(env)
    if not typesafe_key:
        print(
            f"run.py: no TypeSafe key found (checked TYPESAFE_API_KEY and {default_key_path(env)}); "
            "cannot --execute.",
            file=sys.stderr,
        )
        return EXIT_ERROR
    # (bounds and text-model routing already validated above, before the checkout was even consulted)
    text_status, _ = resolve_text_model_config(env)
    if text_status == TEXT_MODEL_CONFIGURED:
        print("Text-model backend configured (all three of API key/base URL/model set). TYPE_TEXT steps can run.", file=sys.stderr)
    else:
        print(
            "Text-model backend not configured. CLICK/SELECT/WAIT/DONE steps still work; any TYPE_TEXT step will "
            "fail loudly instead of typing a value -- no default text-model backend is ever chosen for you. "
            "See references/text-model.md.",
            file=sys.stderr,
        )

    trace_dir = xdg_state_home(env) / "jev-ultrafast" / "traces"
    trace_path = Path(args.trace_path) if args.trace_path else trace_dir / f"{int(time.time())}.json"

    proc_env = dict(env)
    proc_env["TYPESAFE_API_KEY"] = typesafe_key  # passed via env only, never argv/log
    cmd = [
        "uv", "run", "--project", str(checkout), "python",
        str(SKILL_DIR / "_agent_driver.py"),
        "--url", args.url, "--goal", args.goal,
        "--max-steps", str(args.max_steps),
        "--max-seconds", str(args.max_seconds),
        "--trace-path", str(trace_path),
    ]
    if args.auto_approve:
        cmd.append("--auto-approve")

    outer_timeout = args.max_seconds
    print(f"Trace will be written to: {trace_path}")
    print(f"Outer hard timeout: {outer_timeout:g}s (includes model calls and approval waits)")
    result = run_bounded(cmd, cwd=str(checkout), env=proc_env, timeout_seconds=outer_timeout)
    _report_final(result.returncode, inspect_mode=False)
    return result.returncode


def _report_final(code: int, *, inspect_mode: bool) -> None:
    if inspect_mode:
        msg = "Observation finished." if code == EXIT_DONE else STATUS_FOR_EXIT_CODE.get(code, f"Unknown exit code {code}; treat as incomplete.")
    else:
        msg = STATUS_FOR_EXIT_CODE.get(code, f"Unknown exit code {code}; treat as incomplete, not success.")
    print(f"Final: {msg}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
