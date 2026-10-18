import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class TmuxSafeSaveTest(unittest.TestCase):
    def test_near_empty_save_keeps_rich_last_and_pane_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resurrect = root / "resurrect"
            resurrect.mkdir()
            previous = resurrect / "tmux_resurrect_previous.txt"
            previous.write_text("pane\n" * 20)
            (resurrect / "last").symlink_to(previous.name)
            contents = resurrect / "pane_contents.tar.gz"
            contents.write_bytes(b"good scrollback")

            config = root / "config/tmux/plugins/tmux-resurrect/scripts"
            config.mkdir(parents=True)
            save = config / "save.sh"
            save.write_text(
                "#!/bin/bash\n"
                "set -e\n"
                f"d={str(resurrect)!r}\n"
                "f=$d/tmux_resurrect_skeleton.txt\n"
                "printf 'pane\\npane\\n' > \"$f\"\n"
                "ln -sfn \"$(basename \"$f\")\" \"$d/last\"\n"
                "printf 'bad scrollback' > \"$d/pane_contents.tar.gz\"\n"
            )
            save.chmod(0o755)
            fakebin = root / "bin"
            fakebin.mkdir()
            tmux = fakebin / "tmux"
            tmux.write_text(
                "#!/bin/bash\n"
                "case $1 in\n"
                "  list-sessions) printf 'Dotfiles: 1 windows\\nInStockachu: 1 windows\\n' ;;\n"
                f"  show-option) printf '%s\\n' {str(resurrect)!r} ;;\n"
                "  *) exit 1 ;;\n"
                "esac\n"
            )
            tmux.chmod(0o755)
            env = os.environ | {
                "HOME": tmp,
                "XDG_CONFIG_HOME": str(root / "config"),
                "PATH": f"{fakebin}:{os.environ['PATH']}",
            }
            result = subprocess.run(
                [str(ROOT / "bin/tmux-safe-save")], capture_output=True, text=True, env=env
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((resurrect / "last").resolve(), previous)
            self.assertEqual(contents.read_bytes(), b"good scrollback")
            self.assertIn("kept 'last'", result.stdout)


if __name__ == "__main__":
    unittest.main()
