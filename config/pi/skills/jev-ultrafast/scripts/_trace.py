"""Pure, upstream-independent trace writing + metadata redaction.

No import of jev_ultrafast; importable and testable without the pinned
checkout or any network access. Traces are metadata-only: never raw page
text, action labels, titles, full URLs with query/fragment, prompts, request
or response bodies, or credentials. Written atomically at 0600 in a 0700
directory so a crash never leaves a partial/world-readable file.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

# Explicit allow-list, not a deny-list: a new field upstream adds to its
# history dict is excluded by default, not leaked by default.
_STEP_FIELDS = ("operation", "probability", "confidence", "latency_ms", "page_changed", "elapsed_ms")


def redact_url(url: str) -> str:
    """Origin only: paths can contain reset tokens or private account identifiers."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        netloc = f"[{host}]" if ":" in host else host
        if parts.port:
            netloc = f"{netloc}:{parts.port}"
        return urlunsplit((parts.scheme, netloc, "", "", ""))
    except ValueError:
        return "(unparseable)"


def redact_step(step: dict, step_index: int) -> dict:
    """Keeps only bounded, non-content fields: operation, probability,
    confidence, latency, whether the page changed, elapsed time, and whether
    *some* text was entered (never the text itself). Never the element
    label, never a URL, never a title."""
    out = {"step": step_index}
    for key in _STEP_FIELDS:
        if key in step:
            out[key] = step[key]
    out["text_entered"] = step.get("text") is not None
    return out


def goal_fingerprint(goal: str) -> str:
    return hashlib.sha256(goal.encode("utf-8")).hexdigest()


def build_trace(*, url: str, goal: str, max_steps: int, max_seconds: float, auto_approve: bool) -> dict:
    return {
        "schema": "jev-ultrafast-trace.v2",
        "url": redact_url(url),
        "goal_sha256_only": goal_fingerprint(goal),
        "max_steps": max_steps,
        "max_seconds": max_seconds,
        "auto_approve": bool(auto_approve),
        "steps": [],
        "final_status": None,
        "final_url": None,
        "exit_code": None,
    }


def write_trace_atomic(path: Path, trace: dict) -> None:
    """Writes `trace` to `path` atomically at mode 0600, creating its parent
    directory at mode 0700 if needed. Never leaves a partially-written file
    at the final path (temp file in the same directory + os.replace)."""
    path = Path(path)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass
    fd, tmp_name = tempfile.mkstemp(prefix=".trace-", suffix=".tmp", dir=str(parent))
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(trace, indent=2))
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
