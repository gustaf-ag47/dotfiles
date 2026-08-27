#!/usr/bin/env python3
"""Regression tests for the dependency-free Claude token proxy."""

from importlib.machinery import SourceFileLoader
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main, mock


PROXY_PATH = Path(__file__).parents[2] / "bin" / "claude-token-proxy"
proxy = SourceFileLoader("claude_token_proxy", str(PROXY_PATH)).load_module()


class UsagePersistenceTests(TestCase):
    def setUp(self):
        proxy.STATE.clear()
        proxy.PERSISTENCE_ERROR = None
        self.token = proxy.Tok("test-token")
        proxy.STATE.append(self.token)

    def tearDown(self):
        proxy.STATE.clear()
        proxy.PERSISTENCE_ERROR = None

    def test_persistence_failure_does_not_abort_request_accounting(self):
        with mock.patch.object(
            proxy.Path,
            "mkdir",
            side_effect=OSError(30, "Read-only file system"),
        ):
            proxy.record_request(self.token, "claude-opus-test")

        self.assertEqual(self.token.requests, 1)
        self.assertEqual(self.token.by_model["claude-opus-test"]["requests"], 1)
        self.assertIsNotNone(proxy.PERSISTENCE_ERROR)

    def test_persistence_recovers_after_a_failure(self):
        proxy.PERSISTENCE_ERROR = "previous failure"
        with TemporaryDirectory() as directory:
            proxy.CONTROL_DIR = Path(directory)
            proxy.USAGE_STATE_FILE = proxy.CONTROL_DIR / "usage.json"
            self.assertTrue(proxy.save_usage_state())
            self.assertTrue(proxy.USAGE_STATE_FILE.is_file())

        self.assertIsNone(proxy.PERSISTENCE_ERROR)


if __name__ == "__main__":
    main()
