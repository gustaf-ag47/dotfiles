"""Pure logic for decision-gate: policy, cache keys, scoring, store, report.

No network access happens in this module. Backends (scripts/decision_gate/backends.py)
are injected as plain callables everywhere so this module -- and the service
built on top of it -- can be unit tested with fakes.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import time
import uuid
from pathlib import Path

SCHEMA_POLICY = "decision-gate-policy.v1"
SCHEMA_EVENT = "decision-gate-event.v1"
API_VERSION = "v1"

VALID_SENSITIVITY = ("private", "internal", "public")
VALID_BACKENDS = ("jev", "ollama")
VALID_QUESTION_KINDS = ("choice", "bool")
VALID_EVENT_KINDS = ("decide", "outcome")
VALID_SOURCES = ("opus", "human", "agent")

DEFAULT_MIN_P = 0.8
DEFAULT_CACHE_TTL_S = 86400
DEFAULT_DAILY_CALL_CAP = 200
DEFAULT_JEV_TIMEOUT_S = 3.0
DEFAULT_OLLAMA_TIMEOUT_S = 8.0

REPORT_THRESHOLDS = (0.8, 0.9, 0.95)


# ---------------------------------------------------------------------------
# XDG paths
# ---------------------------------------------------------------------------

def xdg_config_home(env=None):
    env = env or os.environ
    return Path(env.get("XDG_CONFIG_HOME") or Path(env.get("HOME", str(Path.home()))) / ".config")


def xdg_state_home(env=None):
    env = env or os.environ
    return Path(env.get("XDG_STATE_HOME") or Path(env.get("HOME", str(Path.home()))) / ".local" / "state")


def default_policy_path(env=None):
    env = env or os.environ
    override = env.get("DECISION_GATE_POLICY_FILE")
    if override:
        return Path(override)
    return xdg_config_home(env) / "decision-gate" / "policy.json"


def default_state_dir(env=None):
    env = env or os.environ
    override = env.get("DECISION_GATE_STATE_DIR")
    if override:
        return Path(override)
    return xdg_state_home(env) / "decision-gate"


def default_jev_key_path(env=None):
    env = env or os.environ
    override = env.get("PI_JEV_KEY_FILE")
    if override:
        return Path(override)
    return xdg_config_home(env) / "jev" / "api-key"


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

DEFAULT_PURPOSE_POLICY = {
    "backend": "ollama",
    "allow_external": False,
    "allowed_sensitivity": list(VALID_SENSITIVITY),
    "min_p": DEFAULT_MIN_P,
    "cache_ttl_s": DEFAULT_CACHE_TTL_S,
    "daily_call_cap": DEFAULT_DAILY_CALL_CAP,
}


class PolicyError(ValueError):
    pass


def _validate_purpose_entry(entry):
    if not isinstance(entry, dict):
        raise PolicyError("purpose policy must be an object")
    backend = entry.get("backend", DEFAULT_PURPOSE_POLICY["backend"])
    if backend not in VALID_BACKENDS:
        raise PolicyError(f"unknown backend: {backend!r}")
    allow_external = entry.get("allow_external", False)
    if not isinstance(allow_external, bool):
        raise PolicyError("allow_external must be a bool")
    allowed = entry.get("allowed_sensitivity", list(VALID_SENSITIVITY))
    if not isinstance(allowed, list) or not all(s in VALID_SENSITIVITY for s in allowed):
        raise PolicyError("allowed_sensitivity must be a list of private|internal|public")
    min_p = entry.get("min_p", DEFAULT_MIN_P)
    if not isinstance(min_p, (int, float)) or not (0 <= min_p <= 1):
        raise PolicyError("min_p must be a number in [0, 1]")
    cache_ttl_s = entry.get("cache_ttl_s", DEFAULT_CACHE_TTL_S)
    if not isinstance(cache_ttl_s, (int, float)) or cache_ttl_s < 0:
        raise PolicyError("cache_ttl_s must be a non-negative number")
    daily_call_cap = entry.get("daily_call_cap", DEFAULT_DAILY_CALL_CAP)
    if not isinstance(daily_call_cap, (int, float)) or daily_call_cap <= 0:
        raise PolicyError("daily_call_cap must be a positive number")
    return {
        "backend": backend,
        "allow_external": allow_external,
        "allowed_sensitivity": allowed,
        "min_p": float(min_p),
        "cache_ttl_s": float(cache_ttl_s),
        "daily_call_cap": float(daily_call_cap),
    }


def validate_policy(raw):
    """Validates a parsed policy document. Raises PolicyError on anything wrong.

    A policy file that fails to parse or validate must never be silently
    treated as "no policy" -- callers should abstain rather than run with
    implicit defaults they never configured. See resolve_policy()'s caller.
    """
    if not isinstance(raw, dict):
        raise PolicyError("policy must be a JSON object")
    out = {"schema": SCHEMA_POLICY, "default": dict(DEFAULT_PURPOSE_POLICY), "purposes": {}}
    if "default" in raw:
        out["default"] = _validate_purpose_entry(raw["default"])
    purposes = raw.get("purposes", {})
    if not isinstance(purposes, dict):
        raise PolicyError("purposes must be an object")
    for name, entry in purposes.items():
        if not isinstance(name, str) or not name:
            raise PolicyError("purpose keys must be non-empty strings")
        out["purposes"][name] = _validate_purpose_entry(entry)
    return out


def load_policy(path=None, env=None):
    """Loads+validates the policy file. A missing file is fine (built-in defaults).

    Returns (policy, error) -- error is None on success, else a short reason
    code. Never raises.
    """
    path = path or default_policy_path(env)
    try:
        raw_text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"schema": SCHEMA_POLICY, "default": dict(DEFAULT_PURPOSE_POLICY), "purposes": {}}, None
    except OSError:
        return None, "policy_unreadable"
    try:
        parsed = json.loads(raw_text)
    except ValueError:
        return None, "policy_malformed"
    try:
        return validate_policy(parsed), None
    except PolicyError:
        return None, "policy_invalid"


def resolve_policy(policy, purpose):
    """Merges the purpose-specific policy over the default. Pure dict merge, no privacy logic here."""
    base = dict(policy.get("default", DEFAULT_PURPOSE_POLICY))
    base.update(policy.get("purposes", {}).get(purpose, {}))
    return base


def enforce_privacy(effective, sensitivity):
    """Hard rule, enforced in code regardless of what the policy file says:
    `private` never reaches `jev` unless the purpose's policy explicitly sets
    `allow_external: true`. When the policy would route private data to jev
    without that explicit flag, this reroutes to ollama rather than abstaining
    -- decision-gate stays usable, it just never leaks private state
    externally. Returns (backend, overridden: bool).
    """
    backend = effective.get("backend", "ollama")
    if sensitivity == "private" and backend == "jev" and not effective.get("allow_external", False):
        return "ollama", True
    return backend, False


def sensitivity_allowed(effective, sensitivity):
    return sensitivity in effective.get("allowed_sensitivity", VALID_SENSITIVITY)


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------

def cache_key(purpose, state, questions, backend_version):
    """sha256(purpose + state + questions + backend version), per the contract.

    `questions` is canonicalized (sorted keys, compact separators) so
    equivalent JSON that differs only in key order/whitespace still hits the
    cache.
    """
    state_str = state if isinstance(state, str) else json.dumps(state, sort_keys=True, separators=(",", ":"))
    questions_str = json.dumps(questions, sort_keys=True, separators=(",", ":"))
    payload = "\u0000".join([purpose, state_str, questions_str, str(backend_version)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def softmax(logprobs):
    """logprobs: dict[label -> natural-log probability (possibly unnormalized)].
    Returns a probability dict that sums to 1. Empty input -> empty output.
    """
    if not logprobs:
        return {}
    max_lp = max(logprobs.values())
    exps = {k: math.exp(v - max_lp) for k, v in logprobs.items()}
    total = sum(exps.values())
    if total <= 0:
        n = len(exps)
        return {k: 1.0 / n for k in exps}
    return {k: v / total for k, v in exps.items()}


def decide_answer(probs, min_p):
    """Given a label->probability dict, picks the top label and decides abstention.

    Returns (choice_label, p, abstained). An empty `probs` always abstains
    with choice=None, p=0.0 (parse failure upstream).
    """
    if not probs:
        return None, 0.0, True
    choice = max(probs, key=probs.get)
    p = probs[choice]
    return choice, p, p < min_p


# ---------------------------------------------------------------------------
# Decision ids
# ---------------------------------------------------------------------------

def new_decision_id():
    return f"dg_{uuid.uuid4().hex}"


def now_iso(ts=None):
    ts = time.time() if ts is None else ts
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


# ---------------------------------------------------------------------------
# Ledger (metadata-only, JSONL) -- same shape of guarantee as the Jev pilot:
# never contains raw state/prompt/answer text, only bounded labels/numbers.
# ---------------------------------------------------------------------------

_SAFE_TOKEN_MAX = 128


def _safe_token(value):
    if not isinstance(value, str) or not value or len(value) > _SAFE_TOKEN_MAX:
        return None
    for ch in value:
        if not (ch.isalnum() or ch in "_.:-"):
            return None
    return value


def build_ledger_event(*, kind, purpose, sensitivity=None, backend=None, model=None, latency_ms=None,
                        cached=None, abstained=None, input_tokens=None, output_tokens=None,
                        estimated_cost_usd=None, cost_source=None, question_count=None,
                        overridden_for_privacy=None, source=None, agreement=None, ts=None):
    """Builds one metadata-only ledger line. Raises ValueError on an invalid kind."""
    if kind not in VALID_EVENT_KINDS:
        raise ValueError(f"invalid ledger event kind: {kind!r}")
    event = {
        "schema": SCHEMA_EVENT,
        "timestamp": now_iso(ts),
        "kind": kind,
        "purpose": _safe_token(purpose),
    }
    if sensitivity is not None:
        event["sensitivity"] = sensitivity if sensitivity in VALID_SENSITIVITY else None
    if backend is not None:
        event["backend"] = backend if backend in VALID_BACKENDS else None
    if model is not None:
        event["model"] = _safe_token(model)
    if latency_ms is not None:
        event["latency_ms"] = float(latency_ms) if isinstance(latency_ms, (int, float)) else None
    if cached is not None:
        event["cached"] = bool(cached)
    if abstained is not None:
        event["abstained"] = bool(abstained)
    if input_tokens is not None:
        event["input_tokens"] = int(input_tokens) if isinstance(input_tokens, (int, float)) else None
    if output_tokens is not None:
        event["output_tokens"] = int(output_tokens) if isinstance(output_tokens, (int, float)) else None
    if estimated_cost_usd is not None:
        event["estimated_cost_usd"] = float(estimated_cost_usd) if isinstance(estimated_cost_usd, (int, float)) else None
    if cost_source is not None:
        event["cost_source"] = _safe_token(cost_source)
    if question_count is not None:
        event["question_count"] = int(question_count) if isinstance(question_count, (int, float)) else None
    if overridden_for_privacy is not None:
        event["overridden_for_privacy"] = bool(overridden_for_privacy)
    if source is not None:
        event["source"] = source if source in VALID_SOURCES else None
    if agreement is not None:
        event["agreement"] = bool(agreement) if isinstance(agreement, bool) else None
    return event


def ledger_path(state_dir):
    return Path(state_dir) / "events.jsonl"


def append_ledger(state_dir, event):
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        os.chmod(state_dir, 0o700)
    except OSError:
        pass
    path = ledger_path(state_dir)
    line = json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# Store: decisions, outcomes, cache -- SQLite (stdlib), state-dir local.
# Stores STRUCTURED answers only (choice/p/probs/abstained per question id),
# never the raw `state` text that was classified.
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    purpose TEXT NOT NULL,
    sensitivity TEXT,
    backend TEXT,
    created_at TEXT NOT NULL,
    answers_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outcomes (
    decision_id TEXT NOT NULL,
    truth_json TEXT NOT NULL,
    source TEXT,
    recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cache (
    cache_key TEXT PRIMARY KEY,
    answers_json TEXT NOT NULL,
    backend TEXT NOT NULL,
    model TEXT,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS budget (
    purpose TEXT NOT NULL,
    day TEXT NOT NULL,
    calls INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (purpose, day)
);
CREATE INDEX IF NOT EXISTS idx_outcomes_decision ON outcomes(decision_id);
"""


