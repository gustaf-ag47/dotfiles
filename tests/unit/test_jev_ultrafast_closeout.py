# Run: python3 -m unittest tests.unit.test_jev_ultrafast_closeout -v
#
# Offline only: no network, no real TypeSafe/text-model/API calls, no pinned
# checkout required (goal text is a local literal, never sent anywhere).
# Covers the closeout-review fixes: NaN/non-finite --max-seconds rejection,
# hanging-child process-group timeout, trace metadata-only content + 0600/0700
# perms + atomic write, dirty-pinned-checkout rejection, and http(s)-only /
# no-embedded-credential URL validation.
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "config" / "pi" / "skills" / "jev-ultrafast"
SCRIPTS_DIR = SKILL_DIR / "scripts"
RUN_PY = SCRIPTS_DIR / "run.py"
SETUP_SH = SCRIPTS_DIR / "setup.sh"

sys.path.insert(0, str(SCRIPTS_DIR))
import _bounded  # noqa: E402
import _trace  # noqa: E402


def clean_env(tmp_home: Path) -> dict:
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_home),
        "XDG_CACHE_HOME": str(tmp_home / "cache"),
        "XDG_CONFIG_HOME": str(tmp_home / "config"),
        "XDG_STATE_HOME": str(tmp_home / "state"),
    }


def run_python(script, args, env):
    return subprocess.run(
        [sys.executable, str(script), *args], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=30,
    )


