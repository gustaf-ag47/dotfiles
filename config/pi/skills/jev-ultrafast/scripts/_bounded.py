"""Pure helpers shared by run.py and the in-venv drivers: a hard-walled
subprocess runner (process-group timeout), URL validation, and safe error
text. No import of jev_ultrafast, no network; safe to unit test directly
without the pinned checkout.
"""
from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass
from urllib.parse import urlsplit

# Shared exit-code vocabulary so a subprocess's returncode can be interpreted
# honestly: only EXIT_DONE is ever described as the agent's own completion,
# and even that is never treated as verified success by the caller. Every
# other code means the run did not complete and must not be reported as a
# silent success.
EXIT_DONE = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_BLOCKED = 10
EXIT_STEP_BUDGET_EXHAUSTED = 11
EXIT_TIME_BUDGET_EXHAUSTED = 12
EXIT_NOT_APPROVED = 13
EXIT_TIMEOUT = 124  # matches the conventional coreutils `timeout` exit code

STATUS_FOR_EXIT_CODE = {
    EXIT_DONE: "Jev reported DONE. NOT independently verified -- check the goal yourself.",
    EXIT_ERROR: "An error occurred. Treat as incomplete, not success.",
    EXIT_BLOCKED: "Jev reported BLOCKED (no supported operation could progress).",
    EXIT_STEP_BUDGET_EXHAUSTED: "Step budget exhausted before completion.",
    EXIT_TIME_BUDGET_EXHAUSTED: "Time budget exhausted before completion.",
    EXIT_NOT_APPROVED: "A step was not approved; run stopped.",
    EXIT_TIMEOUT: "Outer timeout killed the run (possible hang). Treat as incomplete, not success.",
}


class InvalidUrlError(ValueError):
    pass


def validate_url(url: str) -> str:
    """Only plain http(s) URLs with no embedded userinfo credentials.
    Returns the URL unchanged on success; raises InvalidUrlError otherwise."""
    try:
        parts = urlsplit(url)
        _ = parts.port
    except ValueError:
        raise InvalidUrlError("URL is malformed") from None
    if parts.scheme not in ("http", "https"):
        raise InvalidUrlError("URL must start with http:// or https://")
    if not parts.hostname:
        raise InvalidUrlError("URL has no host")
    if parts.username is not None or parts.password is not None:
        raise InvalidUrlError("URL must not embed credentials (user:pass@host)")
    return url


# TEXT_MODEL_STATUS_* values returned by resolve_text_model_config().
TEXT_MODEL_UNSET = "unset"  # none of the three set: click-only execution may proceed, with a warning
TEXT_MODEL_PARTIAL = "partial"  # some but not all set: refused outright, never a silent partial default
TEXT_MODEL_INVALID_BASE_URL = "invalid_base_url"
TEXT_MODEL_CONFIGURED = "configured"


def resolve_text_model_config(env: dict) -> tuple[str, str | None]:
    """Upstream's own field_text() (model.py) silently defaults TEXT_MODEL_BASE_URL
    to https://api.deepseek.com/v1 and TEXT_MODEL to deepseek-chat the moment
    TEXT_MODEL_API_KEY is set -- so a key alone is enough to make a real, billed
    call to a specific provider the user never named. This skill never lets
    that defaulting happen: TEXT_MODEL_API_KEY, TEXT_MODEL_BASE_URL, and
    TEXT_MODEL must all be set together, explicitly, or none of them at all.
    Returns (status, detail); detail is a safe, bounded string (never a raw
    credential or URL with embedded userinfo) only when status is
    TEXT_MODEL_INVALID_BASE_URL.
    """
    key = (env.get("TEXT_MODEL_API_KEY") or "").strip()
    base_url = (env.get("TEXT_MODEL_BASE_URL") or "").strip()
    model = (env.get("TEXT_MODEL") or "").strip()
    present = (bool(key), bool(base_url), bool(model))
    if not any(present):
        return TEXT_MODEL_UNSET, None
    if not all(present):
        return TEXT_MODEL_PARTIAL, None
    try:
        validate_url(base_url)
    except InvalidUrlError as exc:
        return TEXT_MODEL_INVALID_BASE_URL, str(exc)
    if urlsplit(base_url).scheme != "https":
        return TEXT_MODEL_INVALID_BASE_URL, "TEXT_MODEL_BASE_URL must be HTTPS"
    return TEXT_MODEL_CONFIGURED, None


def safe_error_text(exc: BaseException, limit: int = 200) -> str:
    """A bounded, defense-in-depth error summary: never the full traceback,
    and never any text that looks like it might carry a token/secret. Most
    upstream exceptions already carry clean, body-free messages (see
    model.py's post_json), but this is a backstop against an unexpected
    exception type (e.g. a raw httpx error) carrying request/response text."""
    # Provider/browser exceptions can contain arbitrary page or credential text.
    # A denylist cannot reliably detect it; keep only the exception class.
    return f"{type(exc).__name__} (details redacted; run doctor.py for prerequisites)"[:limit]


@dataclass
class BoundedResult:
    returncode: int
    timed_out: bool


def run_bounded(cmd, *, cwd, env, timeout_seconds, stdin=None) -> BoundedResult:
    """Runs `cmd` in its own process group and enforces a hard wall-clock
    timeout independent of anything the child does internally (a blocked
    predict()/input() call, a stuck browser observation, a hung network
    request). On timeout, kills the *whole process group*, not just the
    direct child, so a `uv run` wrapper or a browser-harness daemon call the
    child spawned cannot outlive this call. Never raises on timeout; returns
    EXIT_TIMEOUT so the caller must handle it explicitly rather than treating
    an un-raised return as success.
    """
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=stdin, start_new_session=True)
    try:
        proc.wait(timeout=timeout_seconds)
        return BoundedResult(returncode=proc.returncode, timed_out=False)
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass  # best effort; the group SIGKILL above should be terminal
        return BoundedResult(returncode=EXIT_TIMEOUT, timed_out=True)
    except BaseException:
        # Ctrl-C reaches the wrapper, not the detached child process group.
        # Stop automation before propagating cancellation or an unexpected error.
        _kill_process_group(proc)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        raise


def _kill_process_group(proc: subprocess.Popen) -> None:
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, OSError):
        return
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass
