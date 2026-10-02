#!/usr/bin/env python3
"""Read-only readiness check for the jev-ultrafast skill.

Never makes a network call, never prints a credential value (booleans only),
never mutates anything. Safe to run at any time, including before setup.sh.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from _bounded import TEXT_MODEL_CONFIGURED, resolve_text_model_config
from _trace import redact_url

PINNED_COMMIT = "1231850a0bf1a0c0341fe408ef1668dbbfdfac46"


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


def tool_found(name: str) -> bool:
    return shutil.which(name) is not None


def chrome_found() -> bool:
    return any(shutil.which(n) for n in ("chromium", "google-chrome", "chromium-browser", "google-chrome-stable"))


def checkout_status(path: Path) -> dict:
    if not (path / ".git").is_dir():
        return {"present": False, "commit": None, "pinned": False, "dirty": None}
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "-C", str(path), "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        )
    except (subprocess.CalledProcessError, OSError):
        return {"present": True, "commit": None, "pinned": False, "dirty": None}
    return {"present": True, "commit": commit, "pinned": commit == PINNED_COMMIT, "dirty": dirty}


def venv_status(path: Path) -> dict:
    venv = path / ".venv"
    return {"present": venv.is_dir(), "has_python": (venv / "bin" / "python").exists()}


def key_configured(env: dict) -> bool:
    if (env.get("TYPESAFE_API_KEY") or "").strip():
        return True
    key_path = default_key_path(env)
    try:
        return bool(key_path.read_text().strip())
    except OSError:
        return False


def state_dir_mode_ok(path: Path) -> bool | None:
    if not path.exists():
        return None
    try:
        return (path.stat().st_mode & 0o777) in (0o700, 0o600)
    except OSError:
        return None


def build_report(env: dict) -> dict:
    checkout = checkout_dir(env)
    cstatus = checkout_status(checkout)
    vstatus = venv_status(checkout) if cstatus["present"] else {"present": False, "has_python": False}
    state_dir = xdg_state_home(env) / "jev-ultrafast"
    text_status, _ = resolve_text_model_config(env)
    report = {
        "pinned_commit": PINNED_COMMIT,
        "checkout_dir": str(checkout),
        "checkout": cstatus,
        "venv": vstatus,
        "tools": {
            "git": tool_found("git"),
            "uv": tool_found("uv"),
            "node": tool_found("node"),
            "chrome": chrome_found(),
        },
        "credentials": {
            "typesafe_key_configured": key_configured(env),
            "key_file": str(default_key_path(env)),
            "text_model_api_key_configured": bool((env.get("TEXT_MODEL_API_KEY") or "").strip()),
            "text_model_base_url": redact_url(env["TEXT_MODEL_BASE_URL"]) if env.get("TEXT_MODEL_BASE_URL") else "(not configured; no automatic backend)",
            "text_model_backend_status": text_status,
        },
        "state_dir": {
            "path": str(state_dir),
            "exists": state_dir.exists(),
            "mode_ok": state_dir_mode_ok(state_dir),
        },
    }
    # "clean" (not dirty) is required, not just a matching HEAD: a dirty tree
    # at the pinned commit can still run code that doesn't match the pin.
    clean_pin = cstatus["present"] and cstatus["pinned"] and cstatus["dirty"] is False
    prerequisites_for_inspect = clean_pin and vstatus["has_python"] and report["tools"]["chrome"]
    prerequisites_for_execute = prerequisites_for_inspect and report["credentials"]["typesafe_key_configured"]
    # This is a prerequisite check only -- doctor.py makes no live browser or
    # network call, so actual Chrome/CDP connectivity is never verified here.
    report["browser_connectivity"] = "not_verified (doctor.py makes no live browser/CDP call; only checks binaries/profile presence)"
    report["prerequisites_present_for_inspect"] = prerequisites_for_inspect
    report["prerequisites_present_for_execute"] = prerequisites_for_execute
    report["prerequisites_present_for_type_text"] = (
        prerequisites_for_execute and text_status == TEXT_MODEL_CONFIGURED
    )
    return report


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    report = build_report(os.environ)
    if as_json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"Pinned commit:        {report['pinned_commit']}")
    print(f"Checkout dir:         {report['checkout_dir']}")
    c = report["checkout"]
    print(f"  present:            {c['present']}")
    print(f"  commit matches pin: {c['pinned']} (actual: {c['commit']})")
    print(f"  local changes:      {c['dirty']}")
    v = report["venv"]
    print(f"  .venv ready:        {v['has_python']}")
    t = report["tools"]
    print(f"Tools: git={t['git']} uv={t['uv']} node={t['node']} chrome={t['chrome']}")
    cr = report["credentials"]
    print(f"TypeSafe key configured: {cr['typesafe_key_configured']} (file: {cr['key_file']})")
    print(f"Text model key configured: {cr['text_model_api_key_configured']} (base: {cr['text_model_base_url']})")
    s = report["state_dir"]
    print(f"State dir: {s['path']} exists={s['exists']} mode_ok={s['mode_ok']}")
    print()
    print(f"browser_connectivity: {report['browser_connectivity']}")
    print(f"prerequisites_present_for_inspect:  {report['prerequisites_present_for_inspect']} (binaries/pin/clean-tree only, not a live check)")
    print(f"prerequisites_present_for_execute:  {report['prerequisites_present_for_execute']} (also needs TypeSafe key)")
    print(f"prerequisites_present_for_type_text: {report['prerequisites_present_for_type_text']} (also needs a complete, valid text-model configuration)")
    if not c["present"]:
        print("\nNext: run scripts/setup.sh to clone the pinned checkout.")
    elif not v["has_python"]:
        print("\nNext: run scripts/setup.sh to 'uv sync' the checkout.")
    elif not t["chrome"]:
        print("\nNext: install Chrome/Chromium; this skill does not install it for you.")
    elif not cr["typesafe_key_configured"]:
        print(f"\nNext: place a TypeSafe key at {cr['key_file']} (mode 0600), or set TYPESAFE_API_KEY.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
