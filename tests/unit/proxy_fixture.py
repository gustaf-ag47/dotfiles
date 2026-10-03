"""Per-test isolation for proxy filesystem state and sample ledger."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory

# Ambient provider credentials on the developer's machine must not reach the
# adapters under test: a real DEEPSEEK_API_KEY made the deepseek adapter
# consume mocked get_json side_effect sequences meant for other providers
# (tests failed locally, passed in CI, 2026-10-03). GROK_HOME is pointed at
# the per-test tmp dir for the same reason rather than cleared.
AMBIENT_ENV = ("DEEPSEEK_API_KEY", "DEEPSEEK_ACCOUNT_LABEL")


class ProxyIsolationMixin:
    def run(self, result=None):
        # Wrap run rather than setUp: several legacy tests override setUp without
        # chaining, and every proxy test must still get isolated destinations.
        tmp = TemporaryDirectory()
        saved = {key: getattr(self.proxy, key) for key in
                 ("CONTROL_DIR", "ROUTING_LOG", "USAGE_STATE_FILE", "SAMPLES",
                  "PI_AGENT_DIR")}
        self.proxy.CONTROL_DIR = Path(tmp.name)
        self.proxy.ROUTING_LOG = self.proxy.CONTROL_DIR / "routing.log"
        self.proxy.USAGE_STATE_FILE = self.proxy.CONTROL_DIR / "usage.json"
        self.proxy.SAMPLES = {}
        # A real ~/.pi/agent/auth.json must never leak into tests either:
        # live OAuth entries send other providers down network code paths the
        # test did not mock. Point at an empty dir so every machine behaves
        # like CI: no credentials, deterministic paths.
        self.proxy.PI_AGENT_DIR = Path(tmp.name) / "pi-agent"
        saved_env = {key: os.environ.pop(key) for key in AMBIENT_ENV if key in os.environ}
        saved_env["GROK_HOME"] = os.environ.get("GROK_HOME")
        os.environ["GROK_HOME"] = str(Path(tmp.name) / "grok-home")
        try:
            return super().run(result)
        finally:
            for key, value in saved.items():
                setattr(self.proxy, key, value)
            for key, value in saved_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            tmp.cleanup()
