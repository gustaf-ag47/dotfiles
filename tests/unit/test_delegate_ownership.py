"""Ownership reservations serialize launches and staged checks fail closed."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "bin/delegate-owns-check"


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.env = os.environ | {"PI_DELEGATE_OWNERS_DIR": str(self.root / "claims")}

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, stderr=subprocess.DEVNULL)

    def reserve(self, name, pattern, *extra):
        manifest = self.root / f"{name}.json"
        manifest.write_text(json.dumps({"status": "open", "owns": [pattern], "cwd": str(self.repo)}))
        return subprocess.run([str(HELPER), "--reserve", "--run-id", name, "--manifest", str(manifest),
                               "--cwd", str(self.repo), "--owns", pattern, *extra], env=self.env, text=True, capture_output=True)

    def test_overlap_rejected_but_disjoint_and_override_allowed(self):
        self.assertEqual(self.reserve("one", "src/**").returncode, 0)
        result = self.reserve("two", "src/feature/*.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("owner one", result.stderr)
        self.assertEqual(self.reserve("three", "tests/**").returncode, 0)
        result = self.reserve("four", "src/feature.py", "--allow-overlap")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WARNING", result.stdout)

    def test_closed_lane_releases_ownership(self):
        self.assertEqual(self.reserve("one", "src/**").returncode, 0)
        (self.root / "one.json").write_text(json.dumps({"status": "closed"}))
        self.assertEqual(self.reserve("two", "src/**").returncode, 0)

    def test_claims_are_scoped_to_repository(self):
        self.assertEqual(self.reserve("one", "src/**").returncode, 0)
        self.repo = self.root / "different-repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.assertEqual(self.reserve("two", "src/**").returncode, 0)

    def test_concurrent_conflicting_reservations_have_one_winner(self):
        commands = []
        for name in ("one", "two"):
            manifest = self.root / f"{name}.json"
            manifest.write_text(json.dumps({"status": "open"}))
            commands.append(subprocess.Popen([str(HELPER), "--reserve", "--run-id", name,
                "--manifest", str(manifest), "--cwd", str(self.repo), "--owns", "src/**"],
                env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        for process in commands:
            process.communicate(timeout=10)
        self.assertEqual(sorted(p.returncode for p in commands), [0, 1])

    def test_staged_outside_files_fail_and_owned_pass(self):
        manifest = self.root / "lane.json"
        manifest.write_text(json.dumps({"owns": ["src/**"], "cwd": str(self.repo)}))
        (self.repo / "src").mkdir()
        (self.repo / "src/file.py").write_text("allowed")
        (self.repo / "outside.txt").write_text("not allowed")
        self.git("add", ".")
        def check():
            return subprocess.run([str(HELPER), "--manifest", str(manifest)], env=self.env, text=True, capture_output=True)
        result = check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("outside.txt", result.stdout)
        self.git("rm", "--cached", "outside.txt")
        self.assertEqual(check().returncode, 0)

    def test_invalid_glob_fails_closed(self):
        for pattern in ("/etc/**", "../outside", ""):
            self.assertNotEqual(self.reserve("invalid", pattern).returncode, 0)


if __name__ == "__main__":
    unittest.main()
