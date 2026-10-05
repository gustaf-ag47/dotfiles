#!/usr/bin/env python3
"""Print the Grok CLI's current OAuth access token, read-only.

Reads `$GROK_HOME/auth.json` (default `~/.grok/auth.json`), the file the
official Grok CLI (`grok login --device-auth`) manages. This script never
writes to that file -- the Grok CLI remains the sole owner of that file's
refresh/rotation. When the stored access token has expired, the script pokes
the Grok CLI itself (a cheap, non-interactive `grok models` invocation) so
the CLI performs its own refresh, then re-reads the file; the refresh token
is still only ever rotated in one place. Pi's grok-build provider shells out
to this script fresh on every request instead of caching a copy.

Guards against anything other than the Grok CLI's own fixed OAuth issuer and
client id, so a tampered or unrelated auth.json entry cannot be used as a
credential for an arbitrary host. Exits non-zero with a short, non-secret
message on any missing/malformed/expired state; never prints partial secrets,
stack traces, or raw file contents on error.

Usage:
    grok_oauth.py            # print the current access token, or exit 1
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Fixed, known issuer/client -- the Grok CLI's own OAuth app registration.
# Never resolve this dynamically from file contents; an attacker-controlled
# auth.json must not be able to redirect which issuer/client we trust.
OIDC_ISSUER = "https://auth.x.ai"
OIDC_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
ENTRY_KEY = f"{OIDC_ISSUER}::{OIDC_CLIENT_ID}"

# Refresh skew: treat a token as expired slightly before its reported expiry,
# matching the margin Pi's own OAuth flows use, so a near-expiry token isn't
# handed to a request that will outlive it.
EXPIRY_SKEW_SECONDS = 5 * 60


def grok_home() -> Path:
    raw = os.environ.get("GROK_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".grok"


def load_auth_file(path: Path) -> dict:
    try:
        text = path.read_text()
    except FileNotFoundError:
        sys.exit(f"No Grok CLI auth file at {path}; run `grok login --device-auth`.")
    except PermissionError:
        sys.exit(f"Cannot read Grok CLI auth file at {path} (permission denied).")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        sys.exit(f"Grok CLI auth file at {path} is not valid JSON.")
    if not isinstance(data, dict):
        sys.exit(f"Grok CLI auth file at {path} has an unexpected shape.")
    return data


def _expired(entry: dict) -> bool:
    """Best-effort expiry check. Community-observed field name `expires_at`
    (ISO 8601); treat its absence as unknown rather than expired, since the
    CLI itself -- not this script -- owns refreshing when it is present."""
    raw = entry.get("expires_at")
    if not isinstance(raw, str) or not raw:
        return False
    try:
        # Accept trailing 'Z' as UTC.
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        expiry = datetime.fromisoformat(normalized)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        expires_at = expiry.timestamp()
    except (ValueError, OverflowError):
        return False
    return (expires_at - EXPIRY_SKEW_SECONDS) < time.time()


# How long to wait for the Grok CLI to refresh its own session when we poke
# it. `grok models` is a cheap metadata call, but it does hit the network.
CLI_REFRESH_TIMEOUT_SECONDS = 60


def _poke_grok_cli_refresh() -> bool:
    """Ask the Grok CLI to refresh its own session by running a cheap,
    non-interactive command (`grok models`). The CLI -- not this script --
    rotates the token in auth.json as a side effect. Returns True if the CLI
    ran and exited 0; never raises, never prints CLI output (which could
    contain account details) to our stdout, which must stay token-only."""
    grok = shutil.which("grok")
    if not grok:
        return False
    try:
        result = subprocess.run(
            [grok, "models"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=CLI_REFRESH_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _load_entry(path: Path) -> dict:
    data = load_auth_file(path)
    entry = data.get(ENTRY_KEY)
    if not isinstance(entry, dict):
        sys.exit(
            "No Grok CLI OAuth session for the expected issuer/client; "
            "run `grok login --device-auth`."
        )
    if entry.get("auth_mode") != "oidc":
        sys.exit("Grok CLI auth entry is not an OIDC session; run `grok login --device-auth`.")
    if not isinstance(entry.get("key"), str) or not entry["key"]:
        sys.exit("Grok CLI auth entry has no access token; run `grok login --device-auth`.")
    return entry


def main() -> int:
    path = grok_home() / "auth.json"
    entry = _load_entry(path)

    if _expired(entry):
        # Let the Grok CLI refresh its own session, then re-read the file it
        # owns. We never write auth.json ourselves.
        if _poke_grok_cli_refresh():
            entry = _load_entry(path)
        if _expired(entry):
            sys.exit("Grok CLI OAuth session has expired and auto-refresh via `grok models` failed; run `grok login --device-auth`.")

    print(entry["key"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
