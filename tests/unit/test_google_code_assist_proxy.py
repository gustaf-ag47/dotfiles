"""Offline tests for bin/google-code-assist-proxy (fake upstream, no network)."""
import base64
import io
import json
import runpy
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "bin" / "google-code-assist-proxy"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def id_token(aud):
    payload = base64.urlsafe_b64encode(json.dumps({"aud": aud}).encode()).decode().rstrip("=")
    return f"h.{payload}.s"


class ProxyTest(unittest.TestCase):
    def setUp(self):
        self.m = runpy.run_path(str(SCRIPT), run_name="google_code_assist_proxy")
        self.g = self.m["Handler"].do_POST.__globals__
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.token_file = Path(self.tmp.name) / "token"
        expiry = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() + 3600))
        self.token_file.write_text(json.dumps({"id_token": id_token("cid"),
                                               "token": {"access_token": "AT", "refresh_token": "RT", "expiry": expiry}}))
        self.g["TOKEN_FILE"] = self.token_file
        self.calls = []
        real = self.g["urllib"].request.urlopen

        def fake_urlopen(req, data=None, timeout=None):
            if not isinstance(req, urllib.request.Request) or req.full_url.startswith("http://127.0.0.1"):
                return real(req, data, timeout) if data is None else real(req, data, timeout)
            body = json.loads(req.data) if req.data else None
            self.calls.append((req.full_url, dict(req.header_items()), body))
            if req.full_url.endswith("loadCodeAssist"):
                return FakeResponse(json.dumps({"cloudaicompanionProject": "proj-x"}).encode())
            if "streamGenerateContent" in req.full_url:
                ev = {"response": {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}}
                return FakeResponse(("data: " + json.dumps(ev) + "\r\n\r\n").encode())
            if req.full_url.endswith("generateContent"):
                return FakeResponse(json.dumps({"response": {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}}).encode())
            raise AssertionError(req.full_url)
        self.g["urllib"].request.urlopen = fake_urlopen
        self.addCleanup(setattr, self.g["urllib"].request, "urlopen", real)
        self.g["SESSION"] = self.g["Session"]()
        server = self.g["serve"]("127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.port = server.server_address[1]

    def post(self, path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(body).encode(),
                                     headers={"content-type": "application/json", "x-goog-api-key": "placeholder"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=5) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_refuses_non_loopback_bind(self):
        with self.assertRaises(SystemExit):
            self.m["serve"]("0.0.0.0", 0)

    def test_wraps_request_and_unwraps_response(self):
        tools = [{"functionDeclarations": [{"name": "read"}]}]
        status, text = self.post("/v1beta/models/gemini-3.8-flash-tiered:generateContent",
                                 {"contents": [{"role": "user", "parts": [{"text": "x"}]}], "tools": tools})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(text)["candidates"][0]["content"]["parts"][0]["text"], "ok")
        url, headers, body = self.calls[-1]
        self.assertTrue(url.endswith("/v1internal:generateContent"))
        self.assertEqual(body["project"], "proj-x")
        self.assertEqual(body["model"], "gemini-3.8-flash-tiered")
        self.assertEqual(body["request"]["tools"], tools)
        self.assertEqual(headers["Authorization"], "Bearer AT")  # placeholder key never forwarded

    def test_stream_events_are_unwrapped(self):
        status, text = self.post("/v1beta/models/m:streamGenerateContent?alt=sse",
                                 {"contents": [{"role": "user", "parts": [{"text": "x"}]}]})
        self.assertEqual(status, 200)
        event = json.loads(text.strip()[len("data: "):])
        self.assertIn("candidates", event)
        self.assertNotIn("response", event)

    def test_expired_token_refreshes_in_memory_only(self):
        data = json.loads(self.token_file.read_text())
        data["token"]["expiry"] = "2000-01-01T00:00:00+00:00"
        self.token_file.write_text(json.dumps(data))
        before = self.token_file.read_text()
        session = self.g["SESSION"]
        session._client_secrets = lambda: ["bad", "good"]

        def refresh_urlopen(url, body=None, timeout=None):
            form = dict(p.split("=") for p in body.decode().split("&"))
            self.assertEqual(form["client_id"], "cid")
            if form["client_secret"] != "good":
                raise urllib.error.HTTPError(url, 401, "bad", {}, io.BytesIO(b"{}"))
            return FakeResponse(json.dumps({"access_token": "NEW", "expires_in": 3600}).encode())
        self.g["urllib"].request.urlopen = refresh_urlopen
        self.assertEqual(session.token(), "NEW")
        self.assertEqual(self.token_file.read_text(), before)

    def test_missing_session_is_503(self):
        self.token_file.unlink()
        status, text = self.post("/v1beta/models/m:generateContent", {"contents": []})
        self.assertEqual(status, 503)
        self.assertIn("agy", text)

    def test_unknown_path_404(self):
        self.assertEqual(self.post("/v1/chat/completions", {})[0], 404)


if __name__ == "__main__":
    unittest.main()
