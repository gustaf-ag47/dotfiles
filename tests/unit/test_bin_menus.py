"""Exercise bin scripts without invoking desktop or Docker services."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


BIN = Path(__file__).resolve().parents[2] / "bin"


class MenuTest(unittest.TestCase):
    def test_docker_cleanup_menu_keeps_first_option(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "fzf").write_text("""#!/bin/bash
input=$(cat)
if [ ! -f "$FZF_COUNT_FILE" ]; then
  touch "$FZF_COUNT_FILE"; echo cleanup
elif [ ! -f "$FZF_INPUT_FILE" ]; then
  printf '%s' "$input" > "$FZF_INPUT_FILE"; echo back
else echo exit; fi
""")
            (root / "docker").write_text("#!/bin/bash\nexit 0\n")
            (root / "clear").write_text("#!/bin/bash\nexit 0\n")
            for name in ("fzf", "docker", "clear"):
                (root / name).chmod(0o755)
            env = os.environ.copy()
            env.update(
                PATH=f"{root}:{env['PATH']}",
                FZF_COUNT_FILE=str(root / "count"),
                FZF_INPUT_FILE=str(root / "input"),
            )
            run = subprocess.run(
                ["bash", str(BIN / "fzf-docker")], input="", text=True,
                capture_output=True, env=env, timeout=10,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            options = (root / "input").read_text().splitlines()
            self.assertEqual(options[0], "prune-containers    - Remove all stopped containers")
            self.assertIn("back                - Back to main menu", options)

    def test_volume_uses_theme_icon(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "pulsemixer").write_text("#!/bin/bash\necho '42 42'\n")
            (root / "pulsemixer").chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{root}:{env['PATH']}"
            for flag, icon in (("--get-icon", "audio-volume-medium"),
                               ("--get-mic-icon", "audio-input-microphone")):
                run = subprocess.run(["bash", str(BIN / "volume"), flag],
                                     capture_output=True, text=True, env=env)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout.strip(), icon)


if __name__ == "__main__":
    unittest.main()
