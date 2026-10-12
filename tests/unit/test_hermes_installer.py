"""Regression checks for keeping Hermes snapshot writes on skrubben only."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class HermesInstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.installer = (ROOT / 'scripts/install.sh').read_text()

    def test_snapshot_units_are_not_linked_on_other_hosts(self):
        self.assertIn('RUNNING_HOSTNAME="$(cat /etc/hostname', self.installer)
        self.assertIn(
            'if [ "$RUNNING_HOSTNAME" != "skrubben" ] && [[ "$unit_name" == hermes-state-snapshot.* ]]; then',
            self.installer,
        )

    def test_snapshot_timer_requires_gateway_host_and_all_bind_mounts(self):
        self.assertIn(
            'if [ "$RUNNING_HOSTNAME" = "skrubben" ] && [ "${PROFILE:-$RUNNING_HOSTNAME}" = "skrubben" ]',
            self.installer,
        )
        for state_dir in ('memories', 'skills', 'handovers', 'scripts', 'assets', 'sessions'):
            self.assertIn(state_dir, self.installer)
        self.assertIn('if ! mountpoint -q "$HOME/.hermes/$state_dir"; then', self.installer)
        self.assertIn('systemctl --user enable --now hermes-state-snapshot.timer', self.installer)

    def test_non_gateway_removes_only_managed_snapshot_unit_links(self):
        self.assertIn('disable_hermes_snapshot_units', self.installer)
        self.assertIn('systemctl --user disable --now hermes-state-snapshot.timer', self.installer)
        self.assertIn(
            '[ "$(readlink -f "$target")" = "$(readlink -f "$source")" ]',
            self.installer,
        )


if __name__ == '__main__':
    unittest.main()
