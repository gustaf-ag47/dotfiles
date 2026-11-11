"""bin/terminal: one launcher maps --class/--title/-e onto each emulator's CLI."""

from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TERMINAL = ROOT / "bin" / "terminal"

# Fake emulator: records its argv (one arg per line) and exits with $STUB_RC.
STUB = """#!/bin/bash
{ echo "${0##*/}"; printf '%s\\n' "$@"; echo ---; } >>"$STUB_LOG"
exit "${STUB_RC:-0}"
"""


class TerminalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = self.dir / "log"

    def tearDown(self):
        self.tmp.cleanup()

    def run_with(self, emulators, *args, env=None):
        bindir = Path(tempfile.mkdtemp(dir=self.dir))
        for name in emulators:
            stub = bindir / name
            stub.write_text(STUB)
            stub.chmod(0o755)
        e = {"PATH": str(bindir), "STUB_LOG": str(self.log), "HOME": str(self.dir)}
        e.update(env or {})
        r = subprocess.run(["/bin/bash", str(TERMINAL), *args],
                           capture_output=True, text=True, env=e, timeout=15)
        calls = []
        if self.log.exists():
            calls = [c.strip("\n").split("\n") for c in self.log.read_text().split("---\n") if c.strip()]
        return r, calls

    def test_ghostty_is_preferred(self):
        r, calls = self.run_with(["alacritty", "ghostty"], "-e", "htop")
        self.assertEqual(calls, [["ghostty", "+new-window", "-e", "htop"]])

    def test_alacritty_is_the_fallback_and_gets_class_title_command(self):
        r, calls = self.run_with(["alacritty", "kitty"], "--class", "dotfiles.calc",
                                 "--title", "Calculator", "-e", "python3", "-c", "print(1)")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(calls, [["alacritty", "--class", "dotfiles.calc", "--title", "Calculator",
                                  "-e", "python3", "-c", "print(1)"]])

    def test_override_selects_alacritty(self):
        r, calls = self.run_with(["alacritty", "ghostty"], "-e", "nvim", "a b",
                                 env={"DOTFILES_TERMINAL": "alacritty"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(calls, [["alacritty", "-e", "nvim", "a b"]])

    def test_ghostty_falls_back_to_standalone_when_new_window_fails(self):
        r, calls = self.run_with(["ghostty"], "--title=T", env={"STUB_RC": "1"})
        self.assertEqual(calls, [["ghostty", "+new-window", "--title=T"], ["ghostty", "--title=T"]])
        self.assertEqual(r.returncode, 1)  # the fallback's own status

    def test_ghostty_class_starts_own_instance_with_class_first(self):
        r, calls = self.run_with(["ghostty"], "--class=dotfiles.scratchpad", "-e", "btop")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(calls, [["ghostty", "--class=dotfiles.scratchpad",
                                  "--quit-after-last-window-closed=true", "-e", "btop"]])

    def test_foot_uses_app_id_and_positional_command(self):
        r, calls = self.run_with(["foot"], "--class", "dotfiles.x", "-e", "lf")
        self.assertEqual(calls, [["foot", "--app-id", "dotfiles.x", "lf"]])

    def test_args_after_e_are_never_parsed_as_options(self):
        r, calls = self.run_with(["alacritty"], "-e", "sh", "-c", "echo --class")
        self.assertEqual(calls, [["alacritty", "-e", "sh", "-c", "echo --class"]])

    def test_double_dash_is_an_alias_for_e(self):
        r, calls = self.run_with(["alacritty"], "--", "htop")
        self.assertEqual(calls, [["alacritty", "-e", "htop"]])

    def test_errors(self):
        r, calls = self.run_with(["alacritty"], "--bogus")
        self.assertEqual((r.returncode, calls), (2, []))
        self.assertIn("unknown option", r.stderr)
        r, _ = self.run_with(["alacritty"], "-e")
        self.assertEqual(r.returncode, 2)
        r, _ = self.run_with([])
        self.assertEqual(r.returncode, 1)
        self.assertIn("no terminal emulator", r.stderr)


class CallersTest(unittest.TestCase):
    """Launchers go through bin/terminal and use dotted classes (see bin/terminal)."""

    def test_no_launcher_names_an_emulator(self):
        paths = [ROOT / "bin" / "terminal-calculator", ROOT / "config/gui/Wayland/hypr/pyprland.toml",
                 *sorted((ROOT / "config/applications").glob("*.desktop"))]
        for p in paths:
            self.assertFalse("alacritty" in p.read_text(), p)

    def test_window_classes_are_dotted(self):
        import re
        text = "\n".join(p.read_text() for p in [
            ROOT / "config/gui/Wayland/hypr/pyprland.toml", ROOT / "bin/terminal-calculator",
            ROOT / "bin/read-book"])
        classes = re.findall(r"--class[ =]\"?([\w.-]+)", text)
        self.assertTrue(classes)
        for c in classes:
            self.assertIn(".", c, c)


if __name__ == "__main__":
    unittest.main()
