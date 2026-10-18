"""mimeapps.list: mail and Slack open in the terminal/web launchers, not removed GUI apps."""

import configparser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class MimeAppsTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / 'config/mimeapps/mimeapps.list').read_text()
        self.config = configparser.ConfigParser(interpolation=None)
        self.config.read_string(self.text)

    def test_mail_goes_to_neomutt_launcher(self):
        defaults = self.config['Default Applications']
        self.assertEqual(defaults['x-scheme-handler/mailto'], 'email.desktop;')
        self.assertEqual(defaults['message/rfc822'], 'email.desktop;')
        self.assertTrue((ROOT / 'config/applications/email.desktop').exists())

    def test_slack_links_open_the_web_client(self):
        self.assertEqual(self.config['Default Applications']['x-scheme-handler/slack'], 'slack-web.desktop')
        self.assertTrue((ROOT / 'config/applications/slack-web.desktop').exists())

    def test_no_handlers_for_removed_gui_apps(self):
        for name in ('Thunderbird', 'obsidian', 'postman', 'jetbrains', 'slack.desktop'):
            self.assertNotIn(name, self.text)

    def test_every_referenced_desktop_file_exists(self):
        for section in self.config.sections():
            for value in self.config[section].values():
                for desktop in filter(None, value.split(';')):
                    if desktop in ('firefox.desktop', 'claude-code-url-handler.desktop'):
                        continue
                    self.assertTrue((ROOT / 'config/applications' / desktop).exists(), desktop)


if __name__ == '__main__':
    unittest.main()
