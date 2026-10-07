"""decision-gate HTTP service. Stdlib only (http.server), one process, one SQLite store.

Routing and request handling live here; policy/scoring/storage logic is in
core.py (unit tested with fakes) and real network calls are in backends.py.
Every code path returns JSON; no path ever raises past the handler.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from . import backends, core

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8796

MAX_BODY_BYTES = 256 * 1024
MAX_PURPOSE_LEN = 128
MAX_QUESTIONS = 16
MAX_OPTIONS = 32
PURPOSE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,%d}$" % (MAX_PURPOSE_LEN - 1))


class RequestInvalid(ValueError):
    pass


def validate_decide_request(body):
    if not isinstance(body, dict):
        raise RequestInvalid("body must be a JSON object")
    purpose = body.get("purpose")
    if not isinstance(purpose, str) or not PURPOSE_RE.match(purpose):
        raise RequestInvalid("purpose must be a short alphanumeric/_/- token")
    sensitivity = body.get("sensitivity")
    if sensitivity not in core.VALID_SENSITIVITY:
        raise RequestInvalid("sensitivity must be private|internal|public")
    if "state" not in body:
        raise RequestInvalid("state is required")
    state = body["state"]
    questions = body.get("questions")
    if not isinstance(questions, list) or not (1 <= len(questions) <= MAX_QUESTIONS):
        raise RequestInvalid(f"questions must be a list of 1..{MAX_QUESTIONS} entries")
    seen_ids = set()
    normalized = []
    for q in questions:
        if not isinstance(q, dict):
            raise RequestInvalid("each question must be an object")
        qid = q.get("id")
        kind = q.get("kind")
        prompt = q.get("prompt")
        if not isinstance(qid, str) or not qid or qid in seen_ids:
            raise RequestInvalid("question id must be a unique non-empty string")
        if kind not in core.VALID_QUESTION_KINDS:
            raise RequestInvalid("question kind must be choice|bool")
        if not isinstance(prompt, str) or not prompt:
            raise RequestInvalid("question prompt must be a non-empty string")
        seen_ids.add(qid)
        entry = {"id": qid, "kind": kind, "prompt": prompt}
        if kind == "choice":
            options = q.get("options")
            if not isinstance(options, list) or not (2 <= len(options) <= MAX_OPTIONS) or \
                    not all(isinstance(o, str) and o for o in options) or len(set(options)) != len(options):
                raise RequestInvalid("choice question needs 2+ unique non-empty string options")
            entry["options"] = options
        normalized.append(entry)
    return {"purpose": purpose, "sensitivity": sensitivity, "state": state, "questions": normalized}


def validate_outcome_request(body):
    if not isinstance(body, dict):
        raise RequestInvalid("body must be a JSON object")
    decision_id = body.get("decision_id")
    if not isinstance(decision_id, str) or not decision_id:
        raise RequestInvalid("decision_id is required")
    truth = body.get("truth")
    if not isinstance(truth, dict) or not truth:
        raise RequestInvalid("truth must be a non-empty object")
    source = body.get("source")
    if source not in core.VALID_SOURCES:
        raise RequestInvalid("source must be opus|human|agent")
    return {"decision_id": decision_id, "truth": truth, "source": source}


class Deps:
    """Everything a request handler needs, injected so tests can run without
    network access or the real filesystem config locations.
    """

    def __init__(self, *, store, policy_loader, jev_key_loader, jev_run=backends.jev_run,
                 ollama_run=backends.ollama_run, now=time.time, lock=None):
        self.store = store
        self.policy_loader = policy_loader  # () -> (policy, error)
        self.jev_key_loader = jev_key_loader  # () -> str | None
        self.jev_run = jev_run
        self.ollama_run = ollama_run
        self.now = now
        self.lock = lock or threading.Lock()


def handle_decide(deps: Deps, body: dict) -> dict:
    req = validate_decide_request(body)
    purpose, sensitivity, state, questions = req["purpose"], req["sensitivity"], req["state"], req["questions"]

    policy, policy_error = deps.policy_loader()
    if policy_error is not None:
        # An invalid/unreadable policy file must never silently fall back to
        # defaults: every question abstains rather than running on a config
        # nobody validated.
        return _abstain_all_response(purpose, sensitivity, questions, backend=None, latency_ms=0.0,
                                      deps=deps, reason="policy_invalid")

    effective = core.resolve_policy(policy, purpose)
    if not core.sensitivity_allowed(effective, sensitivity):
        return _abstain_all_response(purpose, sensitivity, questions, backend=None, latency_ms=0.0,
                                      deps=deps, reason="sensitivity_not_allowed")

    backend, overridden = core.enforce_privacy(effective, sensitivity)

    model = backends.JEV_MODEL if backend == "jev" else backends.OLLAMA_MODEL
    key = core.cache_key(purpose, state, questions, f"{backend}:{model}")

    started = time.monotonic()
    with deps.lock:
        cached_entry = deps.store.cache_get(key, now=deps.now())
    if cached_entry is not None:
        answers = _score_answers(questions, cached_entry["answers"], effective["min_p"])
        latency_ms = (time.monotonic() - started) * 1000.0
        decision_id = core.new_decision_id()
        with deps.lock:
            deps.store.record_decision(decision_id, purpose, sensitivity, backend, answers)
            core.append_ledger(core.default_state_dir(), core.build_ledger_event(
                kind="decide", purpose=purpose, sensitivity=sensitivity, backend=backend, model=model,
                latency_ms=latency_ms, cached=True, abstained=any(a["abstained"] for a in answers.values()),
                input_tokens=0, output_tokens=0, estimated_cost_usd=0.0, cost_source="cache",
                question_count=len(questions), overridden_for_privacy=overridden,
            ))
        return {"decision_id": decision_id, "backend": backend, "latency_ms": round(latency_ms, 1),
                "cached": True, "answers": answers}

    # Budget check (per purpose, per UTC day).
    day = time.strftime("%Y-%m-%d", time.gmtime(deps.now()))
    with deps.lock:
        calls_today = deps.store.budget_count(purpose, day)
    if calls_today >= effective["daily_call_cap"]:
        return _abstain_all_response(purpose, sensitivity, questions, backend=backend, latency_ms=0.0,
                                      deps=deps, reason="budget_exhausted", overridden=overridden)

    timeout_s = core.DEFAULT_JEV_TIMEOUT_S if backend == "jev" else core.DEFAULT_OLLAMA_TIMEOUT_S
    try:
        if backend == "jev":
            api_key = deps.jev_key_loader()
            result = deps.jev_run(questions, state, api_key, timeout_s)
        else:
            result = deps.ollama_run(questions, state, timeout_s)
        with deps.lock:
            deps.store.budget_increment(purpose, day)
    except backends.BackendError:
        with deps.lock:
            deps.store.budget_increment(purpose, day)
        latency_ms = (time.monotonic() - started) * 1000.0
        return _abstain_all_response(purpose, sensitivity, questions, backend=backend, latency_ms=latency_ms,
                                      deps=deps, reason="backend_error", overridden=overridden)

    latency_ms = (time.monotonic() - started) * 1000.0
    with deps.lock:
        deps.store.cache_put(key, result.answers, backend, result.model, effective["cache_ttl_s"], now=deps.now())
        deps.store.cache_prune(now=deps.now())

    answers = _score_answers(questions, result.answers, effective["min_p"])
    decision_id = core.new_decision_id()
    abstained_any = any(a["abstained"] for a in answers.values())
    with deps.lock:
        deps.store.record_decision(decision_id, purpose, sensitivity, backend, answers)
        core.append_ledger(core.default_state_dir(), core.build_ledger_event(
            kind="decide", purpose=purpose, sensitivity=sensitivity, backend=backend, model=result.model,
            latency_ms=latency_ms, cached=False, abstained=abstained_any,
            input_tokens=result.input_tokens, output_tokens=result.output_tokens,
            estimated_cost_usd=result.estimated_cost_usd, cost_source=result.cost_source,
            question_count=len(questions), overridden_for_privacy=overridden,
        ))
    return {"decision_id": decision_id, "backend": backend, "latency_ms": round(latency_ms, 1),
            "cached": False, "answers": answers}


def _score_answers(questions, raw_answers, min_p):
    answers = {}
    for q in questions:
        qid = q["id"]
        raw = raw_answers.get(qid) or {}
        probs = raw.get("probs") or {}
        choice_label, p, abstained = core.decide_answer(probs, min_p)
        choice = choice_label
        if q["kind"] == "bool" and choice_label is not None:
            choice = choice_label == "true"
        answers[qid] = {"choice": choice, "p": round(p, 4), "probs": {k: round(v, 4) for k, v in probs.items()},
                         "abstained": abstained}
    return answers


def _abstain_all_response(purpose, sensitivity, questions, *, backend, latency_ms, deps, reason, overridden=False):
    answers = {q["id"]: {"choice": None, "p": 0.0, "probs": {}, "abstained": True} for q in questions}
    decision_id = core.new_decision_id()
    with deps.lock:
        deps.store.record_decision(decision_id, purpose, sensitivity, backend, answers)
        core.append_ledger(core.default_state_dir(), core.build_ledger_event(
            kind="decide", purpose=purpose, sensitivity=sensitivity, backend=backend, model=None,
            latency_ms=latency_ms, cached=False, abstained=True, input_tokens=0, output_tokens=0,
            estimated_cost_usd=0.0, cost_source="unknown", question_count=len(questions),
            overridden_for_privacy=overridden,
        ))
    return {"decision_id": decision_id, "backend": backend, "latency_ms": round(latency_ms, 1),
            "cached": False, "answers": answers, "reason": reason}


def handle_outcome(deps: Deps, body: dict) -> dict:
    req = validate_outcome_request(body)
    with deps.lock:
        decision = deps.store.get_decision(req["decision_id"])
    if decision is None:
        raise RequestInvalid("unknown decision_id")
    agreement = None
    matched = False
    all_correct = True
    for qid, truth_value in req["truth"].items():
        answer = decision["answers"].get(qid)
        if not isinstance(answer, dict) or answer.get("abstained"):
            continue
        matched = True
        if str(answer.get("choice")) != str(truth_value) and not (
            isinstance(truth_value, bool) and isinstance(answer.get("choice"), bool) and answer.get("choice") == truth_value
        ):
            all_correct = False
    if matched:
        agreement = all_correct
    with deps.lock:
        deps.store.record_outcome(req["decision_id"], req["truth"], req["source"])
        core.append_ledger(core.default_state_dir(), core.build_ledger_event(
            kind="outcome", purpose=decision["purpose"], source=req["source"], agreement=agreement,
        ))
    return {"ok": True, "decision_id": req["decision_id"], "agreement": agreement}


def handle_report(deps: Deps, purpose: Optional[str]) -> dict:
    with deps.lock:
        rows = deps.store.report_rows(purpose)
    report = core.compute_report(rows)
    if purpose is not None:
        return {"purpose": purpose, **report.get(purpose, core._summarize_pairs([], core.REPORT_THRESHOLDS))}
    return {"purposes": report}


# ---------------------------------------------------------------------------
# HTTP wiring
# ---------------------------------------------------------------------------

def make_handler_class(deps: Deps):
    class Handler(BaseHTTPRequestHandler):
        server_version = "decision-gate/1"

        def log_message(self, fmt, *args):  # noqa: A002 - stdlib signature
            pass  # metadata-only elsewhere; never log request bodies to stderr by default

        def _send_json(self, status, payload):
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json_body(self):
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length <= 0 or length > MAX_BODY_BYTES:
                raise RequestInvalid("missing or oversized request body")
            raw = self.rfile.read(length)
            try:
                return json.loads(raw)
            except ValueError as exc:
                raise RequestInvalid("body must be valid JSON") from exc

        def do_GET(self):
            from urllib.parse import urlsplit, parse_qs

            parts = urlsplit(self.path)
            if parts.path == "/healthz":
                self._send_json(200, {"status": "ok", "version": core.API_VERSION})
                return
            if parts.path == "/v1/report":
                qs = parse_qs(parts.query)
                purpose = (qs.get("purpose") or [None])[0]
                try:
                    self._send_json(200, handle_report(deps, purpose))
                except Exception:  # noqa: BLE001 - never leak internals to the client
                    self._send_json(500, {"error": "internal_error"})
                return
            self._send_json(404, {"error": "not_found"})

        def do_POST(self):
            if self.path == "/v1/decide":
                try:
                    body = self._read_json_body()
                    self._send_json(200, handle_decide(deps, body))
                except RequestInvalid as exc:
                    self._send_json(400, {"error": str(exc)})
                except Exception:  # noqa: BLE001
                    self._send_json(500, {"error": "internal_error"})
                return
            if self.path == "/v1/outcome":
                try:
                    body = self._read_json_body()
                    self._send_json(200, handle_outcome(deps, body))
                except RequestInvalid as exc:
                    self._send_json(400, {"error": str(exc)})
                except Exception:  # noqa: BLE001
                    self._send_json(500, {"error": "internal_error"})
                return
            self._send_json(404, {"error": "not_found"})

    return Handler


def build_real_deps(env=None):
    env = env or os.environ
    store = core.Store(core.default_state_dir(env))

    def policy_loader():
        return core.load_policy(core.default_policy_path(env), env)

    def jev_key_loader():
        path = core.default_jev_key_path(env)
        try:
            raw = path.read_text(encoding="utf-8").strip()
            return raw or None
        except OSError:
            return None

    return Deps(store=store, policy_loader=policy_loader, jev_key_loader=jev_key_loader)


def run(host=DEFAULT_HOST, port=DEFAULT_PORT, deps: Optional[Deps] = None):
    deps = deps or build_real_deps()
    handler_cls = make_handler_class(deps)
    httpd = ThreadingHTTPServer((host, port), handler_cls)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        deps.store.close()


if __name__ == "__main__":
    run()
