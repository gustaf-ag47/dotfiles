"""DONE claims fail closed against fake GitHub ancestry and per-SHA CI."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
loader = importlib.machinery.SourceFileLoader("delegate_verify", str(ROOT / "bin/delegate-verify"))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.report = self.root / "report.md"
        self.report.write_text("merged: true\n")
        self.sha = "a" * 40
        self.pr = {"number": 12, "head": {"sha": self.sha}, "merge_commit_sha": "b" * 40,
                   "merged_at": "2026-01-01", "base": {"ref": "main", "repo": {"full_name": "owner/repo"}}}
        self.checks = [{"id": 1, "name": "unit", "status": "completed", "conclusion": "success", "details_url": "https://ci/123"}]
        self.statuses = []
        self.comparison = "ahead"
        self.ci_sha = self.sha
        self.required = ["unit"]
        mock = patch.object(module, "api", side_effect=self.api)
        mock.start()
        self.addCleanup(mock.stop)
        mock = patch.object(module.subprocess, "run", side_effect=lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps([{"name": n} for n in self.required]), ""))
        mock.start()
        self.addCleanup(mock.stop)

    def api(self, repo, endpoint, cwd, pages=False):
        if endpoint.endswith("/pulls?per_page=100"):
            return [[self.pr]]
        if "/check-runs?" in endpoint:
            return [{"check_runs": self.checks}]
        if "/statuses?" in endpoint:
            return [self.statuses]
        if endpoint.startswith("compare/"):
            return {"status": self.comparison}
        if endpoint.startswith("actions/runs/"):
            return {"head_sha": self.ci_sha, "status": "completed", "conclusion": "success", "html_url": "https://ci/123"}
        return {"sha": self.sha}

    def verify(self, suffix=""):
        return module.verify(f"task: DONE {self.sha} - {self.report}{suffix}", str(self.root), "owner/repo")

    def test_green_commit_and_merge_ancestry_pass(self):
        self.assertIn("PASS owner/repo@", self.verify(" ci:123"))
        self.assertIn("merged on base", self.verify())

    def test_red_pending_and_missing_required_fail(self):
        for status, conclusion in [("completed", "failure"), ("in_progress", None), ("completed", "cancelled")]:
            self.checks[0].update(status=status, conclusion=conclusion)
            with self.assertRaisesRegex(ValueError, "red checks"):
                self.verify()
        self.checks = []
        with self.assertRaisesRegex(ValueError, "missing"):
            self.verify()

    def test_unreachable_merge_and_false_merge_claim_fail(self):
        self.comparison = "behind"
        with self.assertRaisesRegex(ValueError, "reachable"):
            self.verify()
        self.comparison = "ahead"
        self.pr["merged_at"] = None
        with self.assertRaisesRegex(ValueError, "not merged"):
            self.verify()

    def test_wrong_ci_sha_fails_even_when_run_is_green(self):
        self.ci_sha = "c" * 40
        with self.assertRaisesRegex(ValueError, "not green for claimed SHA"):
            self.verify(" ci:123")

    def test_duplicate_check_name_from_other_app_cannot_hide_failure(self):
        self.checks[0]["app"] = {"id": 1}
        self.checks.append(dict(self.checks[0], id=2, app={"id": 2}, conclusion="failure"))
        with self.assertRaisesRegex(ValueError, "red checks"):
            self.verify()

    def test_latest_rerun_wins_for_same_app(self):
        self.checks[0]["conclusion"] = "failure"
        self.checks.append(dict(self.checks[0], id=2, conclusion="success"))
        self.assertIn("PASS", self.verify())

    def test_no_checks_and_skipped_only_never_claim_green(self):
        self.required = []
        self.checks = []
        with self.assertRaisesRegex(ValueError, "no CI evidence"):
            self.verify()
        self.checks = [{"id": 1, "name": "skip", "status": "completed", "conclusion": "skipped"}]
        with self.assertRaisesRegex(ValueError, "no successful"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
