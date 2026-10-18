"""net-recover / net-watchdog / netchange: shape checks that need no root."""

import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECOVER = ROOT / "system/common/files/usr/local/bin/net-recover"
WATCHDOG = ROOT / "system/hosts/skrubben/files/usr/local/bin/net-watchdog"
NETCHANGE = ROOT / "bin/netchange"


class NetRecoverTest(unittest.TestCase):
    def test_dry_run_lists_every_step_without_root(self):
        out = subprocess.run(["bash", str(RECOVER), "--dry-run"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        for step in ("step 1", "step 2", "step 3", "step 4"):
            self.assertIn(step, out.stdout)
        self.assertIn("ip rule del not fwmark 51820 table 51820", out.stdout)
        self.assertIn("systemctl restart tailscaled", out.stdout)

    def test_refuses_to_run_for_real_as_user(self):
        if os.geteuid() == 0:
            self.skipTest("running as root")
        out = subprocess.run(["bash", str(RECOVER)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 1)
        self.assertIn("needs root", out.stderr)

    def test_scripts_are_executable_and_parse(self):
        for script in (RECOVER, WATCHDOG, NETCHANGE):
            self.assertTrue(os.access(script, os.X_OK), script)
            self.assertEqual(subprocess.run(["bash", "-n", str(script)]).returncode, 0, script)

    def test_watchdog_is_enabled_for_skrubben(self):
        services = (ROOT / "system/hosts/skrubben/services").read_text()
        self.assertIn("enable net-watchdog.timer", services)

    def test_netchange_usage(self):
        out = subprocess.run([str(NETCHANGE), "--help"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0)
        self.assertIn("netchange keep", out.stdout)
        bad = subprocess.run([str(NETCHANGE), "up", "--"], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)


if __name__ == "__main__":
    unittest.main()
