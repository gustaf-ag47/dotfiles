#!/usr/bin/env python3
"""Run the host-local LLM smoke suite without retaining account-sensitive output."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

SCHEMA = "llm-host-smoke.v1"
CHECKS = (
    "git status --short",
    "make test-unit",
    "python3 -m unittest tests.unit.test_llm_usage tests.unit.test_llm_news tests.unit.test_claude_token_proxy -v",
    "node --test --experimental-strip-types tests/unit/test_llm_failover.mjs",
    "bin/llm-usage --refresh --json | python3 -m json.tool >/dev/null",
    "bin/llm-news --json | python3 -m json.tool >/dev/null",
    "curl -s --noproxy '*' \"http://127.0.0.1:${CC_PROXY_PORT:-8788}/_usage\" | python3 -m json.tool >/dev/null",
    "curl -s --noproxy '*' \"http://127.0.0.1:${CC_PROXY_PORT:-8788}/_route?model=claude-opus-5-5\" | python3 -m json.tool >/dev/null",
    "pi --no-session -p '/usage'",
)


def cache_metadata():
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "llm-usage"
    try:
        mode = oct(cache.stat().st_mode & 0o777)
    except OSError:
        mode = None
    return {"path": str(cache), "mode": mode}


def run_check(command, root):
    if command.startswith("pi ") and shutil.which("pi") is None:
        return "unavailable"
    try:
        completed = subprocess.run(
            command, cwd=root, shell=True, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=300, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "timeout-or-error"
    return "pass" if completed.returncode == 0 else "fail"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print the redacted check contract")
    parser.add_argument("--root", default=Path.cwd(), type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.list:
        print(json.dumps({"schema": SCHEMA, "hostname": socket.gethostname(),
                          "redacted": True, "checks": list(CHECKS)}, sort_keys=True))
        return 0
    results = {command: run_check(command, args.root) for command in CHECKS}
    print(json.dumps({"schema": SCHEMA, "hostname": socket.gethostname(), "redacted": True,
                      "cache": cache_metadata(), "results": results}, sort_keys=True))
    return 0 if all(value in ("pass", "unavailable") for value in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
