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
                "XDG_RUNTIME_DIR": tmp,
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

    def test_unchanged_layout_adopts_fresh_pi_sidecar_for_last(self):
        # resurrect's save.sh deletes a new snapshot identical to "last" AFTER
        # the post-save-layout hook wrote its .pi sidecar. The fresh pane ->
        # pi session map must land on "last", and "last" counts as saved now.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resurrect = root / "resurrect"
            resurrect.mkdir()
            last_file = resurrect / "tmux_resurrect_last.txt"
            last_file.write_text("pane\n" * 20)
            Path(str(last_file) + ".pi").write_text("S\t1\t1\t/old.jsonl\n")
            os.utime(last_file, (1000, 1000))
            (resurrect / "last").symlink_to(last_file.name)
            self._fake_env(root, resurrect, (
                f"d={str(resurrect)!r}\n"
                "f=$d/tmux_resurrect_new.txt\n"
                "printf 'S\\t1\\t1\\t/new.jsonl\\n' > \"$f.pi\"\n"  # hook output
                # identical to last: save.sh removes the new snapshot
            ))
            result = self._run(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((resurrect / "last").resolve(), last_file)
            self.assertEqual(Path(str(last_file) + ".pi").read_text(), "S\t1\t1\t/new.jsonl\n")
            self.assertFalse((resurrect / "tmux_resurrect_new.txt.pi").exists())
            self.assertGreater(last_file.stat().st_mtime, 1000)

    def test_orphaned_saving_spinner_is_killed_even_when_save_fails(self):
        # A save.sh that dies before stop_spinner leaves tmux_spinner.sh
        # looping "Saving..." in the status line forever.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resurrect = root / "resurrect"
            resurrect.mkdir()
            self._fake_env(root, resurrect, "exit 3\n")
            scripts = root / "config/tmux/plugins/tmux-resurrect/scripts"
            spinner = scripts / "tmux_spinner.sh"
            spinner.write_text("#!/bin/bash\nwhile true; do sleep 0.1; done\n")
            spinner.chmod(0o755)
            orphan = subprocess.Popen(["bash", str(spinner), "Saving...", "saved!"])
            try:
                result = self._run(root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNotNone(orphan.wait(timeout=5))
            finally:
                orphan.kill()

    def test_concurrent_save_waits_for_lock_then_skips(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resurrect = root / "resurrect"
            resurrect.mkdir()
            marker = root / "ran"
            self._fake_env(root, resurrect, f"touch {str(marker)!r}\n")
            holder = subprocess.Popen(
                ["flock", str(root / "tmux-safe-save.lock"), "sleep", "30"]
            )
            try:
                for _ in range(50):
                    if (root / "tmux-safe-save.lock").exists():
                        break
                    subprocess.run(["sleep", "0.1"])
                result = self._run(root, {"TMUX_SAFE_SAVE_LOCK_WAIT": "1"})
            finally:
                holder.kill()
                holder.wait()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("still running", result.stdout)
            self.assertFalse(marker.exists())

    def _fake_env(self, root, resurrect, body):
        config = root / "config/tmux/plugins/tmux-resurrect/scripts"
        config.mkdir(parents=True)
        save = config / "save.sh"
        save.write_text("#!/bin/bash\nset -e\n" + body)
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

    def _run(self, root, extra=None):
        env = os.environ | (extra or {}) | {
            "HOME": str(root),
            "XDG_RUNTIME_DIR": str(root),
            "XDG_CONFIG_HOME": str(root / "config"),
            "PATH": f"{root / 'bin'}:{os.environ['PATH']}",
        }
        return subprocess.run([str(ROOT / "bin/tmux-safe-save")], capture_output=True, text=True, env=env)


if __name__ == "__main__":
    unittest.main()
