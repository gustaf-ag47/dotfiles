"""Guard against proxy tests mutating the operator's real proxy cache.

The suites run in a subprocess whose XDG_CACHE_HOME is a temp dir, so the proxy's
CONTROL_DIR resolves there; a leak to the real cache can only come from a hardcoded
path. Comparing mtimes of the real files is not a valid oracle: the live proxy
rewrites usage.json on every request, so that check fails whenever the system is
in use. Instead assert that the suites pass under the redirect and that the real
cache gained no new files (tests/unit/proxy_fixture.py sends each test to its own
temp dir, so even the redirected cache normally stays empty).
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

# Discovered, not hand-maintained: every unit module that loads the proxy
# script writes through its CONTROL_DIR and must honour the cache redirect.
# A hard-coded list drifted (it missed test_proxy_grok, test_proxy_5h and
# test_anthropic_usage_freshness).
PROXY_SUITES = sorted(
    "tests.unit." + path.stem
    for path in Path(__file__).parent.glob("test_*.py")
    if path.stem != Path(__file__).stem and "claude-token-proxy" in path.read_text()
)


class ProxyCacheIsolationTests(unittest.TestCase):
    def test_proxy_suites_write_only_to_the_redirected_cache(self):
        real = Path.home() / ".cache/cc-proxy"
        before = {str(p.relative_to(real)) for p in real.rglob("*")} if real.exists() else set()
        with tempfile.TemporaryDirectory() as cache:
            env = dict(os.environ, XDG_CACHE_HOME=cache)
            env.pop("PI_ANTHROPIC_PROXY_URL", None)
            result = subprocess.run([sys.executable, "-m", "unittest", *PROXY_SUITES],
                                    cwd=Path(__file__).resolve().parents[2], env=env,
                                    capture_output=True, text=True, timeout=300)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = {str(p.relative_to(real)) for p in real.rglob("*")} if real.exists() else set()
        self.assertEqual(after - before, set(), "proxy tests created files in the real ~/.cache/cc-proxy")


if __name__ == "__main__":
    unittest.main()
