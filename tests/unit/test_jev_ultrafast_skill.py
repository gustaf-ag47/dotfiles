# Run: python3 -m unittest tests.unit.test_jev_ultrafast_skill -v
#
# Offline only: no network, no real TypeSafe/text-model calls, no pinned
# checkout required. Exercises the wrapper contract (config/credential
# resolution, bounds, redaction, discovery) via subprocess + temp env, never
# the upstream library itself (that needs `scripts/setup.sh` + a live Chrome,
# out of scope for this offline suite -- see docs/jev-ultrafast.md).
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "config" / "pi" / "skills" / "jev-ultrafast"
RUN_PY = SKILL_DIR / "scripts" / "run.py"
DOCTOR_PY = SKILL_DIR / "scripts" / "doctor.py"
SETUP_SH = SKILL_DIR / "scripts" / "setup.sh"


def run_python(script, args, env):
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def clean_env(tmp_home: Path) -> dict:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_home),
        "XDG_CACHE_HOME": str(tmp_home / "cache"),
        "XDG_CONFIG_HOME": str(tmp_home / "config"),
        "XDG_STATE_HOME": str(tmp_home / "state"),
    }
    return env


class SkillDiscoveryTests(unittest.TestCase):
    def test_skill_md_present_and_has_frontmatter(self):
        text = (SKILL_DIR / "SKILL.md").read_text()
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("name: jev-ultrafast", text)
        self.assertIn("description:", text)
        self.assertIn("disable-model-invocation: true", text)

    def test_referenced_scripts_exist_and_are_executable(self):
        for rel in ("scripts/setup.sh", "scripts/doctor.py", "scripts/run.py"):
            path = SKILL_DIR / rel
            self.assertTrue(path.exists(), f"missing {rel}")
            mode = path.stat().st_mode
            self.assertTrue(mode & stat.S_IXUSR, f"{rel} not executable")

    def test_references_exist(self):
        self.assertTrue((SKILL_DIR / "references" / "limitations.md").exists())
        self.assertTrue((SKILL_DIR / "references" / "text-model.md").exists())

    def test_scripts_syntax_clean(self):
        for rel in ("scripts/run.py", "scripts/doctor.py", "scripts/_agent_driver.py", "scripts/_inspect_driver.py"):
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(SKILL_DIR / rel)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(["bash", "-n", str(SETUP_SH)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class DoctorTests(unittest.TestCase):
    def test_doctor_reports_missing_checkout_without_crashing_or_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = clean_env(Path(tmp))
            result = run_python(DOCTOR_PY, ["--json"], env)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["checkout"]["present"])
            self.assertFalse(payload["ready_for_inspect"])
            self.assertFalse(payload["ready_for_execute"])
            self.assertFalse(payload["credentials"]["typesafe_key_configured"])

    def test_doctor_never_prints_key_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = clean_env(home)
            key_dir = home / "config" / "jev"
            key_dir.mkdir(parents=True)
            key_file = key_dir / "api-key"
            key_file.write_text("sk-super-secret-value-should-never-appear\n")
            key_file.chmod(0o600)
            result = run_python(DOCTOR_PY, [], env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("sk-super-secret-value-should-never-appear", result.stdout)
            self.assertNotIn("sk-super-secret-value-should-never-appear", result.stderr)
            payload_env = dict(env)
            result_json = run_python(DOCTOR_PY, ["--json"], payload_env)
            payload = json.loads(result_json.stdout)
            self.assertTrue(payload["credentials"]["typesafe_key_configured"])

    def test_doctor_respects_pi_jev_key_file_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = clean_env(home)
            alt_key = home / "alt-key"
            alt_key.write_text("secret\n")
            env["PI_JEV_KEY_FILE"] = str(alt_key)
            result = run_python(DOCTOR_PY, ["--json"], env)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["credentials"]["typesafe_key_configured"])
            self.assertEqual(payload["credentials"]["key_file"], str(alt_key))


class RunPyPreflightTests(unittest.TestCase):
    """Only the dry-run / bounds-checking / credential-resolution contract.
    Never reaches --execute against a real checkout (none is present in this
    offline suite), so these never invoke `uv run` or any network path."""

    def test_dry_run_requires_url_and_goal(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = clean_env(Path(tmp))
            result = run_python(RUN_PY, [], env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--url", result.stderr)

    def test_dry_run_without_checkout_reports_not_ready_and_makes_no_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = clean_env(Path(tmp))
            result = run_python(RUN_PY, ["--url", "https://example.com", "--goal", "do a thing"], env)
            self.assertEqual(result.returncode, 1)
            self.assertIn("NOT READY", result.stdout)
            self.assertIn("run scripts/setup.sh", result.stdout)

    def test_execute_without_checkout_fails_before_any_subprocess(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = clean_env(Path(tmp))
            result = run_python(
                RUN_PY,
                ["--url", "https://example.com", "--goal", "x", "--execute", "--max-steps", "3", "--max-seconds", "30"],
                env,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("NOT READY", result.stdout)

    def test_execute_rejects_step_budget_above_cap(self):
        # Bounds are enforced before any checkout/credential check, so no
        # checkout needs to exist for this to be meaningful.
        with tempfile.TemporaryDirectory() as tmp:
            env = clean_env(Path(tmp))
            result = run_python(
                RUN_PY,
                [
                    "--url", "https://example.com", "--goal", "x",
                    "--execute", "--max-steps", "999", "--max-seconds", "30",
                ],
                env,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("--max-steps must be", result.stderr)

    def test_execute_rejects_time_budget_above_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = clean_env(Path(tmp))
            result = run_python(
                RUN_PY,
                [
                    "--url", "https://example.com", "--goal", "x",
                    "--execute", "--max-steps", "3", "--max-seconds", "99999",
                ],
                env,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("--max-seconds must be", result.stderr)

    def test_execute_without_typesafe_key_refuses_before_subprocess(self):
        # Exercises resolve_typesafe_key()/checkout-ready gating directly
        # (via module import, monkeypatching checkout_ready) rather than
        # faking a git commit matching the real pinned SHA, which isn't
        # reproducible without a real upstream clone.
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = clean_env(home)
            saved = {k: os.environ.get(k) for k in env}
            os.environ.update(env)
            try:
                module = _import_run_module()
                original = module.checkout_ready
                module.checkout_ready = lambda path: (True, "ok")
                buf = io.StringIO()
                try:
                    with contextlib.redirect_stderr(buf):
                        rc = module.main(
                            ["--url", "https://example.com", "--goal", "x",
                             "--execute", "--max-steps", "3", "--max-seconds", "30"]
                        )
                finally:
                    module.checkout_ready = original
                self.assertEqual(rc, 1)
                self.assertIn("no TypeSafe key found", buf.getvalue())
            finally:
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

    def test_inspect_and_execute_are_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = clean_env(Path(tmp))
            result = run_python(
                RUN_PY,
                ["--url", "https://example.com", "--goal", "x", "--inspect", "--execute"],
                env,
            )
            self.assertEqual(result.returncode, 2)

    def test_dry_run_never_prints_key_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = clean_env(home)
            key_dir = home / "config" / "jev"
            key_dir.mkdir(parents=True)
            (key_dir / "api-key").write_text("sk-dryrun-secret-value\n")
            result = run_python(RUN_PY, ["--url", "https://example.com", "--goal", "x"], env)
            self.assertNotIn("sk-dryrun-secret-value", result.stdout)
            self.assertNotIn("sk-dryrun-secret-value", result.stderr)
            self.assertIn("TypeSafe key configured: True", result.stdout)


def _import_run_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("jev_ultrafast_run", RUN_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
