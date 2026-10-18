"""hypr-power-profile: pick ac/battery from sysfs and drive hyprctl keywords."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "bin" / "hypr-power-profile"


def supply(root, name, kind, online=None, scope=None):
    d = root / name
    d.mkdir()
    (d / "type").write_text(kind + "\n")
    if online is not None:
        (d / "online").write_text(f"{online}\n")
    if scope is not None:
        (d / "scope").write_text(scope + "\n")


class HyprPowerProfileTest(unittest.TestCase):
    def run_script(self, supplies, *args):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ps = root / "power_supply"
            ps.mkdir()
            supplies(ps)
            log = root / "hyprctl.log"
            (root / "hyprctl").write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$HYPRCTL_LOG"\n')
            (root / "hyprctl").chmod(0o755)
            env = os.environ.copy()
            env.update(PATH=f"{root}:{env['PATH']}", POWER_SUPPLY_DIR=str(ps), HYPRCTL_LOG=str(log))
            run = subprocess.run(["bash", str(SCRIPT), *args], text=True, capture_output=True, env=env, timeout=10)
            calls = log.read_text().splitlines() if log.exists() else []
            return run, calls

    def test_battery_disables_blur_and_shadow(self):
        def layout(ps):
            supply(ps, "BAT0", "Battery")
            supply(ps, "AC", "Mains", online=0)
        run, calls = self.run_script(layout)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(calls), 1)
        self.assertIn("decoration:blur:enabled false", calls[0])
        self.assertIn("decoration:shadow:enabled false", calls[0])

    def test_ac_restores_effects(self):
        def layout(ps):
            supply(ps, "ADP1", "Mains", online=1)
        run, calls = self.run_script(layout)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("decoration:blur:enabled true", calls[0])
        self.assertIn("decoration:shadow:enabled true", calls[0])

    def test_peripheral_mains_is_ignored(self):
        def layout(ps):
            supply(ps, "hid-mouse", "Mains", online=1, scope="Device")
            supply(ps, "AC", "Mains", online=0)
        run, _ = self.run_script(layout, "--status")
        self.assertEqual(run.stdout.strip(), "battery")

    def test_no_adapter_means_ac(self):
        run, calls = self.run_script(lambda ps: None, "--status")
        self.assertEqual(run.stdout.strip(), "ac")
        self.assertEqual(calls, [])

    def test_unknown_argument_fails(self):
        run, _ = self.run_script(lambda ps: None, "--bogus")
        self.assertEqual(run.returncode, 2)


if __name__ == "__main__":
    unittest.main()
