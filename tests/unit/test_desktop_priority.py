"""desktop-priority: idle-class stray panes, low weight for background services."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "bin/desktop-priority"


class DesktopPriorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.um = t / "user@1000.service"
        self.log = t / "calls"
        for d, idle, weight in [
            ("tmux-spawn-a.scope", "0", "100"),            # stray pane beside app.slice
            ("app.slice/tmux-spawn-b.scope", "0", "100"),  # stray pane inside app.slice
            ("app.slice/tmux-spawn-c.scope", "1", "100"),  # already idle
            ("agents.slice/tmux-spawn-d.scope", "0", "100"),
            ("app.slice/app-com.mitchellh.ghostty.service", "0", "100"),
            ("app.slice/waybar.service", "0", "100"),
            ("app.slice/tmux.service", "0", "20"),          # kept: restored
            ("app.slice/syncthing.service", "0", "100"),
            ("app.slice/log-sentinel.service", "0", "20"),  # already low
        ]:
            p = self.um / d
            p.mkdir(parents=True)
            (p / "cpu.idle").write_text(idle + "\n")
            (p / "cpu.weight").write_text(weight + "\n")
        bindir = t / "bin"
        bindir.mkdir()
        fake = bindir / "systemctl"
        fake.write_text(f'#!/bin/sh\necho "$@" >> {self.log}\n')
        fake.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}",
                    "DESKTOP_PRIORITY_CGROUP": str(self.um)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_applies_only_where_needed(self):
        subprocess.run([str(SCRIPT)], env=self.env, check=True, capture_output=True)
        calls = sorted(self.log.read_text().splitlines())
        self.assertEqual(calls, sorted([
            "--user set-property --runtime tmux-spawn-a.scope CPUWeight=idle",
            "--user set-property --runtime tmux-spawn-b.scope CPUWeight=idle",
            "--user set-property --runtime syncthing.service CPUWeight=20 IOWeight=20",
            "--user set-property --runtime tmux.service CPUWeight=100 IOWeight=100",
        ]))

    def test_dry_run_changes_nothing(self):
        out = subprocess.run([str(SCRIPT), "--dry-run"], env=self.env, check=True,
                             capture_output=True, text=True).stdout
        self.assertIn("would set syncthing.service", out)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
