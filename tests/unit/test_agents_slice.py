"""tmux panes share one low-weight agents.slice (desktop responsiveness)."""
import configparser
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USER_UNITS = ROOT / "config/systemd/user"


def _ini(path: Path) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(strict=False)
    cp.optionxform = str
    cp.read(path)
    return cp


class AgentsSliceTests(unittest.TestCase):
    def test_slice_is_below_app_slice_default_weight(self):
        cp = _ini(USER_UNITS / "agents.slice")
        self.assertEqual(cp["Slice"]["CPUWeight"], "idle")
        self.assertLess(int(cp["Slice"]["IOWeight"]), 100)
        self.assertEqual(cp["Slice"]["ManagedOOMMemoryPressure"], "kill")

    def test_every_pane_scope_joins_the_slice(self):
        cp = _ini(USER_UNITS / "tmux-spawn-.scope.d/50-background.conf")
        self.assertEqual(cp["Scope"]["Slice"], "agents.slice")
        # A per-pane weight would be meaningless inside the slice and misleading.
        self.assertNotIn("CPUWeight", cp["Scope"])

    def test_installer_links_slice_and_drop_in(self):
        text = (ROOT / "scripts/install.sh").read_text()
        self.assertIn('config/systemd/user/agents.slice" "$XDG_CONFIG_HOME/systemd/user/agents.slice"', text)
        self.assertIn('config/systemd/user/tmux-spawn-.scope.d" "$XDG_CONFIG_HOME/systemd/user/tmux-spawn-.scope.d"', text)


if __name__ == "__main__":
    unittest.main()
