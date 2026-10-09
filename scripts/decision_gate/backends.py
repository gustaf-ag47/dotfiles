"""Real backends: jev (TypeSafe System One, direct HTTP) and ollama (local).

Both expose the same shape: `run(questions, state, timeout_s) -> BackendResult`.
Both raise BackendTimeout/BackendError rather than returning partial data, so
the caller (service.py) always has one abstain path. No caching, policy, or
ledger logic lives here -- this module only knows how to talk to one upstream.
"""
from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-1.13.0"
JEV_COST_PER_MTOK_INPUT_USD = 0.042

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen2.5vl:7b"
OLLAMA_KEEP_ALIVE = "30s"


class BackendError(RuntimeError):
    pass


class BackendTimeout(BackendError):
    pass


@dataclass
class BackendResult:
    # answers: {question_id: {"probs": {label: p, ...}}} -- raw probability
    # distributions only; abstention/min_p thresholding happens in the caller
    # (core.decide_answer), not here, so policy stays out of the backend.
    answers: Dict[str, Dict[str, float]]
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_source: str = "unknown"
    estimated_cost_usd: float = 0.0


def _question_options(question):
    if question["kind"] == "bool":
        return ["true", "false"]
    return list(question["options"])


# ---------------------------------------------------------------------------
# jev (TypeSafe System One)
# ---------------------------------------------------------------------------

