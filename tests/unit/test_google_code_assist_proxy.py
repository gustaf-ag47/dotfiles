"""Offline tests for bin/google-code-assist-proxy (no network, no agy)."""
import json
import os
import runpy
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "bin" / "google-code-assist-proxy"


def load():
    return runpy.run_path(str(SCRIPT), run_name="google_code_assist_proxy")


def post(port, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


class ProxyTest(unittest.TestCase):
    def setUp(self):
        self.m = load()

    def serve(self):
        g = self.m["Handler"].do_POST.__globals__
        server = g["serve"]("127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        return g, server.server_address[1]

    def test_refuses_non_loopback_bind(self):
        with self.assertRaises(SystemExit):
            self.m["serve"]("0.0.0.0", 0)

    def test_rejects_tools(self):
        g, port = self.serve()
        g["generate"] = lambda body: self.fail("must not reach upstream")
        for body in (
            {"messages": [{"role": "user", "content": "hi"}], "tools": [{"type": "function", "function": {"name": "x"}}]},
            {"messages": [{"role": "tool", "content": "out", "tool_call_id": "1"}]},
            {"messages": [{"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]}]},
            {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x"}}]}]},
        ):
            status, text = post(port, body)
            self.assertEqual(status, 400, body)
            self.assertIn("not supported", text)

    def test_text_request_and_stream(self):
        g, port = self.serve()
        seen = {}

        def fake(body):
            seen["wrapped"] = g["request_body"](body)
            return {"response": {"candidates": [{"content": {"parts": [{"text": "OK"}]}}],
                                 "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1}}}
        g["generate"] = fake
        msgs = [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}]
        status, text = post(port, {"model": "gemini-3.8-flash-low", "messages": msgs})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(text)["choices"][0]["message"]["content"], "OK")
        self.assertEqual(seen["wrapped"]["request"]["systemInstruction"]["parts"][0]["text"], "be brief")
        status, text = post(port, {"model": "gemini-3.8-flash-low", "messages": msgs, "stream": True})
        self.assertEqual(status, 200)
        self.assertIn('"content": "OK"', text)
        self.assertIn('"finish_reason": "stop"', text)
        self.assertTrue(text.rstrip().endswith("data: [DONE]"))

    def test_403_without_fallback_is_error_and_no_agy(self):
        g, port = self.serve()

        def denied(body):
            raise urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
        g["direct"] = denied
        g["via_agy"] = lambda body: self.fail("agy fallback must be opt-in")
        os.environ.pop("GOOGLE_CODE_ASSIST_AGY_FALLBACK", None)
        status, text = post(port, {"messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(status, 502)
        self.assertIn("HTTP 403", text)

    def test_missing_token_is_reported_without_secret(self):
        with tempfile.TemporaryDirectory() as d:
            g = self.m["access_token"].__globals__
            g["TOKEN_FILE"] = Path(d) / "missing"
            with self.assertRaises(g["Rejected"]) as ctx:
                g["access_token"]()
            self.assertEqual(ctx.exception.status, 503)


if __name__ == "__main__":
    unittest.main()
