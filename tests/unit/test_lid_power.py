"""lid-power (xps14): decision table and no-root behaviour."""

import os
import subprocess
import sys
import unittest
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "system/hosts/xps14/files/usr/local/bin/lid-power"
# No __pycache__ inside system/: install-system.sh would ship it to /usr/local/bin.
sys.dont_write_bytecode = True
_loader = SourceFileLoader("lid_power", str(SCRIPT))
_spec = importlib.util.spec_from_loader("lid_power", _loader)
lp = importlib.util.module_from_spec(_spec)
_loader.exec_module(lp)


def plan(lid, ac, sav=False, kbd=0, saved=None):
    return lp.plan(lid_closed=lid, on_ac=ac, we_set_sav=sav, kbd_level=kbd, kbd_saved=saved)


class PlanTest(unittest.TestCase):
    def test_closed_on_battery_enters_power_saver(self):
        self.assertEqual(plan(True, False), [("tlp", "power-saver")])

    def test_closed_on_battery_is_idempotent(self):
        self.assertEqual(plan(True, False, sav=True), [])

    def test_closed_on_ac_never_power_saver(self):
        # Docked with the lid shut: keep desk performance.
        self.assertEqual(plan(True, True), [])
        self.assertEqual(plan(True, True, sav=True), [("tlp", "ac")])

    def test_open_restores_battery_profile(self):
        self.assertEqual(plan(False, False, sav=True), [("tlp", "bat")])

    def test_manual_power_saver_is_left_alone(self):
        self.assertEqual(plan(False, False, sav=False), [])

    def test_keyboard_backlight_off_and_restored(self):
        self.assertEqual(plan(True, True, kbd=2), [("kbd", 0)])
        self.assertEqual(plan(True, True, kbd=0, saved=2), [])
        self.assertEqual(plan(False, True, saved=2), [("kbd", 2)])
        self.assertEqual(plan(True, True, kbd=0), [])


class ShapeTest(unittest.TestCase):
    def test_executable(self):
        self.assertTrue(os.access(SCRIPT, os.X_OK))

    def test_refuses_apply_as_user(self):
        if os.geteuid() == 0:
            self.skipTest("running as root")
        out = subprocess.run([str(SCRIPT), "--apply"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 1)
        self.assertIn("needs root", out.stderr)

    def test_enabled_for_xps14(self):
        services = (ROOT / "system/hosts/xps14/services").read_text()
        self.assertIn("enable lid-power.service", services)


if __name__ == "__main__":
    unittest.main()
