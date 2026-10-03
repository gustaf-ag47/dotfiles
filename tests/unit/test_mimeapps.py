"""Mail associations must be portable, not transient per-host launcher names."""
import configparser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class MimeAppsTests(unittest.TestCase):
    def test_thunderbird_uses_installed_distribution_desktop_id(self):
        text = (ROOT / 'config/mimeapps/mimeapps.list').read_text()
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(text)
        for section in ('Default Applications', 'Added Associations'):
            for mime in ('x-scheme-handler/mailto', 'message/rfc822',
                         'x-scheme-handler/mid', 'x-scheme-handler/net.thunderbird'):
                self.assertEqual(config[section][mime], 'org.mozilla.Thunderbird.desktop;')
        self.assertNotIn('userapp-Thunderbird-', text)


if __name__ == '__main__':
    unittest.main()