class Store:
    """Thin SQLite wrapper. One connection per Store instance; callers (the
    single-threaded-per-request service) are responsible for serializing
    writes across threads via a lock -- see service.py.
    """

    def __init__(self, state_dir):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        try:
            os.chmod(self.state_dir, 0o700)
        except OSError:
            pass
        self.db_path = self.state_dir / "store.sqlite3"
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass

    def close(self):
        self.conn.close()

    # -- cache ---------------------------------------------------------
    def cache_get(self, key, now=None):
        now = time.time() if now is None else now
        row = self.conn.execute(
            "SELECT answers_json, backend, model, expires_at FROM cache WHERE cache_key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        answers_json, backend, model, expires_at = row
        if expires_at <= now:
            self.conn.execute("DELETE FROM cache WHERE cache_key = ?", (key,))
            self.conn.commit()
            return None
        return {"answers": json.loads(answers_json), "backend": backend, "model": model}

    def cache_put(self, key, answers, backend, model, ttl_s, now=None):
        now = time.time() if now is None else now
        self.conn.execute(
            "INSERT OR REPLACE INTO cache (cache_key, answers_json, backend, model, expires_at) VALUES (?, ?, ?, ?, ?)",
            (key, json.dumps(answers), backend, model, now + ttl_s),
        )
        self.conn.commit()

    def cache_prune(self, now=None, max_entries=5000):
        now = time.time() if now is None else now
        self.conn.execute("DELETE FROM cache WHERE expires_at <= ?", (now,))
        count = self.conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        if count > max_entries:
            excess = count - max_entries
            self.conn.execute(
                "DELETE FROM cache WHERE cache_key IN "
                "(SELECT cache_key FROM cache ORDER BY expires_at ASC LIMIT ?)",
                (excess,),
            )
        self.conn.commit()

    # -- budget ----------------------------------------------------------
    def budget_count(self, purpose, day):
        row = self.conn.execute(
            "SELECT calls FROM budget WHERE purpose = ? AND day = ?", (purpose, day)
        ).fetchone()
        return row[0] if row else 0

    def budget_increment(self, purpose, day):
        self.conn.execute(
            "INSERT INTO budget (purpose, day, calls) VALUES (?, ?, 1) "
            "ON CONFLICT(purpose, day) DO UPDATE SET calls = calls + 1",
            (purpose, day),
        )
        self.conn.commit()

    # -- decisions / outcomes --------------------------------------------
    def record_decision(self, decision_id, purpose, sensitivity, backend, answers, ts=None):
        self.conn.execute(
            "INSERT OR REPLACE INTO decisions (decision_id, purpose, sensitivity, backend, created_at, answers_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (decision_id, purpose, sensitivity, backend, now_iso(ts), json.dumps(answers)),
        )
        self.conn.commit()

    def get_decision(self, decision_id):
        row = self.conn.execute(
            "SELECT purpose, sensitivity, backend, answers_json FROM decisions WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        if row is None:
            return None
        purpose, sensitivity, backend, answers_json = row
        return {"purpose": purpose, "sensitivity": sensitivity, "backend": backend, "answers": json.loads(answers_json)}

    def record_outcome(self, decision_id, truth, source, ts=None):
        self.conn.execute(
            "INSERT INTO outcomes (decision_id, truth_json, source, recorded_at) VALUES (?, ?, ?, ?)",
            (decision_id, json.dumps(truth), source, now_iso(ts)),
        )
        self.conn.commit()

    def report_rows(self, purpose=None):
        """Yields (purpose, answers_json, truth_json) for every decision that has at least one outcome."""
        sql = (
            "SELECT d.purpose, d.answers_json, o.truth_json FROM decisions d "
            "JOIN outcomes o ON o.decision_id = d.decision_id"
        )
        params = ()
        if purpose is not None:
            sql += " WHERE d.purpose = ?"
            params = (purpose,)
        return self.conn.execute(sql, params).fetchall()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _compare(choice, truth_value):
    """Equality that treats JSON bool/string truth values sanely against a stored choice."""
    if isinstance(truth_value, bool) and isinstance(choice, bool):
        return choice == truth_value
    if isinstance(truth_value, bool):
        return str(choice).lower() == str(truth_value).lower()
    return str(choice) == str(truth_value)


def compute_report(rows, thresholds=REPORT_THRESHOLDS):
    """rows: iterable of (purpose, answers_json_str, truth_json_str).

    Returns {purpose: {n, abstain_rate, agreement, by_question: {...}, thresholds: {t: {coverage, precision}}}}.
    """
    by_purpose = {}
    for purpose, answers_json, truth_json in rows:
        try:
            answers = json.loads(answers_json)
            truth = json.loads(truth_json)
        except ValueError:
            continue
        bucket = by_purpose.setdefault(purpose, {"pairs": [], "by_question": {}})
        for qid, truth_value in truth.items():
            answer = answers.get(qid)
            if not isinstance(answer, dict):
                continue
            p = answer.get("p")
            abstained = bool(answer.get("abstained"))
            choice = answer.get("choice")
            correct = (not abstained) and _compare(choice, truth_value)
            pair = {"qid": qid, "p": p, "abstained": abstained, "correct": correct}
            bucket["pairs"].append(pair)
            bucket["by_question"].setdefault(qid, []).append(pair)

    report = {}
    for purpose, bucket in by_purpose.items():
        report[purpose] = _summarize_pairs(bucket["pairs"], thresholds)
        report[purpose]["by_question"] = {
            qid: _summarize_pairs(pairs, thresholds) for qid, pairs in bucket["by_question"].items()
        }
    return report


def _summarize_pairs(pairs, thresholds):
    n = len(pairs)
    if n == 0:
        return {"n": 0, "abstain_rate": None, "agreement": None,
                "thresholds": {str(t): {"coverage": None, "precision": None} for t in thresholds}}
    abstained_n = sum(1 for p in pairs if p["abstained"])
    answered = [p for p in pairs if not p["abstained"]]
    agreement = (sum(1 for p in answered if p["correct"]) / len(answered)) if answered else None
    out_thresholds = {}
    for t in thresholds:
        at_or_above = [p for p in pairs if (not p["abstained"]) and isinstance(p["p"], (int, float)) and p["p"] >= t]
        coverage = len(at_or_above) / n
        precision = (sum(1 for p in at_or_above if p["correct"]) / len(at_or_above)) if at_or_above else None
        out_thresholds[str(t)] = {"coverage": round(coverage, 4), "precision": (round(precision, 4) if precision is not None else None)}
    return {
        "n": n,
        "abstain_rate": round(abstained_n / n, 4),
        "agreement": (round(agreement, 4) if agreement is not None else None),
        "thresholds": out_thresholds,
    }