class NonFiniteBoundTests(unittest.TestCase):
    def test_nan_max_seconds_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = clean_env(Path(tmp))
            result = run_python(
                RUN_PY, ["--url", "https://example.com", "--goal", "x", "--execute", "--max-steps", "3", "--max-seconds", "nan"], env,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("finite", result.stderr)

    def test_infinity_max_seconds_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = clean_env(Path(tmp))
            result = run_python(
                RUN_PY, ["--url", "https://example.com", "--goal", "x", "--execute", "--max-steps", "3", "--max-seconds", "inf"], env,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("finite", result.stderr)

    def test_negative_max_seconds_still_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = clean_env(Path(tmp))
            result = run_python(
                RUN_PY, ["--url", "https://example.com", "--goal", "x", "--execute", "--max-steps", "3", "--max-seconds", "-5"], env,
            )
            self.assertEqual(result.returncode, 2)


class UrlValidationTests(unittest.TestCase):
    def test_embedded_credentials_rejected_and_not_echoed(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = clean_env(Path(tmp))
            result = run_python(RUN_PY, ["--url", "https://user:hunter2@example.com", "--goal", "x"], env)
            self.assertEqual(result.returncode, 2)
            self.assertIn("embed credentials", result.stderr)
            self.assertNotIn("hunter2", result.stdout)
            self.assertNotIn("hunter2", result.stderr)

    def test_non_http_scheme_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = clean_env(Path(tmp))
            for scheme in ("ftp://example.com", "file:///etc/passwd", "javascript:alert(1)"):
                result = run_python(RUN_PY, ["--url", scheme, "--goal", "x"], env)
                self.assertEqual(result.returncode, 2, scheme)

    def test_plain_https_accepted_by_validator(self):
        self.assertEqual(_bounded.validate_url("https://example.com/path?q=1"), "https://example.com/path?q=1")

    def test_dry_run_echoes_redacted_url_without_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = clean_env(Path(tmp))
            result = run_python(RUN_PY, ["--url", "https://example.com/search?token=secret123", "--goal", "x"], env)
            self.assertNotIn("secret123", result.stdout)
            self.assertIn("https://example.com", result.stdout)
            self.assertNotIn("/search", result.stdout)


class HangingChildTimeoutTests(unittest.TestCase):
    def test_interrupt_stops_detached_children(self):
        proc = Mock()
        proc.wait.side_effect = [KeyboardInterrupt(), 0]
        with patch.object(_bounded.subprocess, 'Popen', return_value=proc), \
             patch.object(_bounded, '_kill_process_group') as kill:
            with self.assertRaises(KeyboardInterrupt):
                _bounded.run_bounded(['fixture'], cwd='.', env={}, timeout_seconds=5)
        kill.assert_called_once_with(proc)

    def test_hanging_child_is_killed_within_bound(self):
        start = time.monotonic()
        result = _bounded.run_bounded(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            cwd=str(ROOT), env=dict(os.environ), timeout_seconds=1,
        )
        elapsed = time.monotonic() - start
        self.assertTrue(result.timed_out)
        self.assertEqual(result.returncode, _bounded.EXIT_TIMEOUT)
        self.assertLess(elapsed, 10, "run_bounded did not enforce its timeout promptly")

    def test_hanging_grandchild_in_new_process_group_is_also_killed(self):
        # Simulates a stuck predict()/input() whose child spawned its own
        # subprocess (e.g. `uv run` -> python -> browser-harness daemon): the
        # whole group must die, not just the direct child.
        script = (
            "import subprocess, time, sys; "
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
            "time.sleep(60)"
        )
        start = time.monotonic()
        result = _bounded.run_bounded(
            [sys.executable, "-c", script], cwd=str(ROOT), env=dict(os.environ), timeout_seconds=1,
        )
        elapsed = time.monotonic() - start
        self.assertTrue(result.timed_out)
        self.assertLess(elapsed, 10)

    def test_fast_child_returns_its_own_code_not_timeout(self):
        result = _bounded.run_bounded(
            [sys.executable, "-c", "import sys; sys.exit(7)"], cwd=str(ROOT), env=dict(os.environ), timeout_seconds=5,
        )
        self.assertFalse(result.timed_out)
        self.assertEqual(result.returncode, 7)

    def test_inspect_mode_has_an_outer_timeout_shorter_than_a_minute_and_a_half(self):
        # Static contract check: run.py must bound --inspect too, not just
        # --execute. Read the constant rather than running a real browser.
        spec = importlib.util.spec_from_file_location("jev_ultrafast_run", RUN_PY)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(0 < module.INSPECT_TIMEOUT_SECONDS <= 90)


class FinalIntegrationTests(unittest.TestCase):
    def load(self, filename):
        spec = importlib.util.spec_from_file_location('closeout_' + filename, SCRIPTS_DIR / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_execute_outer_deadline_equals_requested_seconds(self):
        module = self.load('run.py')
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, clean_env(Path(tmp)), clear=True), \
             patch.object(module, 'checkout_ready', return_value=(True, 'ok')), \
             patch.object(module, 'resolve_typesafe_key', return_value='test'), \
             patch.object(module, 'run_bounded', return_value=_bounded.BoundedResult(0, False)) as run, \
             patch('builtins.print'):
            module.main(['--url', 'https://example.com', '--goal', 'x', '--execute', '--max-steps', '1', '--max-seconds', '5'])
            self.assertEqual(run.call_args.kwargs['timeout_seconds'], 5)

    def test_doctor_requires_complete_backend_and_redacts_endpoint(self):
        module = self.load('doctor.py')
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(module, 'checkout_status', return_value={'present': True, 'pinned': True, 'dirty': False}), \
             patch.object(module, 'venv_status', return_value={'has_python': True}), \
             patch.object(module, 'tool_found', return_value=True), \
             patch.object(module, 'chrome_found', return_value=True), \
             patch.object(module, 'key_configured', return_value=True):
            env = dict(clean_env(Path(tmp)), TEXT_MODEL_API_KEY='test')
            report = module.build_report(env)
            self.assertFalse(report['prerequisites_present_for_type_text'])
            self.assertEqual(report['credentials']['text_model_backend_status'], 'partial')
            env.update(TEXT_MODEL_BASE_URL='https://user:PRIVATE_VALUE@example.com/private_path?x=PRIVATE_VALUE', TEXT_MODEL='test')
            report = module.build_report(env)
            self.assertFalse(report['prerequisites_present_for_type_text'])
            self.assertNotIn('PRIVATE_VALUE', json.dumps(report))
            self.assertNotIn('private_path', json.dumps(report))

    def test_goal_and_unrecognized_error_content_are_not_printed(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_python(RUN_PY, ['--url', 'https://example.com/private_path?token=PRIVATE_VALUE', '--goal', 'SENSITIVE_GOAL'], clean_env(Path(tmp)))
            self.assertNotIn('SENSITIVE_GOAL', result.stdout)
            self.assertNotIn('PRIVATE_VALUE', result.stdout)
            self.assertNotIn('private_path', result.stdout)
        self.assertNotIn('PRIVATE_VALUE', _bounded.safe_error_text(ValueError('payload PRIVATE_VALUE')))


class TracePrivacyTests(unittest.TestCase):
    def test_redact_step_excludes_label_text_and_url(self):
        step = {
            "step": 1,
            "action": "Click 'Submit payment for card ending 4242'",
            "operation": "CLICK",
            "probability": 0.9,
            "confidence": 0.95,
            "latency_ms": 120,
            "text": "4242 4242 4242 4242",
            "page_changed": True,
            "elapsed_ms": 500,
            "url": "https://example.com/checkout?card=4242424242424242",
        }
        redacted = _trace.redact_step(step, 1)
        self.assertNotIn("action", redacted)
        self.assertNotIn("url", redacted)
        self.assertNotIn("text", redacted)
        self.assertEqual(redacted["text_entered"], True)
        blob = json.dumps(redacted)
        self.assertNotIn("4242", blob)
        self.assertNotIn("Submit payment", blob)
        self.assertEqual(set(redacted), {"step", "operation", "probability", "confidence", "latency_ms", "page_changed", "elapsed_ms", "text_entered"})

    def test_redact_url_drops_query_fragment_and_credentials(self):
        self.assertEqual(
            _trace.redact_url("https://user:pass@example.com:8443/a/b?x=secret#frag"),
            "https://example.com:8443",
        )

    def test_build_trace_never_contains_raw_goal(self):
        trace = _trace.build_trace(
            url="https://example.com", goal="log into my bank account 12345", max_steps=3, max_seconds=30, auto_approve=False,
        )
        blob = json.dumps(trace)
        self.assertNotIn("bank account", blob)
        self.assertNotIn("12345", blob)
        self.assertIn("goal_sha256_only", trace)
        self.assertEqual(len(trace["goal_sha256_only"]), 64)

    def test_trace_file_written_atomically_at_0600_in_0700_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_dir = Path(tmp) / "nested" / "traces"
            trace_path = trace_dir / "trace.json"
            trace = _trace.build_trace(url="https://example.com", goal="x", max_steps=1, max_seconds=1, auto_approve=False)
            _trace.write_trace_atomic(trace_path, trace)

            self.assertTrue(trace_path.exists())
            self.assertEqual(trace_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(trace_dir.stat().st_mode & 0o777, 0o700)
            # no leftover temp file
            leftovers = [p for p in trace_dir.iterdir() if p.name != "trace.json"]
            self.assertEqual(leftovers, [])
            self.assertEqual(json.loads(trace_path.read_text())["schema"], "jev-ultrafast-trace.v2")

    def test_trace_write_failure_does_not_leave_partial_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "trace.json"
            trace = {"not": "json-serializable", "bad": object()}
            with self.assertRaises(TypeError):
                _trace.write_trace_atomic(trace_path, trace)
            self.assertFalse(trace_path.exists())
            leftovers = list(Path(tmp).glob(".trace-*"))
            self.assertEqual(leftovers, [])


class SafeErrorTextTests(unittest.TestCase):
    def test_bounded_length_no_traceback(self):
        try:
            raise RuntimeError("x" * 1000)
        except RuntimeError as exc:
            text = _bounded.safe_error_text(exc)
            self.assertLessEqual(len(text), 200)
            self.assertNotIn("Traceback", text)

    def test_redacts_messages_that_look_like_they_carry_a_token(self):
        try:
            raise RuntimeError("request failed: Authorization: Bearer sk-abcdef1234567890")
        except RuntimeError as exc:
            text = _bounded.safe_error_text(exc)
            self.assertNotIn("sk-abcdef1234567890", text)
            self.assertIn("redacted", text)


class DirtyCheckoutRejectionTests(unittest.TestCase):
    """Exercises setup.sh's verify_pinned_clean() by sourcing the script (its
    `main` never runs when sourced -- see the BASH_SOURCE guard at the
    bottom of setup.sh) against local fixture git repos. No network, no real
    upstream clone."""

    def _run_verify(self, repo_dir: Path, expected_commit: str) -> str:
        script = f'source "{SETUP_SH}"; verify_pinned_clean "{repo_dir}" "{expected_commit}"'
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=15)
        return result.stdout.strip()

    def _init_repo(self, repo_dir: Path) -> str:
        repo_dir.mkdir(parents=True)
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        subprocess.run(["git", "init", "-q", str(repo_dir)], check=True, env=env)
        (repo_dir / "f.txt").write_text("content\n")
        subprocess.run(["git", "-C", str(repo_dir), "add", "f.txt"], check=True, env=env)
        subprocess.run(["git", "-C", str(repo_dir), "commit", "-q", "-m", "init"], check=True, env=env)
        return subprocess.check_output(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], text=True, env=env).strip()

    def test_clean_checkout_at_expected_commit_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            commit = self._init_repo(repo)
            self.assertEqual(self._run_verify(repo, commit), "ok")

    def test_dirty_checkout_at_expected_commit_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            commit = self._init_repo(repo)
            (repo / "f.txt").write_text("modified locally\n")
            self.assertEqual(self._run_verify(repo, commit), "dirty")

    def test_untracked_file_also_counts_as_dirty(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            commit = self._init_repo(repo)
            (repo / "new_untracked.txt").write_text("x\n")
            self.assertEqual(self._run_verify(repo, commit), "dirty")

    def test_wrong_commit_is_reported_distinctly_from_dirty(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            self._init_repo(repo)
            result = self._run_verify(repo, "0" * 40)
            self.assertTrue(result.startswith("wrong_commit:"))

    def test_absent_checkout_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._run_verify(Path(tmp) / "nope", "0" * 40), "absent")

    def test_setup_sh_uses_frozen_sync(self):
        self.assertIn("uv sync --frozen", SETUP_SH.read_text())


class CheckoutReadyDirtyTests(unittest.TestCase):
    """run.py's own checkout_ready() must independently reject a dirty tree
    at the pinned commit, not rely solely on setup.sh having been run
    correctly earlier."""

    def test_dirty_tree_at_pinned_commit_rejected(self):
        spec = importlib.util.spec_from_file_location("jev_ultrafast_run", RUN_PY)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
            subprocess.run(["git", "init", "-q", str(repo)], check=True, env=env)
            (repo / "f.txt").write_text("x\n")
            subprocess.run(["git", "-C", str(repo), "add", "f.txt"], check=True, env=env)
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "i"], check=True, env=env)
            commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, env=env).strip()
            (repo / ".venv" / "bin").mkdir(parents=True)
            (repo / ".venv" / "bin" / "python").write_text("#!/bin/sh\n")

            module.PINNED_COMMIT = commit  # test-only: pin to our fixture commit
            ready, reason = module.checkout_ready(repo)
            self.assertTrue(ready, reason)

            (repo / "f.txt").write_text("dirty now\n")
            ready, reason = module.checkout_ready(repo)
            self.assertFalse(ready)
            self.assertIn("local changes", reason)


class TextModelRoutingTests(unittest.TestCase):
    """Key-only must never silently reach upstream's DeepSeek default."""

    def test_key_only_is_partial_not_configured(self):
        status, detail = _bounded.resolve_text_model_config({"TEXT_MODEL_API_KEY": "sk-test"})
        self.assertEqual(status, _bounded.TEXT_MODEL_PARTIAL)
        self.assertIsNone(detail)

    def test_none_set_is_unset(self):
        status, _ = _bounded.resolve_text_model_config({})
        self.assertEqual(status, _bounded.TEXT_MODEL_UNSET)

    def test_all_three_https_is_configured(self):
        status, _ = _bounded.resolve_text_model_config(
            {"TEXT_MODEL_API_KEY": "sk-test", "TEXT_MODEL_BASE_URL": "https://api.example.com/v1", "TEXT_MODEL": "m"}
        )
        self.assertEqual(status, _bounded.TEXT_MODEL_CONFIGURED)

    def test_http_base_url_rejected_even_if_all_three_set(self):
        status, detail = _bounded.resolve_text_model_config(
            {"TEXT_MODEL_API_KEY": "sk-test", "TEXT_MODEL_BASE_URL": "http://api.example.com/v1", "TEXT_MODEL": "m"}
        )
        self.assertEqual(status, _bounded.TEXT_MODEL_INVALID_BASE_URL)
        self.assertIn("HTTPS", detail)

    def test_embedded_credentials_in_base_url_rejected(self):
        status, detail = _bounded.resolve_text_model_config(
            {"TEXT_MODEL_API_KEY": "sk-test", "TEXT_MODEL_BASE_URL": "https://u:p@api.example.com/v1", "TEXT_MODEL": "m"}
        )
        self.assertEqual(status, _bounded.TEXT_MODEL_INVALID_BASE_URL)
        self.assertNotIn("u:p", detail)

    def test_run_py_execute_refuses_key_only_config_and_never_reaches_deepseek(self):
        # End-to-end: a bare TEXT_MODEL_API_KEY must never let --execute launch
        # the subprocess that would otherwise silently talk to upstream's
        # default https://api.deepseek.com/v1. No network call is made here;
        # this asserts run.py refuses *before* spawning anything.
        with tempfile.TemporaryDirectory() as tmp:
            env = clean_env(Path(tmp))
            env["TEXT_MODEL_API_KEY"] = "sk-live-looking-secret"
            result = run_python(
                RUN_PY,
                ["--url", "https://example.com", "--goal", "x", "--execute", "--max-steps", "3", "--max-seconds", "30"],
                env,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("must all be set together", result.stderr)
            self.assertNotIn("sk-live-looking-secret", result.stdout)
            self.assertNotIn("sk-live-looking-secret", result.stderr)
            self.assertNotIn("deepseek.com", result.stdout.lower())

    def test_run_py_dry_run_reports_partial_status_without_echoing_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = clean_env(Path(tmp))
            env["TEXT_MODEL_API_KEY"] = "sk-live-looking-secret"
            result = run_python(RUN_PY, ["--url", "https://example.com", "--goal", "x"], env)
            self.assertIn("Text-model backend status: partial", result.stdout)
            self.assertNotIn("sk-live-looking-secret", result.stdout)


if __name__ == "__main__":
    unittest.main()
