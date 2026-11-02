"""install.sh must enable user units only after their ExecStart targets exist.

Units run ~/.local/bin/* (linked by the bin/ loop) and ~/.pi/agent/skills/*
(provisioned by pi-setup). Enabling earlier made every first install fail the
first start of llm-proxy, host-pressure-alert and the delegate timers.
"""

import os
import re
import subprocess
import tempfile
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

    def test_dangling_units_retired_right_before_enable(self):
        call = line_of(r"^enable_user_units\s*$")
        self.assertEqual(line_of(r"retire_dangling_units$"), call - 1)


def function_source(name: str) -> str:
    start = line_of(rf"^{name}\(\) \{{")
    end = next(i for i in range(start, len(INSTALL)) if INSTALL[i] == "}")
    return "\n".join(INSTALL[start:end + 1])


class RetireDanglingUnitsTest(unittest.TestCase):
    """A unit renamed in the repo (claude-token-proxy -> llm-proxy) must be stopped and unlinked."""

    def test_stops_disables_and_unlinks_only_dangling_repo_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dotfiles, xdg, fake = tmp / "dotfiles", tmp / "xdg", tmp / "fakebin"
            repo_units, user = dotfiles / "config/systemd/user", xdg / "systemd/user"
            for d in (repo_units, user / "default.target.wants", fake):
                d.mkdir(parents=True)
            (repo_units / "llm-proxy.service").write_text("[Service]\n")
            (user / "llm-proxy.service").symlink_to(repo_units / "llm-proxy.service")
            (user / "claude-token-proxy.service").symlink_to(repo_units / "claude-token-proxy.service")
            (user / "default.target.wants/claude-token-proxy.service").symlink_to(user / "claude-token-proxy.service")
            (user / "default.target.wants/llm-proxy.service").symlink_to(user / "llm-proxy.service")
            (user / "private.service").symlink_to(tmp / "elsewhere/private.service")  # not ours: keep
            calls = tmp / "calls"
            (fake / "systemctl").write_text(f'#!/bin/bash\necho "$*" >> "{calls}"\n')
            (fake / "systemctl").chmod(0o755)
            script = function_source("retire_dangling_units") + "\nretire_dangling_units\n"
            env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}",
                   "DOTFILES": str(dotfiles), "XDG_CONFIG_HOME": str(xdg)}
            r = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("retired: claude-token-proxy.service", r.stdout)
            self.assertFalse(os.path.lexists(user / "claude-token-proxy.service"))
            self.assertFalse(os.path.lexists(user / "default.target.wants/claude-token-proxy.service"))
            self.assertTrue((user / "llm-proxy.service").exists())
            self.assertTrue(os.path.lexists(user / "default.target.wants/llm-proxy.service"))
            self.assertTrue(os.path.lexists(user / "private.service"))
            self.assertEqual(calls.read_text().splitlines(),
                             ["--user stop claude-token-proxy.service", "--user disable claude-token-proxy.service"])


if __name__ == "__main__":
    unittest.main()
