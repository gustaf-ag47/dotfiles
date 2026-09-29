"""Per-test isolation for proxy filesystem state and sample ledger."""
from pathlib import Path
from tempfile import TemporaryDirectory


class ProxyIsolationMixin:
    def run(self, result=None):
        # Wrap run rather than setUp: several legacy tests override setUp without
        # chaining, and every proxy test must still get isolated destinations.
        tmp = TemporaryDirectory()
        saved = {key: getattr(self.proxy, key) for key in
                 ("CONTROL_DIR", "ROUTING_LOG", "USAGE_STATE_FILE", "SAMPLES")}
        self.proxy.CONTROL_DIR = Path(tmp.name)
        self.proxy.ROUTING_LOG = self.proxy.CONTROL_DIR / "routing.log"
        self.proxy.USAGE_STATE_FILE = self.proxy.CONTROL_DIR / "usage.json"
        self.proxy.SAMPLES = {}
        try:
            return super().run(result)
        finally:
            for key, value in saved.items():
                setattr(self.proxy, key, value)
            tmp.cleanup()
