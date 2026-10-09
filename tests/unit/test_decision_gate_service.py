#!/usr/bin/env python3
"""Service-level tests: real HTTP server (ThreadingHTTPServer) + fake backends.

No network access and no real jev/ollama calls happen in this file -- the
backend callables injected into Deps are synthetic. This exercises routing,
validation, policy enforcement, caching, budget, abstention and reporting the
same way a real consumer would, over loopback HTTP.
"""
import json
import tempfile
import threading
import unittest
import unittest.mock
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from scripts.decision_gate import backends, core, service


class FakeBackend:
    """Deterministic fake: returns fixed probability distributions per question id."""

    def __init__(self, by_question, model="fake-model", input_tokens=100, output_tokens=10,
                 cost_source="published-rate", estimated_cost_usd=0.001, raise_error=None):
        self.by_question = by_question
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cost_source = cost_source
        self.estimated_cost_usd = estimated_cost_usd
        self.raise_error = raise_error
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.raise_error:
            raise self.raise_error
        questions = args[0]
        answers = {q["id"]: {"probs": self.by_question.get(q["id"], {})} for q in questions}
        return backends.BackendResult(answers=answers, model=self.model, input_tokens=self.input_tokens,
                                       output_tokens=self.output_tokens, cost_source=self.cost_source,
                                       estimated_cost_usd=self.estimated_cost_usd)


class DecisionGateServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tmp.name) / "state"
        self.policy_patch = unittest.mock.patch.object(core, "default_state_dir", return_value=self.state_dir)
        self.policy_patch.start()
        self.store = core.Store(self.state_dir)
        self.policy = {"schema": core.SCHEMA_POLICY, "default": dict(core.DEFAULT_PURPOSE_POLICY), "purposes": {}}
        self.jev_backend = FakeBackend({"kind": {"receipt": 0.94, "invoice": 0.04, "other": 0.02}})
        self.ollama_backend = FakeBackend({"kind": {"receipt": 0.94, "invoice": 0.04, "other": 0.02}})
        self.deps = service.Deps(
            store=self.store,
            policy_loader=lambda: (self.policy, None),
            jev_key_loader=lambda: "fake-key",
            jev_run=self.jev_backend,
            ollama_run=self.ollama_backend,
        )
        handler_cls = service.make_handler_class(self.deps)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.store.close()
        self.policy_patch.stop()
        self.tmp.cleanup()

    def base_url(self):
        return f"http://127.0.0.1:{self.port}"

    def post(self, path, body):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url()}{path}", data=data, method="POST",
                                      headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def get(self, path):
        req = urllib.request.Request(f"{self.base_url()}{path}", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def decide_body(self, purpose="finance-attachment-kind", sensitivity="internal"):
        return {
            "purpose": purpose, "sensitivity": sensitivity, "state": "a short receipt-looking text",
            "questions": [{"id": "kind", "kind": "choice", "prompt": "What kind?",
                            "options": ["receipt", "invoice", "other"]}],
        }

    def test_healthz(self):
        status, body = self.get("/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")

    def test_decide_happy_path_internal_uses_policy_backend(self):
        self.policy["default"]["backend"] = "jev"
        status, body = self.post("/v1/decide", self.decide_body(sensitivity="internal"))
        self.assertEqual(status, 200)
        self.assertEqual(body["backend"], "jev")
        self.assertFalse(body["cached"])
        self.assertEqual(body["answers"]["kind"]["choice"], "receipt")
        self.assertAlmostEqual(body["answers"]["kind"]["p"], 0.94, places=2)
        self.assertFalse(body["answers"]["kind"]["abstained"])
        self.assertEqual(self.jev_backend.calls, 1)

    def test_decide_caches_second_call(self):
        self.post("/v1/decide", self.decide_body())
        self.post("/v1/decide", self.decide_body())
        self.assertEqual(self.ollama_backend.calls, 1)
        status, body = self.post("/v1/decide", self.decide_body())
        self.assertTrue(body["cached"])

    def test_decide_private_never_reaches_jev_without_allow_external(self):
        self.policy["default"]["backend"] = "jev"
        self.policy["default"]["allow_external"] = False
        status, body = self.post("/v1/decide", self.decide_body(sensitivity="private"))
        self.assertEqual(status, 200)
        self.assertEqual(body["backend"], "ollama")
        self.assertEqual(self.jev_backend.calls, 0)
        self.assertEqual(self.ollama_backend.calls, 1)

    def test_decide_private_allowed_with_explicit_flag(self):
        self.policy["default"]["backend"] = "jev"
        self.policy["default"]["allow_external"] = True
        status, body = self.post("/v1/decide", self.decide_body(sensitivity="private"))
        self.assertEqual(body["backend"], "jev")
        self.assertEqual(self.jev_backend.calls, 1)

    def test_decide_below_min_p_abstains(self):
        self.policy["default"]["min_p"] = 0.99
        status, body = self.post("/v1/decide", self.decide_body())
        self.assertTrue(body["answers"]["kind"]["abstained"])

    def test_decide_backend_error_abstains(self):
        self.ollama_backend.raise_error = backends.BackendError("boom")
        status, body = self.post("/v1/decide", self.decide_body())
        self.assertEqual(status, 200)
        self.assertTrue(body["answers"]["kind"]["abstained"])
        self.assertIsNone(body["answers"]["kind"]["choice"])

    def test_decide_backend_timeout_abstains(self):
        self.ollama_backend.raise_error = backends.BackendTimeout("timeout")
        status, body = self.post("/v1/decide", self.decide_body())
        self.assertTrue(body["answers"]["kind"]["abstained"])

    def test_decide_budget_exhausted_abstains(self):
        self.policy["default"]["daily_call_cap"] = 1
        self.post("/v1/decide", self.decide_body(purpose="budget-test"))
        status, body = self.post("/v1/decide", {**self.decide_body(purpose="budget-test"),
                                                  "state": "a different text so the cache misses"})
        self.assertTrue(body["answers"]["kind"]["abstained"])
        self.assertEqual(body.get("reason"), "budget_exhausted")

    def test_decide_rejects_invalid_sensitivity(self):
        body = self.decide_body()
        body["sensitivity"] = "top-secret"
        status, _ = self.post("/v1/decide", body)
        self.assertEqual(status, 400)

    def test_decide_rejects_missing_questions(self):
        body = self.decide_body()
        body["questions"] = []
        status, _ = self.post("/v1/decide", body)
        self.assertEqual(status, 400)

    def test_decide_bool_question_choice_is_native_bool(self):
        self.ollama_backend.by_question["financial"] = {"true": 0.99, "false": 0.01}
        body = self.decide_body()
        body["questions"].append({"id": "financial", "kind": "bool", "prompt": "Is this financial?"})
        status, resp = self.post("/v1/decide", body)
        self.assertIs(resp["answers"]["financial"]["choice"], True)

    def test_decide_sensitivity_not_allowed_for_purpose(self):
        self.policy["purposes"]["restricted"] = {"allowed_sensitivity": ["public"]}
        status, body = self.post("/v1/decide", self.decide_body(purpose="restricted", sensitivity="private"))
        self.assertEqual(status, 200)
        self.assertTrue(body["answers"]["kind"]["abstained"])
        self.assertEqual(body.get("reason"), "sensitivity_not_allowed")

    def test_outcome_and_report_round_trip(self):
        status, decided = self.post("/v1/decide", self.decide_body(purpose="report-test"))
        decision_id = decided["decision_id"]
        status, outcome_resp = self.post("/v1/outcome", {"decision_id": decision_id, "truth": {"kind": "receipt"},
                                                            "source": "opus"})
        self.assertEqual(status, 200)
        self.assertTrue(outcome_resp["agreement"])

        status, report = self.get("/v1/report?purpose=report-test")
        self.assertEqual(status, 200)
        self.assertEqual(report["n"], 1)
        self.assertEqual(report["agreement"], 1.0)

    def test_outcome_unknown_decision_id_is_400(self):
        status, _ = self.post("/v1/outcome", {"decision_id": "dg_nope", "truth": {"a": 1}, "source": "human"})
        self.assertEqual(status, 400)

    def test_outcome_invalid_source_is_400(self):
        status, decided = self.post("/v1/decide", self.decide_body(purpose="src-test"))
        status, _ = self.post("/v1/outcome", {"decision_id": decided["decision_id"], "truth": {"kind": "x"},
                                               "source": "robot"})
        self.assertEqual(status, 400)

    def test_report_empty_purpose(self):
        status, report = self.get("/v1/report?purpose=never-seen")
        self.assertEqual(status, 200)
        self.assertEqual(report["n"], 0)

    def test_policy_invalid_abstains_everything(self):
        self.deps.policy_loader = lambda: (None, "policy_invalid")
        status, body = self.post("/v1/decide", self.decide_body())
        self.assertEqual(status, 200)
        self.assertTrue(body["answers"]["kind"]["abstained"])

    def test_unknown_route_is_404(self):
        status, _ = self.get("/v1/nope")
        self.assertEqual(status, 404)

    def test_ledger_written_and_metadata_only(self):
        self.post("/v1/decide", self.decide_body(purpose="ledger-test"))
        ledger = core.ledger_path(self.state_dir)
        self.assertTrue(ledger.exists())
        line = json.loads(ledger.read_text().strip().split("\n")[0])
        self.assertEqual(line["schema"], core.SCHEMA_EVENT)
        self.assertNotIn("state", line)
        self.assertNotIn("answers", line)
        self.assertEqual(line["purpose"], "ledger-test")


if __name__ == "__main__":
    unittest.main()
