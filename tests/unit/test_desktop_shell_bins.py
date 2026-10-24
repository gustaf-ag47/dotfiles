"""bin/keys, bin/sysstat, bin/battery-menu, bin/popover: text/JSON paths, no desktop needed."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BIN = Path(__file__).resolve().parents[2] / "bin"
HYPR = Path(__file__).resolve().parents[2] / "config" / "gui" / "Wayland" / "hypr"


def run(script, *args, env=None):
    e = os.environ.copy()
    e.update(env or {})
    return subprocess.run(["bash", str(BIN / script), *args],
                          capture_output=True, text=True, env=e, timeout=15)


class KeysTest(unittest.TestCase):
    def test_renders_sections_and_binds_from_repo_keymap(self):
        with tempfile.TemporaryDirectory() as tmp:
            host = Path(tmp) / "host.conf"
            host.write_text("## Host\nbind = $mainMod, O, exec, picker\n")
            r = run("keys", "--text", env={
                "HYPR_KEYMAP": str(HYPR / "keymap.conf"),
                "HYPR_HOST_CONF": str(host),
            })
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertTrue(out.startswith("APPS & WINDOWS\n"), out[:60])
        self.assertIn("SCRATCHPADS\n", out)
        self.assertIn("HOST\n", out)
        self.assertIn("picker", out)
        # Super+/ opens this sheet; $mainMod rendered as the glyph, slash as "/".
        self.assertRegex(out, r"󰘳 /\s+keys")
        # Explanatory (single '#') comments never become headers.
        self.assertNotIn("NEIGHBOURING MONITOR", out)

    def test_every_keymap_bind_has_a_section(self):
        keymap = (HYPR / "keymap.conf").read_text().splitlines()
        section = None
        for line in keymap:
            if line.startswith("## "):
                section = line
            elif line.lstrip().startswith("bind"):
                self.assertIsNotNone(section, f"bind before any '## Section': {line}")


class SysstatTest(unittest.TestCase):
    def test_waybar_json_has_text_class_tooltip(self):
        r = run("sysstat", "--waybar")
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(set(payload), {"text", "class", "tooltip"})
        self.assertIn(payload["class"], {"ok", "warn", "crit"})
        self.assertRegex(payload["tooltip"], r"cpu \d+%  mem \d+%  disk \d+%")

    def test_thresholds_drive_class(self):
        calm = run("sysstat", "--waybar", env={
            "SYSSTAT_WARN_CPU": "101", "SYSSTAT_WARN_MEM": "101",
            "SYSSTAT_WARN_DISK": "101", "SYSSTAT_WARN_TEMP": "1000",
            "SYSSTAT_CRIT_CPU": "101", "SYSSTAT_CRIT_MEM": "101",
            "SYSSTAT_CRIT_DISK": "101", "SYSSTAT_CRIT_TEMP": "1000",
        })
        self.assertEqual(json.loads(calm.stdout)["class"], "ok")
        self.assertRegex(json.loads(calm.stdout)["text"], r"^󰍛 \d+%  ?󰘚 \d+%$")
        hot = run("sysstat", "--waybar", env={"SYSSTAT_WARN_MEM": "0", "SYSSTAT_CRIT_MEM": "0"})
        self.assertEqual(json.loads(hot.stdout)["class"], "crit")
        self.assertIn("󰘚", json.loads(hot.stdout)["text"])


def fake_power_supply(tmp):
            ps = Path(tmp)
            bat = ps / "BAT0"
            bat.mkdir()
            for name, val in {
                "type": "Battery", "status": "Charging", "capacity": "74",
                "cycle_count": "10", "current_now": "1814000", "voltage_now": "12026000",
                "charge_full": "5962000", "charge_full_design": "5962000",
                "charge_types": "Trickle [Fast] Standard Adaptive Custom",
                "charge_control_start_threshold": "95", "charge_control_end_threshold": "100",
            }.items():
                (bat / name).write_text(val + "\n")
            src = ps / "ucsi-source-psy-USBC000:003"
            src.mkdir()
            (src / "online").write_text("1\n")
            (src / "voltage_now").write_text("18000000\n")
            (src / "current_now").write_text("5000000\n")
            mouse = ps / "hidpp_battery_0"
            mouse.mkdir()
            (mouse / "type").write_text("Battery\n")
            (mouse / "scope").write_text("Device\n")
            (mouse / "capacity").write_text("3\n")
            return ps


class BatteryMenuTest(unittest.TestCase):
    def test_text_reads_fake_sysfs(self):
        with tempfile.TemporaryDirectory() as tmp:
            ps = fake_power_supply(tmp)
            r = run("battery-menu", "--text", env={"POWER_SUPPLY_DIR": str(ps), "PATH": "/usr/bin:/bin"})
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertIn("74%", lines[0])
        self.assertIn("21.8 W", lines[0])
        self.assertIn("Fast (ExpressCharge)", lines[1])
        self.assertIn("18 V · 5 A", lines[2])
        self.assertIn("100% · 10 cycles", lines[3])
        self.assertNotIn("3%", r.stdout)

    def test_json_for_the_eww_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            ps = fake_power_supply(tmp)
            r = run("battery-menu", "--json", env={"POWER_SUPPLY_DIR": str(ps), "PATH": "/usr/bin:/bin"})
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertEqual((d["cap"], d["status"], d["mode"], d["pd"]), (74, "charging", "Fast", "18 V · 5 A"))
        self.assertEqual(d["watts"], "21.8")
        self.assertIsInstance(d["can_set"], bool)

    def test_set_rejects_unknown_mode(self):
        r = run("battery-menu", "--set", "Turbo", env={"PATH": "/usr/bin:/bin"})
        self.assertEqual(r.returncode, 2)


class PopoverDataTest(unittest.TestCase):
    """`popover data <topic>` feeds eww; each must be one JSON object with the
    keys the yuck dereferences, even when the backing tool is absent."""

    def test_sys_shape(self):
        r = run("popover", "data", "sys", env={"PATH": f"{BIN}:/usr/bin:/bin"})
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertEqual(set(d), {"cpu", "mem", "disk", "temp", "load", "up", "procs"})
        self.assertTrue(all({"name", "cpu", "mem"} <= set(p) for p in d["procs"]))

    def test_llm_shape_without_providers(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub = Path(tmp) / "llm-usage"
            stub.write_text("#!/bin/sh\nexit 1\n")
            stub.chmod(0o755)
            r = run("popover", "data", "llm", env={"PATH": f"{tmp}:/usr/bin:/bin"})
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertEqual(d["percent"], 0)
        self.assertEqual(d["lines"][0]["name"], "unavailable")

    def test_yuck_only_references_known_topics_and_actions(self):
        yuck = (Path(__file__).resolve().parents[2] / "config/gui/Wayland/eww/eww.yuck").read_text()
        popover = (BIN / "popover").read_text()
        import re
        for topic, action in set(re.findall(r"popover act (\w+) (\w+)", yuck)):
            self.assertIn(f"{topic}:{action})", popover, f"{topic}:{action} has no handler in bin/popover")
        for topic in set(re.findall(r"popover data (\w+)", yuck)):
            self.assertIn(f"data_{topic}()", popover)


if __name__ == "__main__":
    unittest.main()
