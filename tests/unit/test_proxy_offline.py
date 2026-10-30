"""A Wi-Fi drop must surface as a transient offline error, never as pool
exhaustion or a token cooldown. See bin/claude-token-proxy is_offline_error,
offline_message and the request loop."""
import errno
import io
import socket
import unittest
from email.message import Message
from pathlib import Path
from unittest import mock

from tests.unit._helpers import load_script
from tests.unit.proxy_fixture import ProxyIsolationMixin

PROXY_PATH = Path(__file__).resolve().parents[2] / "bin" / "claude-token-proxy"
proxy = load_script("claude_token_proxy_offline_tests", PROXY_PATH)


class OfflineClassifierTests(unittest.TestCase):
    def test_connectivity_errors_are_offline(self):
        self.assertTrue(proxy.is_offline_error(socket.gaierror(-2, "Name or service not known")))
        self.assertTrue(proxy.is_offline_error(OSError(errno.ENETUNREACH, "Network unreachable")))
        self.assertTrue(proxy.is_offline_error(OSError(errno.EHOSTUNREACH, "No route to host")))
        self.assertTrue(proxy.is_offline_error(ConnectionResetError()))
        self.assertTrue(proxy.is_offline_error(TimeoutError()))

    def test_wrapped_connectivity_error_is_unwrapped(self):
        try:
            try:
                raise OSError(errno.ENETUNREACH, "down")
            except OSError as cause:
                raise RuntimeError("upstream failed") from cause
        except RuntimeError as exc:
            self.assertTrue(proxy.is_offline_error(exc))

    def test_http_level_errors_are_not_offline(self):
        # A 429/403 is an HTTP *response*, never an exception, so it never reaches
        # the classifier; an unrelated bug (ValueError) must not look like offline.
        self.assertFalse(proxy.is_offline_error(ValueError("bad body")))
        self.assertFalse(proxy.is_offline_error(OSError(errno.ENOSPC, "No space left")))

    def test_offline_message_omits_the_pool_exhausted_marker(self):
        msg = proxy.offline_message(3)
        self.assertIn(proxy.OFFLINE_MARKER, msg)
        self.assertIn("No OAuth account quota was consumed", msg)
        # The failover extension must not read this as a quota reset.
        self.assertNotIn("no OAuth account can serve", msg)


class OfflineRequestTests(ProxyIsolationMixin, unittest.TestCase):
    proxy = proxy

    def setUp(self):
        super().setUp()
        proxy.STATE.clear()
        proxy.LAST_PICK.clear()

    def tearDown(self):
        proxy.STATE.clear()
        proxy.LAST_PICK.clear()

    def make(self, name, u7):
        tok = proxy.Tok(name)
        tok.u7 = u7
        proxy.STATE.append(tok)
        return tok

    def _handler(self):
        body = b'{"model":"claude-opus-5"}'
        handler = object.__new__(proxy.Handler)
        handler.command = "POST"
        handler.path = "/v1/messages"
        handler.headers = Message()
        handler.headers["Content-Length"] = str(len(body))
        handler.rfile = io.BytesIO(body)
        handler._send_api_error = mock.Mock()
        handler._stream = mock.Mock()
        handler._deepseek_fallback = mock.Mock(return_value=False)
        return handler

    def test_network_down_yields_offline_error_without_burning_quota(self):
        first = self.make("gs", u7=0.4)
        second = self.make("other", u7=0.5)
        handler = self._handler()
        with mock.patch.object(proxy.time, "time", return_value=1000), \
                mock.patch.object(proxy, "save_usage_state"), \
                mock.patch.object(proxy, "upstream",
                                  side_effect=OSError(errno.ENETUNREACH, "Network unreachable")):
            handler._proxy()

        self.assertEqual(handler._send_api_error.call_args.args[0], 503)
        self.assertIn(proxy.OFFLINE_MARKER, handler._send_api_error.call_args.args[1])
        self.assertEqual(handler._send_api_error.call_args.args[2], "overloaded_error")
        # No cooldown, no parking, no DeepSeek fallback, no starvation accounting.
        for tok in (first, second):
            self.assertEqual(tok.cooldown_until, 0.0)
            self.assertTrue(tok.valid)
        handler._deepseek_fallback.assert_not_called()
        handler._stream.assert_not_called()

    def test_offline_error_is_not_the_pool_exhausted_message(self):
        self.make("gs", u7=0.4)
        handler = self._handler()
        with mock.patch.object(proxy.time, "time", return_value=1000), \
                mock.patch.object(proxy, "save_usage_state"), \
                mock.patch.object(proxy, "upstream", side_effect=socket.gaierror(-2, "no DNS")):
            handler._proxy()
        message = handler._send_api_error.call_args.args[1]
        self.assertNotIn("no OAuth account can serve", message)


class OnlineProbeTests(unittest.TestCase):
    def test_reachable_true_on_successful_connect(self):
        conn = mock.MagicMock()
        with mock.patch.object(proxy.socket, "create_connection", return_value=conn) as create:
            online, detail = proxy.upstream_reachable()
        self.assertTrue(online)
        self.assertIsNone(detail)
        create.assert_called_once()

    def test_reachable_false_when_offline(self):
        with mock.patch.object(proxy.socket, "create_connection",
                               side_effect=OSError(errno.ENETUNREACH, "down")):
            online, detail = proxy.upstream_reachable()
        self.assertFalse(online)
        self.assertEqual(detail, "OSError")

    def test_online_endpoint_reports_status(self):
        handler = object.__new__(proxy.Handler)
        handler.path = "/_online"
        handler._send_json = mock.Mock()
        with mock.patch.object(proxy, "upstream_reachable", return_value=(False, "OSError")):
            handler.do_GET()
        status, payload = handler._send_json.call_args.args
        self.assertEqual(status, 200)
        self.assertEqual(payload["online"], False)
        self.assertEqual(payload["host"], proxy.UPSTREAM_HOST)


if __name__ == "__main__":
    unittest.main()
