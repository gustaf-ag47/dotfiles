"""Regression checks for X11 configuration wiring (config audit)."""

import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class XorgConfigTests(unittest.TestCase):
    def test_i3_loads_resources_before_starting_polybar(self):
        config = (ROOT / 'config/gui/Xorg/i3/config').read_text()
        self.assertRegex(
            config,
            r"exec --no-startup-id sh -c 'xrdb -merge .* && .*polybar/launch\.sh\"'",
        )
        if shutil.which('i3'):
            subprocess.run(['i3', '-C', '-c', str(ROOT / 'config/gui/Xorg/i3/config')],
                           check=True, capture_output=True, text=True)

    def test_polybar_palette_parses_without_x_server(self):
        config = ROOT / 'config/gui/Xorg/polybar/config.ini'
        text = config.read_text()
        self.assertNotIn('${xrdb:', text)
        self.assertNotIn('#{xrdb:', text)
        self.assertRegex(text, re.compile(r'^alert = #[0-9a-f]{6}$', re.MULTILINE))
        if shutil.which('polybar'):
            result = subprocess.run(['polybar', '-c', str(config), '-d', 'foreground'],
                                    check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), '#c0caf5')

    def test_gtk2_has_default_lookup_path(self):
        installer = (ROOT / 'scripts/install.sh').read_text()
        self.assertIn('link_config "$DOTFILES/config/gui/gtk-2.0/gtkrc" "$HOME/.gtkrc-2.0"',
                      installer)


if __name__ == '__main__':
    unittest.main()
