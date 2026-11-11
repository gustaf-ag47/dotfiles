"""bin/waybar-hotplug: find monitors without a Waybar surface, restart only then."""

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "bin" / "waybar-hotplug"
loader = SourceFileLoader("waybar_hotplug", str(SCRIPT))
spec = spec_from_loader("waybar_hotplug", loader)
WH = module_from_spec(spec)
loader.exec_module(WH)

MONITORS = [{"name": "eDP-1"}, {"name": "DP-1"}, {"name": "DP-2"}, {"name": "HDMI-A-1", "disabled": True}]


def layers(**per_monitor):
    """layers(eDP_1=["waybar"]) -> hyprctl -j layers shape (top level "2")."""
    return {mon.replace("_", "-"): {"levels": {"2": [{"namespace": ns} for ns in names]}}
            for mon, names in per_monitor.items()}


class MissingBarsTest(unittest.TestCase):
    def test_after_hotplug_only_the_laptop_panel_has_a_bar(self):
        # The state seen on xps14: Waybar alive, bars gone from both externals.
        got = WH.missing_bars(MONITORS, layers(eDP_1=["waybar"], DP_1=[], DP_2=["swaync"]))
        self.assertEqual(got, ["DP-1", "DP-2"])

    def test_all_bars_present_and_disabled_monitors_ignored(self):
        got = WH.missing_bars(MONITORS, layers(eDP_1=["waybar"], DP_1=["waybar"], DP_2=["waybar"]))
        self.assertEqual(got, [])

    def test_monitor_missing_from_layers_counts(self):
        self.assertEqual(WH.missing_bars([{"name": "DP-3"}], {}), ["DP-3"])


class EventsTest(unittest.TestCase):
    def test_only_monitor_events_trigger(self):
        self.assertTrue(WH.is_monitor_event("monitoradded>>DP-1"))
        self.assertTrue(WH.is_monitor_event("monitoraddedv2>>2,DP-1,Dell"))
        self.assertTrue(WH.is_monitor_event("monitorremoved>>DP-1"))
        self.assertFalse(WH.is_monitor_event("workspace>>3"))
        self.assertFalse(WH.is_monitor_event("activewindow>>kitty,monitoradded"))


class CheckAndFixTest(unittest.TestCase):
    def setUp(self):
        self.saved = (WH.hyprctl_json, WH.subprocess.run)
        self.calls = []
        WH.subprocess.run = lambda cmd, **kw: self.calls.append(cmd)

    def tearDown(self):
        WH.hyprctl_json, WH.subprocess.run = self.saved

    def state(self, lay):
        WH.hyprctl_json = lambda what: MONITORS if what == "monitors" else lay

    def test_restarts_waybar_when_a_bar_is_missing(self):
        self.state(layers(eDP_1=["waybar"]))
        self.assertFalse(WH.check_and_fix())
        self.assertEqual(self.calls, [["systemctl", "--user", "restart", "waybar.service"]])

    def test_leaves_a_healthy_waybar_alone(self):
        self.state(layers(eDP_1=["waybar"], DP_1=["waybar"], DP_2=["waybar"]))
        self.assertTrue(WH.check_and_fix())
        self.assertEqual(self.calls, [])

    def test_unreadable_state_does_not_restart(self):
        def boom(what):
            raise ValueError("bad json")
        WH.hyprctl_json = boom
        self.assertTrue(WH.check_and_fix())
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
