"""API-key-style clients (Hermes) must use the proxy's subscription transport."""
import importlib.machinery
from pathlib import Path
from unittest import TestCase, mock

proxy = importlib.machinery.SourceFileLoader(
    "proxy_oauth_headers", str(Path(__file__).parents[2] / "bin/claude-token-proxy")
).load_module()


class OAuthTransportTests(TestCase):
    def test_upstream_normalizes_hermes_headers_without_mutating_input(self):
        headers = {
            "X-Api-Key": "client-placeholder",
            "authorization": "Bearer client-placeholder",
            "Anthropic-Beta": "interleaved-thinking-2025-05-14",
            "User-Agent": "Anthropic/Python",
            "Content-Type": "application/json",
        }
        original = dict(headers)
        with mock.patch.object(proxy.http.client, "HTTPSConnection") as connection:
            proxy.upstream("POST", "/v1/messages", headers, b"{}", "pool-token")
        sent = {k.lower(): v for k, v in connection.return_value.request.call_args.kwargs["headers"].items()}
        self.assertNotIn("x-api-key", sent)
        self.assertEqual(sent["authorization"], "Bearer pool-token")
        self.assertIn("oauth-2025-04-20", sent["anthropic-beta"].split(","))
        self.assertIn("interleaved-thinking-2025-05-14", sent["anthropic-beta"].split(","))
        self.assertEqual(sent["x-app"], "cli")
        self.assertEqual(sent["user-agent"], proxy.OAUTH_USER_AGENT)
        self.assertEqual(headers, original)

    def test_existing_betas_deduplicated_and_stale_client_versions_overridden(self):
        headers = {"anthropic-beta": proxy.OAUTH_BETA + ",custom-beta", "user-agent": "claude-code/2.1.83"}
        with mock.patch.object(proxy.http.client, "HTTPSConnection") as connection:
            proxy.upstream("POST", "/v1/messages", headers, b"{}", "pool-token")
        sent = {k.lower(): v for k, v in connection.return_value.request.call_args.kwargs["headers"].items()}
        betas = sent["anthropic-beta"].split(",")
        self.assertEqual(len(betas), len(set(betas)))
        self.assertIn("custom-beta", betas)
        # Anthropic gates models by claude-code version; a stale client UA must not pass through.
        self.assertEqual(sent["user-agent"], proxy.OAUTH_USER_AGENT)
