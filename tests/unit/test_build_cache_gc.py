import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "bin/build-cache-gc"


class BuildCacheGcTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name)
        (self.cache / "README").write_text("go cache\n")
        (self.cache / "ab").mkdir()
        self.fresh = self.cache / "ab/fresh-d"
        self.cold = self.cache / "ab/cold-d"
        self.warm = self.cache / "ab/warm-a"
        for path, age_h in ((self.fresh, 0), (self.cold, 72), (self.warm, 12)):
            path.write_text("x")
            t = time.time() - age_h * 3600
            os.utime(path, (t, t))

    def tearDown(self):
        self.tmp.cleanup()

    def run_gc(self, root_pct, *args):
        env = dict(
            os.environ,
            BUILD_CACHE_GC_GOCACHE=str(self.cache),
            BUILD_CACHE_GC_ROOT_PCT=str(root_pct),
            BUILD_CACHE_GC_DOCKER="0",
        )
        out = subprocess.run(["bash", str(SCRIPT), *args], env=env, check=True, capture_output=True, text=True)
        return out.stdout

    def test_normal_disk_drops_only_entries_idle_for_two_days(self):
        out = self.run_gc(50)
        self.assertIn("gocache_idle_h=48", out)
        self.assertFalse(self.cold.exists())
        self.assertTrue(self.warm.exists())
        self.assertTrue(self.fresh.exists())
        self.assertTrue((self.cache / "README").exists())

    def test_disk_pressure_drops_entries_idle_for_six_hours(self):
        out = self.run_gc(88)
        self.assertIn("gocache_idle_h=6", out)
        self.assertFalse(self.cold.exists())
        self.assertFalse(self.warm.exists())
        self.assertTrue(self.fresh.exists())

    def test_dry_run_deletes_nothing(self):
        out = self.run_gc(88, "--dry-run")
        self.assertIn("would-remove: go_entries=2", out)
        self.assertTrue(self.cold.exists())

    def test_directory_without_go_readme_is_left_alone(self):
        (self.cache / "README").unlink()
        self.run_gc(88)
        self.assertTrue(self.cold.exists())


if __name__ == "__main__":
    unittest.main()
