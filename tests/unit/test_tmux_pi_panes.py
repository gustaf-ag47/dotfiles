import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
_loader = importlib.machinery.SourceFileLoader("tmux_pi_panes", str(ROOT / "bin/tmux-pi-panes"))
panes = importlib.util.module_from_spec(importlib.util.spec_from_loader(_loader.name, _loader))
_loader.exec_module(panes)


class SidecarFormatTest(unittest.TestCase):
    def test_round_trips_session_names_with_spaces(self):
        rows = [("Delta Reign Pre-Release", "3", "0", "/s/a b.jsonl")]
        self.assertEqual(panes.parse_rows(panes.format_rows(rows)), rows)

    def test_skips_malformed_lines(self):
        self.assertEqual(panes.parse_rows("x\t1\t0\n\t1\t0\t/f\n"), [])


class SessionFileForPidTest(unittest.TestCase):
    def test_reads_path_written_by_the_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "4242").write_text("/s/one.jsonl\n")
            self.assertEqual(panes.session_file_for_pid("4242", Path(tmp)), "/s/one.jsonl")
            self.assertIsNone(panes.session_file_for_pid("7", Path(tmp)))


class CarryForwardTest(unittest.TestCase):
    # On shutdown pi dies before tmux's final save; keep its pane's last
    # known session, but only for panes that still exist without pi.
    def test_keeps_previous_row_for_pane_that_lost_pi(self):
        previous = [("A", "1", "0", "/old.jsonl"), ("A", "2", "0", "/gone.jsonl")]
        kept = panes.carry_forward([], previous, pi_less={("A", "1", "0")})
        self.assertEqual(kept, [("A", "1", "0", "/old.jsonl")])

    def test_current_row_wins_over_previous(self):
        current = [("A", "1", "0", "/new.jsonl")]
        previous = [("A", "1", "0", "/old.jsonl")]
        self.assertEqual(panes.carry_forward(current, previous, pi_less=set()), current)


class PreviousSidecarTest(unittest.TestCase):
    def test_picks_latest_sidecar_older_than_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            for stamp in ("20261015T180000", "20261015T181000", "20261015T182000"):
                Path(tmp, f"tmux_resurrect_{stamp}.txt.pi").write_text("")
            snapshot = Path(tmp, "tmux_resurrect_20261015T182000.txt")
            self.assertEqual(panes.previous_sidecar(snapshot).name, "tmux_resurrect_20261015T181000.txt.pi")


class RestoreTest(unittest.TestCase):
    def test_resumes_shell_panes_and_falls_back_to_plain_pi(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp, "tmux_resurrect_1.txt")
            snap.write_text("pane\n")
            Path(tmp, "last").symlink_to(snap.name)
            live = Path(tmp, "live session.jsonl")
            live.write_text("{}\n")
            Path(str(snap) + ".pi").write_text(panes.format_rows([
                ("S", "1", "0", str(live)),
                ("S", "2", "0", str(live)),          # pane runs something else
                ("S", "3", "0", str(Path(tmp, "missing.jsonl"))),
            ]))
            commands = {"S:1.0": "zsh", "S:2.0": "nvim", "S:3.0": "zsh"}
            sent = []

            def fake_tmux(*args):
                if args[0] == "display-message":
                    return mock.Mock(returncode=0, stdout=commands[args[3]] + "\n")
                if args[0] == "send-keys":
                    sent.append(args)
                return mock.Mock(returncode=0, stdout="")

            with mock.patch.object(panes, "resurrect_dir", return_value=Path(tmp)), \
                 mock.patch.object(panes, "live_session_files", return_value=set()), \
                 mock.patch.object(panes, "tmux", side_effect=fake_tmux):
                panes.cmd_restore()
            self.assertEqual(sent[0], ("send-keys", "-t", "S:1.0", "-l", "--", f"pi --session '{live}'"))
            self.assertEqual(sent[1], ("send-keys", "-t", "S:1.0", "Enter"))
            # unused pi (no .jsonl yet) still comes back as a plain pi
            self.assertEqual(sent[2], ("send-keys", "-t", "S:3.0", "-l", "--", "pi"))
            self.assertEqual(len(sent), 4)


class GuessSessionFileTest(unittest.TestCase):
    # pi started before the extension existed: no state file, argv overwritten,
    # no fd on the .jsonl. Only cwd + start time + file mtimes are available.
    def _proc(self, tmp, pid, cwd, start_ticks):
        proc = Path(tmp, "proc")
        (proc / str(pid)).mkdir(parents=True, exist_ok=True)
        (proc / "stat").write_text("cpu 1 2 3\nbtime 1000\n")
        (proc / str(pid) / "cwd").symlink_to(cwd)
        # after ") ": state is field 0, starttime (man proc: field 22) is 19
        fields = ["S"] + ["0"] * 18 + [str(start_ticks)]
        (proc / str(pid) / "stat").write_text(f"{pid} (pi) " + " ".join(fields) + "\n")
        return proc

    def _file(self, root, cwd, name, mtime):
        d = panes.session_dir_for_cwd(cwd, root)
        d.mkdir(parents=True, exist_ok=True)
        f = d / name
        f.write_text("{}\n")
        os.utime(f, (mtime, mtime))
        return str(f)

    def test_unique_file_written_after_start_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            tck = os.sysconf("SC_CLK_TCK")
            proc = self._proc(tmp, 42, "/work/a", start_ticks=100 * tck)  # start = 1100
            root = Path(tmp, "sessions")
            old = self._file(root, "/work/a", "old.jsonl", 1050)
            live = self._file(root, "/work/a", "live.jsonl", 1200)
            self.assertEqual(panes.guess_session_file(42, set(), proc, root), live)
            # a file another live pi already claims is never a candidate
            self.assertIsNone(panes.guess_session_file(42, {live}, proc, root))
            self.assertNotEqual(panes.guess_session_file(42, set(), proc, root), old)

    def test_two_candidates_is_ambiguous_not_a_guess(self):
        with tempfile.TemporaryDirectory() as tmp:
            tck = os.sysconf("SC_CLK_TCK")
            proc = self._proc(tmp, 42, "/work/a", start_ticks=100 * tck)
            root = Path(tmp, "sessions")
            self._file(root, "/work/a", "x.jsonl", 1200)
            self._file(root, "/work/a", "y.jsonl", 1300)
            self.assertIsNone(panes.guess_session_file(42, set(), proc, root))

    def test_session_dir_layout(self):
        self.assertEqual(panes.session_dir_for_cwd("/tmp", Path("/r")), Path("/r/--tmp--"))
        self.assertEqual(panes.session_dir_for_cwd("/a/b c", Path("/r")), Path("/r/--a-b c--"))


if __name__ == "__main__":
    unittest.main()
