import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "llm_host_smoke.py"


class HostSmokeContractTests(unittest.TestCase):
    def test_list_is_redacted_and_covers_independent_host_checks(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--list"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema"], "llm-host-smoke.v1")
        self.assertIn("hostname", payload)
        checks = payload["checks"]
        self.assertIn("make test-unit", checks)
        self.assertIn("bin/llm-usage --refresh --json | python3 -m json.tool >/dev/null", checks)
        self.assertIn("bin/llm-news --json | python3 -m json.tool >/dev/null", checks)
        self.assertIn("pi --no-session -p '/usage'", checks)
        self.assertTrue(payload["redacted"])
        self.assertNotIn("auth.json", result.stdout)
        self.assertNotIn("Bearer", result.stdout)
        self.assertNotIn("account_id", result.stdout)


if __name__ == "__main__":
    unittest.main()
