#!/usr/bin/env python3
"""Opt-in, read-only browser enrichment for the local LLM usage report.

This module consumes already-approved CDP/page data. It does not open a browser,
send cookies, persist responses, or perform account actions.
"""
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


class MutationDenied(ValueError):
    """Raised when a browser operation could mutate an account."""


_MUTATING_PATHS = re.compile(r"/(?:checkout|buy|purchase|reset|reload|top[_-]?up|plan|billing|settings/(?:account|billing))", re.I)
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def assert_read_only(method, url):
    """Allow only safe navigation/reads; deliberately reject mutation-shaped URLs."""
    if str(method).upper() != "GET" or _MUTATING_PATHS.search(urlsplit(str(url)).path):
        raise MutationDenied("browser inspection permits GET reads only")


def _source_category(url):
    host = (urlsplit(url).hostname or "unknown").lower()
    if host in {"claude.ai", "console.anthropic.com"}:
        return "anthropic usage page"
    if host in {"chatgpt.com", "chat.openai.com", "platform.openai.com"}:
        return "openai usage page"
    if host == "platform.deepseek.com":
        return "deepseek usage page"
    return "provider usage page"


def _network_values(responses):
    values = {}
    for response in responses or []:
        if not isinstance(response, dict):
            continue
        body = response.get("body")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except (TypeError, ValueError):
                continue
        if not isinstance(body, dict):
            continue
        for key, aliases in {
            "reset_expiry": ("reset_expiry", "resetExpiry", "reset_at"),
            "reset_count": ("reset_count", "resetCount", "available_count"),
        }.items():
            for alias in aliases:
                if alias in body and isinstance(body[alias], (str, int, float)) and not isinstance(body[alias], bool):
                    values[key] = body[alias]
                    break
    return values


def inspect_snapshot(rendered, network_responses, source_url, observed_at, now):
    """Normalize fixture-equivalent rendered/CDP observations without sensitive data."""
    rendered = rendered if isinstance(rendered, dict) else {}
    values = {}
    expiry = rendered.get("reset_expiry") or rendered.get("resetExpiry")
    if isinstance(expiry, str) and expiry:
        values["reset_expiry"] = expiry
    values.update({key: value for key, value in _network_values(network_responses).items() if key not in values})
    count = rendered.get("reset_count") or rendered.get("resetCount")
    if isinstance(count, (int, float)) and not isinstance(count, bool):
        values["reset_count"] = count
    if rendered.get("offer") or rendered.get("offer_present") is True:
        values["offer_present"] = True
    status = "ok"
    reason = None
    auth_failure = any(isinstance(response, dict) and response.get("status") in (401, 403)
                       for response in (network_responses or []))
    if rendered.get("logged_in") is False or auth_failure:
        status, reason = "unavailable", "authenticated browser session is logged out"
    elif not values:
        status, reason = "unavailable", "usage page exposed no recognized fields"
    result = {
        "status": status,
        "source": "authenticated browser rendered page",
        "source_category": _source_category(source_url),
        "observed_at": observed_at,
        "age_seconds": max(0, now - observed_at),
        "confidence": "medium",
        "values": values,
    }
    if reason:
        result["reason"] = reason
    return result


def write_cache(path, snapshot):
    """Atomically write only the normalized snapshot with restrictive permissions."""
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=".llm-browser-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(snapshot, stream, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_cache(path, now, max_age):
    try:
        path = Path(path)
        if path.stat().st_mode & 0o077:
            return None
        with path.open(encoding="utf-8") as stream:
            snapshot = json.load(stream)
        observed = snapshot.get("observed_at")
        if not isinstance(observed, (int, float)) or now - observed > max_age:
            return None
        snapshot["age_seconds"] = max(0, now - observed)
        return snapshot
    except (OSError, ValueError, TypeError):
        return None
