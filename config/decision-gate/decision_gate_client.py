#!/usr/bin/env python3
"""Vendorable decision-gate client. Single file, Python stdlib only.

Copy this file into any project (or `import` it if decision-gate's repo path
is on sys.path already) -- it has no dependency on the rest of decision-gate.

Contract: see $NOTES/Homelab/dotfiles/decision-gate.md in the dotfiles repo. Summary:

    POST /v1/decide   {"purpose", "sensitivity", "state", "questions": [...]}
                      -> {"decision_id", "backend", "latency_ms", "cached", "answers"}
    POST /v1/outcome  {"decision_id", "truth": {...}, "source"}
    GET  /v1/report?purpose=...
    GET  /healthz

Fail-open = abstain: any network error, timeout, non-2xx response, or
malformed JSON from the service is reported as an all-abstained decision
(never raised to the caller) so a decision-gate outage degrades a pipeline to
"send everything to the expensive model" rather than crashing it. Call
`decide(..., strict=True)` to get real exceptions instead, e.g. for the CLI.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

DEFAULT_BASE_URL = "http://127.0.0.1:8796"
DEFAULT_TIMEOUT_S = 10.0


class DecisionGateError(RuntimeError):
    pass


def _post(base_url: str, path: str, body: dict, timeout_s: float) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}{path}", data=data, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read(1024 * 1024))


def _get(base_url: str, path: str, timeout_s: float) -> dict:
    req = urllib.request.Request(f"{base_url}{path}", method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read(1024 * 1024))


def _abstained_decision(questions: List[dict]) -> dict:
    answers = {q["id"]: {"choice": None, "p": 0.0, "probs": {}, "abstained": True} for q in questions}
    return {"decision_id": None, "backend": None, "latency_ms": 0.0, "cached": False,
            "answers": answers, "fail_open": True}


def decide(purpose: str, sensitivity: str, state: Any, questions: List[dict], *,
           base_url: str = DEFAULT_BASE_URL, timeout_s: float = DEFAULT_TIMEOUT_S, strict: bool = False) -> dict:
    """Asks decision-gate to answer `questions` about `state`.

    On any failure (network, timeout, bad response) returns an all-abstained
    decision with `fail_open: True` set, unless `strict=True`, in which case
    a DecisionGateError is raised instead. Callers should treat `abstained`
    per-question exactly as they would an abstain from a live call: route to
    the expensive model / a human.
    """
    body = {"purpose": purpose, "sensitivity": sensitivity, "state": state, "questions": questions}
    try:
        return _post(base_url, "/v1/decide", body, timeout_s)
    except Exception as exc:  # noqa: BLE001 - fail-open must catch everything, including non-HTTP errors
        if strict:
            raise DecisionGateError(str(exc)) from exc
        return _abstained_decision(questions)


def outcome(decision_id: str, truth: Dict[str, Any], source: str, *,
            base_url: str = DEFAULT_BASE_URL, timeout_s: float = DEFAULT_TIMEOUT_S, strict: bool = False) -> Optional[dict]:
    """Records what actually happened for shadow evaluation. Best-effort: a
    failure here must never break the caller's pipeline (the decision was
    already acted on), so it silently returns None unless `strict=True`.
    """
    body = {"decision_id": decision_id, "truth": truth, "source": source}
    try:
        return _post(base_url, "/v1/outcome", body, timeout_s)
    except Exception as exc:  # noqa: BLE001
        if strict:
            raise DecisionGateError(str(exc)) from exc
        return None


def report(purpose: Optional[str] = None, *, base_url: str = DEFAULT_BASE_URL,
           timeout_s: float = DEFAULT_TIMEOUT_S, strict: bool = False) -> Optional[dict]:
    path = "/v1/report" + (f"?purpose={urllib.parse.quote(purpose)}" if purpose else "")
    try:
        return _get(base_url, path, timeout_s)
    except Exception as exc:  # noqa: BLE001
        if strict:
            raise DecisionGateError(str(exc)) from exc
        return None


def healthz(*, base_url: str = DEFAULT_BASE_URL, timeout_s: float = 3.0) -> bool:
    try:
        resp = _get(base_url, "/healthz", timeout_s)
        return resp.get("status") == "ok"
    except Exception:  # noqa: BLE001 - a health check that can raise isn't one
        return False
