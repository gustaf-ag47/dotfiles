#!/usr/bin/env python3
"""Tests for the vendorable config/decision-gate/decision_gate_client.py.

Loaded by path (SourceFileLoader) the same way other single-file tools in
this repo are tested, since it is meant to be copied standalone into other
projects rather than imported as part of this package.
"""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.machinery import SourceFileLoader
from pathlib import Path

CLIENT_PATH = Path(__file__).parents[2] / "config" / "decision-gate" / "decision_gate_client.py"
client = SourceFileLoader("decision_gate_client", str(CLIENT_PATH)).load_module()


class EchoHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, status, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/healthz":
            self._send(200, {"status": "ok", "version": "v1"})
            return
        if self.path.startswith("/v1/report"):
            self._send(200, {"purpose": "p", "n": 3})
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        if self.path == "/v1/decide":
            answers = {q["id"]: {"choice": "receipt", "p": 0.94, "probs": {"receipt": 0.94}, "abstained": False}
                       for q in body["questions"]}
            self._send(200, {"decision_id": "dg_test", "backend": "ollama", "latency_ms": 5.0,
                              "cached": False, "answers": answers})
            return
        if self.path == "/v1/outcome":
            self._send(200, {"ok": True, "decision_id": body["decision_id"], "agreement": True})
            return
        self._send(404, {"error": "not_found"})


class ClientAgainstLiveServerTests(unittest.TestCase):
    def setUp(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), EchoHandler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_decide_happy_path(self):
        result = client.decide("p", "internal", "state", [{"id": "kind", "kind": "choice",
                                "prompt": "?", "options": ["receipt", "invoice"]}], base_url=self.base_url)
        self.assertEqual(result["answers"]["kind"]["choice"], "receipt")
        self.assertNotIn("fail_open", result)

    def test_outcome_happy_path(self):
        result = client.outcome("dg_test", {"kind": "receipt"}, "opus", base_url=self.base_url)
        self.assertTrue(result["agreement"])

    def test_report_happy_path(self):
        result = client.report("p", base_url=self.base_url)
        self.assertEqual(result["n"], 3)

    def test_healthz_true(self):
        self.assertTrue(client.healthz(base_url=self.base_url))


class ClientFailOpenTests(unittest.TestCase):
    """No server listening on this port -- every call must fail open, not raise."""

    DEAD_URL = "http://127.0.0.1:1"  # privileged, unused port: connection refused/timeout either way

    def test_decide_fails_open_to_all_abstained(self):
        questions = [{"id": "kind", "kind": "choice", "prompt": "?", "options": ["a", "b"]}]
        result = client.decide("p", "internal", "state", questions, base_url=self.DEAD_URL, timeout_s=1)
        self.assertTrue(result["fail_open"])
        self.assertTrue(result["answers"]["kind"]["abstained"])
        self.assertIsNone(result["answers"]["kind"]["choice"])

    def test_decide_strict_raises(self):
        questions = [{"id": "kind", "kind": "choice", "prompt": "?", "options": ["a", "b"]}]
        with self.assertRaises(client.DecisionGateError):
            client.decide("p", "internal", "state", questions, base_url=self.DEAD_URL, timeout_s=1, strict=True)

    def test_outcome_fails_open_to_none(self):
        self.assertIsNone(client.outcome("dg_x", {"a": 1}, "opus", base_url=self.DEAD_URL, timeout_s=1))

    def test_report_fails_open_to_none(self):
        self.assertIsNone(client.report("p", base_url=self.DEAD_URL, timeout_s=1))

    def test_healthz_false_on_dead_server(self):
        self.assertFalse(client.healthz(base_url=self.DEAD_URL, timeout_s=1))


if __name__ == "__main__":
    unittest.main()
