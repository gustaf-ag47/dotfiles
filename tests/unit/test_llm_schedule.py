"""Fake oracle integration tests for quota scheduler."""
import http.server
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "bin/llm-schedule"


class Oracle(http.server.BaseHTTPRequestHandler):
    usage = {}
    route = {}

    def do_GET(self):
        body = json.dumps(self.route if self.path.startswith("/_route") else self.usage).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Oracle)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.env = dict(os.environ, XDG_DATA_HOME=self.temp.name, XDG_STATE_HOME=self.temp.name,
                        PI_ANTHROPIC_PROXY_URL=f"http://127.0.0.1:{self.server.server_port}",
                        LLM_SCHEDULE_NO_SYSTEMD="1")
        Oracle.route = {"candidates": [{"provider": "anthropic", "routable": True}]}
        Oracle.usage = {"tokens": []}

    def call(self, *args):
        return subprocess.run([str(SCRIPT), *args], env=self.env, capture_output=True, text=True, check=True)

    def test_waste_starts_once_and_moves_to_done(self):
        self.call("add", "--prefer", "anthropic", "--", "true")
        self.call("run-due")
        queue = Path(self.temp.name) / "llm-schedule/queue"
        self.assertEqual(len(list(queue.glob("*.job"))), 1)
        Oracle.usage = {"tokens": [{"fp": "a", "valid": True, "u7": .2,
                                      "forecast": {"7d": {"forecast": "waste", "projected_at_reset": .5}}}]}
        self.call("run-due")
        self.call("run-due")
        self.assertFalse(list(queue.glob("*.job")))
        done = list((queue.parent / "done").glob("*.job"))
        self.assertEqual(len(done), 1)
        self.assertEqual(json.loads(done[0].read_text())["start_reason"], "waste")

    def test_reset_and_preference(self):
        self.call("add", "--prefer", "codex", "--", "true")
        now = time.time()
        Oracle.usage = {"providers": {"openai-codex": {"windows": [{"name": "primary_window", "used_percent": 2,
                                "reset_at": now + 7 * 86400 - 60}], "forecast": {}}},
                        "_samples": {"codex:primary_window": {"primary_window": [[now - 60, .02]]}}}
        self.call("run-due")
        self.assertEqual(len(list((Path(self.temp.name) / "llm-schedule/queue").glob("*.job"))), 1)
        Oracle.route = {"candidates": [{"provider": "openai-codex", "routable": True}]}
        self.call("run-due")
        done = next((Path(self.temp.name) / "llm-schedule/done").glob("*.job"))
        self.assertEqual(json.loads(done.read_text())["start_reason"], "reset")

    def test_not_before_and_remove(self):
        slug = self.call("add", "--not-before", "2020-01-01T00:00:00Z", "--", "true").stdout.strip()
        self.assertIn(slug, self.call("list").stdout)
        self.call("rm", slug)
        self.assertNotIn(slug, self.call("list").stdout)
