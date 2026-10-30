"""Shared fixture helpers preserve their offline test semantics."""
import base64
from http.server import BaseHTTPRequestHandler
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.request

from tests.unit._helpers import fake_jwt, load_script, stub_http


class HelpersTests(unittest.TestCase):
    def test_fake_jwt_preserves_payload_and_custom_header(self):
        token = fake_jwt({'sub': 'fixture'}, 'canary', {'alg': 'RS256'})
        head, body, signature = token.split('.')
        self.assertEqual(json.loads(base64.urlsafe_b64decode(head + '===')), {'alg': 'RS256'})
        self.assertEqual(json.loads(base64.urlsafe_b64decode(body + '===')), {'sub': 'fixture'})
        self.assertEqual(signature, 'canary')

    def test_load_script_by_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'script.py'
            path.write_text('value = 42\n')
            self.assertEqual(load_script('fixture_script', path).value, 42)

    def test_load_script_extensionless_registers_module_for_dataclasses(self):
        # bin/ tools have no .py suffix; spec_from_file_location cannot infer a
        # loader for them, and dataclasses need the module in sys.modules.
        name = 'fixture_extensionless_script'
        self.addCleanup(sys.modules.pop, name, None)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tool'
            path.write_text('#!/usr/bin/env python3\nfrom dataclasses import dataclass\n\n'
                            '@dataclass\nclass Point:\n    x: int\n\nvalue = Point(3).x\n')
            module = load_script(name, path)
        self.assertEqual(module.value, 3)
        self.assertIs(sys.modules[name], module)
        self.assertEqual(module.__file__, str(path))

    def test_load_script_failure_restores_previous_module_state(self):
        absent, present = 'fixture_failing_absent', 'fixture_failing_present'
        sentinel = object()
        sys.modules[present] = sentinel
        self.addCleanup(sys.modules.pop, present, None)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'broken'
            path.write_text('raise RuntimeError("boom")\n')
            for name in (absent, present):
                with self.assertRaisesRegex(RuntimeError, 'boom'):
                    load_script(name, path)
        self.assertNotIn(absent, sys.modules)
        self.assertIs(sys.modules[present], sentinel)

    def test_stub_http_serves_loopback_and_closes(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'ok')

        with stub_http(Handler) as server:
            with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/', timeout=2) as response:
                self.assertEqual(response.read(), b'ok')
        self.assertEqual(server.fileno(), -1)
