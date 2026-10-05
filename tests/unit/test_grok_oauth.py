"""Offline tests for scripts/grok_oauth.py, the read-only Grok CLI auth bridge.

Every test runs against a temp GROK_HOME; none touch a real ~/.grok. The
script must never write to its auth file (verified by mtime/content checks)
and must fail with short, non-secret messages on missing/malformed/wrong
issuer/expired state.
"""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/grok_oauth.py"
ENTRY_KEY = "https://auth.x.ai::b1a00492-073a-47ea-816f-4c329264a828"


def run(grok_home: Path, env_overrides: dict | None = None):
    env = {"PATH": "/usr/bin:/bin"}
    env["GROK_HOME"] = str(grok_home)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


class GrokOAuthBridgeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.grok_home = Path(self._tmp.name)

    def write_auth(self, entries: dict):
        (self.grok_home / "auth.json").write_text(json.dumps(entries))

    # --- absent / malformed auth -------------------------------------------------

    def test_missing_auth_file_is_a_useful_non_secret_error(self):
        result = run(self.grok_home)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("grok login", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_malformed_json_does_not_crash_with_a_traceback(self):
        (self.grok_home / "auth.json").write_text("{not json")
        result = run(self.grok_home)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not valid JSON", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_expected_entry_key_errors_without_guessing_another_entry(self):
        self.write_auth({"https://evil.example::other-client": {"auth_mode": "oidc", "key": "SECRET"}})
        result = run(self.grok_home)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No Grok CLI OAuth session", result.stderr)
        self.assertNotIn("SECRET", result.stdout)
        self.assertNotIn("SECRET", result.stderr)

    def test_wrong_auth_mode_is_rejected(self):
        self.write_auth({ENTRY_KEY: {"auth_mode": "api_key", "key": "SECRET"}})
        result = run(self.grok_home)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not an OIDC session", result.stderr)

    def test_missing_token_field_is_rejected(self):
        self.write_auth({ENTRY_KEY: {"auth_mode": "oidc"}})
        result = run(self.grok_home)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no access token", result.stderr)

    # --- happy path ----------------------------------------------------------------

    def test_valid_session_prints_only_the_token(self):
        self.write_auth({ENTRY_KEY: {"auth_mode": "oidc", "key": "TEST_TOKEN_123"}})
        result = run(self.grok_home)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "TEST_TOKEN_123")

    def test_respects_grok_home_override_and_default_is_untouched(self):
        self.write_auth({ENTRY_KEY: {"auth_mode": "oidc", "key": "FROM_OVERRIDE"}})
        result = run(self.grok_home)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "FROM_OVERRIDE")

    def test_script_never_writes_to_the_auth_file(self):
        self.write_auth({ENTRY_KEY: {"auth_mode": "oidc", "key": "UNCHANGED"}})
        auth_path = self.grok_home / "auth.json"
        before_mtime = auth_path.stat().st_mtime_ns
        before_content = auth_path.read_bytes()
        run(self.grok_home)
        run(self.grok_home)
        self.assertEqual(auth_path.stat().st_mtime_ns, before_mtime)
        self.assertEqual(auth_path.read_bytes(), before_content)

    # --- expiry ----------------------------------------------------------------

    def test_expired_token_with_expires_at_is_rejected(self):
        self.write_auth({ENTRY_KEY: {"auth_mode": "oidc", "key": "STALE", "expires_at": "2000-01-01T00:00:00Z"}})
        result = run(self.grok_home)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expired", result.stderr)

    def test_future_expires_at_is_accepted(self):
        self.write_auth({ENTRY_KEY: {"auth_mode": "oidc", "key": "FRESH", "expires_at": "2999-01-01T00:00:00Z"}})
        result = run(self.grok_home)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "FRESH")

    def test_expiry_is_independent_of_local_timezone(self):
        from datetime import datetime, timedelta, timezone
        expiry = datetime.now(timezone.utc) + timedelta(minutes=30)
        for offset in (timezone.utc, timezone(timedelta(hours=5))):
            self.write_auth({ENTRY_KEY: {
                "auth_mode": "oidc", "key": "FRESH",
                "expires_at": expiry.astimezone(offset).isoformat(),
            }})
            for tz in ("UTC", "Europe/Stockholm", "America/Los_Angeles"):
                result = run(self.grok_home, {"TZ": tz})
                self.assertEqual(result.returncode, 0, (tz, result.stderr))

    # --- expiry auto-refresh via the Grok CLI ---------------------------------

    def _fake_grok(self, script_body: str) -> Path:
        """Install a fake `grok` binary in a temp dir and return that dir,
        for prepending to PATH. The fake CLI is the only thing allowed to
        rewrite the temp auth.json, mirroring the real ownership rule."""
        bin_dir = self.grok_home / "fakebin"
        bin_dir.mkdir(exist_ok=True)
        grok = bin_dir / "grok"
        grok.write_text("#!/bin/bash\n" + textwrap.dedent(script_body))
        grok.chmod(0o755)
        return bin_dir

    def test_expired_token_pokes_grok_cli_and_uses_the_refreshed_token(self):
        self.write_auth({ENTRY_KEY: {"auth_mode": "oidc", "key": "STALE", "expires_at": "2000-01-01T00:00:00Z"}})
        auth_path = json.dumps(str(self.grok_home / "auth.json"))
        bin_dir = self._fake_grok(f"""
            [[ "$1" == models ]] || exit 1
            {sys.executable} - <<'PYEOF'
import json
path = {auth_path}
data = json.load(open(path))
entry = data["{ENTRY_KEY}"]
entry["key"] = "REFRESHED"
entry["expires_at"] = "2999-01-01T00:00:00Z"
json.dump(data, open(path, "w"))
PYEOF
        """)
        result = run(self.grok_home, {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "REFRESHED")

    def test_expired_token_with_failing_grok_cli_errors_without_stale_token(self):
        self.write_auth({ENTRY_KEY: {"auth_mode": "oidc", "key": "STALE", "expires_at": "2000-01-01T00:00:00Z"}})
        bin_dir = self._fake_grok("exit 1\n")
        result = run(self.grok_home, {"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expired", result.stderr)
        self.assertNotIn("STALE", result.stdout)

    def test_expired_token_with_no_grok_on_path_errors_cleanly(self):
        self.write_auth({ENTRY_KEY: {"auth_mode": "oidc", "key": "STALE", "expires_at": "2000-01-01T00:00:00Z"}})
        result = run(self.grok_home)  # default PATH has no grok
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expired", result.stderr)
        self.assertIn("grok login", result.stderr)

    def test_absent_expires_at_does_not_block_token_use(self):
        # The field is community-observed, not guaranteed; the CLI itself owns
        # refresh when expiry data is unavailable to us.
        self.write_auth({ENTRY_KEY: {"auth_mode": "oidc", "key": "NO_EXPIRY_FIELD"}})
        result = run(self.grok_home)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "NO_EXPIRY_FIELD")

    # --- permissions -------------------------------------------------------------

    def test_default_grok_home_is_home_dot_grok_when_unset(self):
        # Importing the module (not executing __main__) lets us check the
        # default path logic without touching the real filesystem.
        import importlib.util

        spec = importlib.util.spec_from_file_location("grok_oauth", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        import os

        env_backup = os.environ.pop("GROK_HOME", None)
        try:
            self.assertEqual(module.grok_home(), Path.home() / ".grok")
        finally:
            if env_backup is not None:
                os.environ["GROK_HOME"] = env_backup


if __name__ == "__main__":
    unittest.main()