def jev_run(questions: List[dict], state, api_key: str, timeout_s: float, model: str = JEV_MODEL) -> BackendResult:
    """One POST to api.typesafe.ai/v1/systemone covering every question in `questions`.

    Wire protocol per TypeSafe's own docs (docs.typesafe.ai/api.md, fetched
    2026-10-02, see operator notes: jev-pi-routing.md section 5a): question
    types are `noul` (bool) and `choice`; request body is
    `{state, model, questions}`; response is
    `{model, answers, usage: {input_tokens, output_tokens}}`.
    """
    if not api_key:
        raise BackendError("jev_no_api_key")
    wire_questions = {}
    for q in questions:
        if q["kind"] == "bool":
            wire_questions[q["id"]] = {"type": "noul", "instructions": q["prompt"]}
        else:
            criteria = {opt: opt for opt in q["options"]}
            wire_questions[q["id"]] = {"type": "choice", "instructions": q["prompt"], "criteria": criteria}

    state_str = state if isinstance(state, str) else json.dumps(state, sort_keys=True)
    body = json.dumps({"state": state_str, "model": model, "questions": wire_questions}).encode("utf-8")
    req = urllib.request.Request(
        JEV_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read(1024 * 1024)
    except urllib.error.URLError as exc:
        if isinstance(getattr(exc, "reason", None), TimeoutError) or "timed out" in str(exc).lower():
            raise BackendTimeout("jev_timeout") from exc
        raise BackendError(f"jev_http_error:{exc.__class__.__name__}") from exc
    except TimeoutError as exc:
        raise BackendTimeout("jev_timeout") from exc

    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise BackendError("jev_bad_response") from exc

    wire_answers = parsed.get("answers") or {}
    answers = {}
    for q in questions:
        qid = q["id"]
        wa = wire_answers.get(qid)
        if not isinstance(wa, dict):
            answers[qid] = {"probs": {}}
            continue
        if q["kind"] == "bool":
            # Verified live 2026-10-07: TypeSafe's actual wire response for a
            # `noul` question is `{"type": "noul", "noul": <p_true>}`, not
            # the `{"probability": ...}` shape docs.typesafe.ai/api.md implied
            # when this was written from docs alone (see docs/decision-gate.md).
            p_true = wa.get("noul", wa.get("probability"))
            if isinstance(p_true, (int, float)):
                answers[qid] = {"probs": {"true": float(p_true), "false": 1.0 - float(p_true)}}
            else:
                answers[qid] = {"probs": {}}
        else:
            probs = wa.get("probabilities")
            if isinstance(probs, dict) and probs:
                answers[qid] = {"probs": {str(k): float(v) for k, v in probs.items() if isinstance(v, (int, float))}}
            else:
                answers[qid] = {"probs": {}}

    usage = parsed.get("usage") or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    estimated_cost_usd = (input_tokens / 1_000_000.0) * JEV_COST_PER_MTOK_INPUT_USD
    return BackendResult(
        answers=answers,
        model=str(parsed.get("model") or model),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_source="published-rate",
        estimated_cost_usd=estimated_cost_usd,
    )


# ---------------------------------------------------------------------------
# ollama (local)
# ---------------------------------------------------------------------------

def _letters(n):
    return [chr(ord("A") + i) for i in range(n)]


def _build_prompt(question, letters, options):
    lines = [question["prompt"], ""]
    for letter, opt in zip(letters, options):
        lines.append(f"{letter}) {opt}")
    lines.append("")
    lines.append(f"Answer with exactly one letter ({'/'.join(letters)}), nothing else.")
    return "\n".join(lines)


def _ollama_one(question, base_url, model, timeout_s):
    options = _question_options(question)
    letters = _letters(len(options))
    prompt = _build_prompt(question, letters, options)
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": 1, "temperature": 0},
        "logprobs": True,
        # Ollama 0.35.1 rejects top_logprobs > 20 with a 400; our contract
        # caps options at MAX_OPTIONS=32 in service.py, so this can legitimately
        # need to request more than the ceiling allows -- better to request the
        # max and risk missing a low-probability option's logprob than to 400.
        "top_logprobs": min(20, max(10, len(options) * 3)),
        "keep_alive": OLLAMA_KEEP_ALIVE,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/chat", data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read(1024 * 1024)
    except urllib.error.URLError as exc:
        if isinstance(getattr(exc, "reason", None), TimeoutError) or "timed out" in str(exc).lower():
            raise BackendTimeout("ollama_timeout") from exc
        raise BackendError(f"ollama_http_error:{exc.__class__.__name__}") from exc
    except TimeoutError as exc:
        raise BackendTimeout("ollama_timeout") from exc

    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise BackendError("ollama_bad_response") from exc

    logprobs = parsed.get("logprobs") or []
    if not logprobs:
        return {"probs": {}}, 0, 0
    top = logprobs[0].get("top_logprobs") or []
    logprob_by_letter = {}
    for entry in top:
        token = str(entry.get("token", "")).strip()
        if token and token[0].upper() in letters and len(token) <= 2:
            letter = token[0].upper()
            # Keep the highest logprob seen for a letter (a model can emit
            # both "A" and "A)" style variants across top_logprobs slots).
            lp = entry.get("logprob")
            if isinstance(lp, (int, float)) and (letter not in logprob_by_letter or lp > logprob_by_letter[letter]):
                logprob_by_letter[letter] = float(lp)
    letter_to_option = dict(zip(letters, options))
    from . import core as _core  # local import to avoid a cycle at module load time

    option_logprobs = {letter_to_option[letter]: lp for letter, lp in logprob_by_letter.items() if letter in letter_to_option}
    probs = _core.softmax(option_logprobs)

    usage_in = int(parsed.get("prompt_eval_count") or 0)
    usage_out = int(parsed.get("eval_count") or 0)
    return {"probs": probs}, usage_in, usage_out


def ollama_run(questions: List[dict], state, timeout_s: float, base_url: str = OLLAMA_BASE_URL,
                model: str = OLLAMA_MODEL) -> BackendResult:
    """One /api/chat call per question (num_predict=1, logprobs on), letter-mapped options."""
    answers = {}
    input_tokens = 0
    output_tokens = 0
    deadline = time.monotonic() + timeout_s
    for q in questions:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BackendTimeout("ollama_timeout")
        # Fold the free-text `state` into the prompt as context.
        q_with_state = dict(q)
        state_str = state if isinstance(state, str) else json.dumps(state, sort_keys=True)
        q_with_state["prompt"] = f"Context: {state_str}\n\n{q['prompt']}"
        answer, in_tok, out_tok = _ollama_one(q_with_state, base_url, model, remaining)
        answers[q["id"]] = answer
        input_tokens += in_tok
        output_tokens += out_tok
    return BackendResult(
        answers=answers, model=model, input_tokens=input_tokens, output_tokens=output_tokens,
        cost_source="cache",  # local inference: no billed cost, treated as a known zero (see llm_usage.py JEV_KNOWN_COST_SOURCES)
        estimated_cost_usd=0.0,
    )
