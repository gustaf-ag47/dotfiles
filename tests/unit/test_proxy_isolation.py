"""Guard against proxy tests mutating the operator's real proxy cache."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ProxyCacheIsolationTests(unittest.TestCase):
    def test_proxy_suite_does_not_change_real_cache_mtimes(self):
        real = Path.home() / ".cache/cc-proxy"
        def snapshot():
            if not real.exists():
                return None
            return {str(p.relative_to(real)): (p.stat().st_mtime_ns, p.stat().st_size)
                    for p in [real, *real.rglob("*")]}
        before = snapshot()
        with tempfile.TemporaryDirectory() as cache:
            env = dict(os.environ, XDG_CACHE_HOME=cache)
            result = subprocess.run([sys.executable, "-m", "unittest",
                "tests.unit.test_claude_token_proxy", "tests.unit.test_proxy_cross_provider",
                "tests.unit.test_proxy_deepseek_backstop", "tests.unit.test_proxy_observability"],
                cwd=Path(__file__).resolve().parents[2], env=env, capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(snapshot(), before, "proxy tests changed ~/.cache/cc-proxy")


if __name__ == "__main__":
    unittest.main()
