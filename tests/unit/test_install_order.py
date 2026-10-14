"""install.sh must enable user units only after their ExecStart targets exist.

Units run ~/.local/bin/* (linked by the bin/ loop) and ~/.pi/agent/skills/*
(provisioned by pi-setup). Enabling earlier made every first install fail the
first start of claude-token-proxy, host-pressure-alert and the delegate timers.
"""

import re
import unittest
from pathlib import Path

INSTALL = (Path(__file__).resolve().parents[2] / "scripts/install.sh").read_text().splitlines()


def line_of(pattern: str) -> int:
    hits = [i for i, line in enumerate(INSTALL) if re.search(pattern, line)]
    if len(hits) != 1:
        raise AssertionError(f"expected one match for {pattern!r}, got {len(hits)}")
    return hits[0]


class InstallOrderTest(unittest.TestCase):
    def test_units_enabled_after_bin_links_and_pi_setup(self):
        call = line_of(r"^enable_user_units\s*$")
        self.assertGreater(call, line_of(r'^for script in "\$DOTFILES/bin/"\*'))
        self.assertGreater(call, line_of(r'"\$DOTFILES/bin/pi-setup" --apply'))

    def test_enable_is_the_only_unit_start(self):
        starts = [i for i, line in enumerate(INSTALL) if "enable --now" in line and not line.lstrip().startswith("#")]
        body = range(line_of(r"^enable_user_units\(\) \{"), line_of(r"^enable_user_units\s*$"))
        hermes = [i for i in starts if i not in body]
        # Only the skrubben Hermes snapshot block may start a unit outside the function.
        for i in hermes:
            self.assertIn("hermes-state-snapshot", "\n".join(INSTALL[max(0, i - 3):i + 1]))


if __name__ == "__main__":
    unittest.main()
