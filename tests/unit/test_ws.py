import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]

SPEC_YAML = importlib.util.spec_from_file_location("ws_yaml", ROOT / "scripts/ws_yaml.py")
ws_yaml = importlib.util.module_from_spec(SPEC_YAML)
SPEC_YAML.loader.exec_module(ws_yaml)

SPEC_WS = importlib.util.spec_from_file_location("ws", ROOT / "scripts/ws.py")
ws = importlib.util.module_from_spec(SPEC_WS)
SPEC_WS.loader.exec_module(ws)

FIXTURE = """
env:
  SYNC: /home/example/sync
  NOTES: /home/example/sync/Vault
  DOTFILES: /home/example/sync/src/dotfiles
  SRC: /home/example/sync/src
  WORKTREES: /mnt/example/scratch/tmp
areas:
  - name: dotfiles
    session: Dotfiles
    cwd: /home/example/sync/src/dotfiles
    runs: /home/example/sync/Vault/Dotfiles/agent-runs
  - name: widgetco
    session: Widgetco
    cwd: /home/example/sync/src/widgetco/app
    runs: /home/example/sync/Vault/Widgetco/agent-runs
projects:
  - name: widgetco
    area: widgetco
    window_prefix: sub-
  - name: widgetco-admin
    area: widgetco
    cwd: /home/example/sync/src/widgetco/admin
    window_prefix: adm-
repos:
  - path: /home/example/sync/src/dotfiles
    remote: git@example.com:example/dotfiles.git
    area: dotfiles
units:
  - name: tmux.service
"""


class YamlSubsetTest(unittest.TestCase):
    def test_nested_mapping_and_list_of_mappings(self):
        doc = ws_yaml.load(FIXTURE)
        self.assertEqual(doc["env"]["SYNC"], "/home/example/sync")
        self.assertEqual(len(doc["areas"]), 2)
        self.assertEqual(doc["areas"][0]["name"], "dotfiles")
        self.assertEqual(doc["projects"][1]["cwd"], "/home/example/sync/src/widgetco/admin")


class RouteResolutionTest(unittest.TestCase):
    def setUp(self):
        self.doc = ws_yaml.load(FIXTURE)

    def test_route_to_declared_project(self):
        route = ws.resolve_route(self.doc, "widgetco")
        self.assertEqual(route["session"], "Widgetco")
        self.assertEqual(route["cwd"], "/home/example/sync/src/widgetco/app")
        self.assertEqual(route["window_prefix"], "sub-")

    def test_route_falls_back_to_area(self):
        route = ws.resolve_route(self.doc, "dotfiles")
        self.assertEqual(route["session"], "Dotfiles")
        self.assertEqual(route["runs"], "/home/example/sync/Vault/Dotfiles/agent-runs")

    def test_project_overrides_area_cwd(self):
        route = ws.resolve_route(self.doc, "widgetco-admin")
        self.assertEqual(route["session"], "Widgetco")
        self.assertEqual(route["cwd"], "/home/example/sync/src/widgetco/admin")
        self.assertEqual(route["window_prefix"], "adm-")

    def test_unknown_target_returns_none(self):
        self.assertIsNone(ws.resolve_route(self.doc, "does-not-exist"))


PROJECT_SESSION_FIXTURE = """
env:
  SYNC: /home/example/sync
  NOTES: /home/example/sync/Vault
  DOTFILES: /home/example/sync/src/dotfiles
  SRC: /home/example/sync/src
  WORKTREES: /mnt/example/scratch/tmp
areas:
  - name: dotfiles
    session: Dotfiles
    cwd: /home/example/sync/src/dotfiles
    runs: /home/example/sync/Vault/Dotfiles/agent-runs
projects:
  - name: fleet-state
    area: dotfiles
    session: Fleet-State
    cwd: /home/example/sync/src/fleet-state
"""


class DeclaredSessionsTest(unittest.TestCase):
    def test_project_session_overriding_its_area_is_declared(self):
        doc = ws_yaml.load(PROJECT_SESSION_FIXTURE)
        declared = ws.declared_sessions_with_cwd(doc)
        self.assertEqual(declared, {
            "Dotfiles": "/home/example/sync/src/dotfiles",
            "Fleet-State": "/home/example/sync/src/fleet-state",
        })

    def test_project_without_its_own_session_does_not_duplicate_its_area(self):
        doc = ws_yaml.load(FIXTURE)
        declared = ws.declared_sessions_with_cwd(doc)
        self.assertEqual(declared, {
            "Dotfiles": "/home/example/sync/src/dotfiles",
            "Widgetco": "/home/example/sync/src/widgetco/app",
        })


class CmdUpCreatesProjectSessionTest(unittest.TestCase):
    def test_creates_session_for_project_override_with_its_own_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace.yaml"
            workspace.write_text(PROJECT_SESSION_FIXTURE)
            args = argparse.Namespace(workspace=str(workspace), dry_run=False, non_interactive=True)
            with mock.patch.object(ws, "tmux_sessions", return_value=["Dotfiles"]), \
                 mock.patch.object(ws, "tmux") as tmux_mock, \
                 mock.patch.object(ws, "tmux_windows", return_value=[]), \
                 mock.patch.object(ws, "open_lanes", return_value=[]):
                tmux_mock.return_value = subprocess.CompletedProcess([], 0, "", "")
                ws.cmd_up(args)
            tmux_mock.assert_any_call(
                ["new-session", "-d", "-s", "Fleet-State", "-c", "/home/example/sync/src/fleet-state"]
            )


class RouteCliTest(unittest.TestCase):
    def test_route_subcommand_prints_four_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace.yaml"
            workspace.write_text(FIXTURE)
            run = subprocess.run(
                ["python3", str(ROOT / "scripts/ws.py"),
                 "--workspace", str(workspace), "route", "widgetco"],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            fields = run.stdout.strip().split()
            self.assertEqual(len(fields), 4)
            self.assertEqual(fields[0], "Widgetco")

    def test_route_unknown_target_is_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace.yaml"
            workspace.write_text(FIXTURE)
            run = subprocess.run(
                ["python3", str(ROOT / "scripts/ws.py"),
                 "--workspace", str(workspace), "route", "ghost-project"],
                capture_output=True, text=True, timeout=10,
            )
            self.assertNotEqual(run.returncode, 0)


class TmpWorktreeGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        root = Path(self.tmpdir.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        self.fake_tmp = root / "tmp-root"
        self.fake_tmp.mkdir()

        def git(*args):
            subprocess.run(
                ["git", "-C", str(self.repo), *args],
                check=True, capture_output=True, text=True,
                env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                     "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
            )

        git("init", "-q", "-b", "main")
        (self.repo / "README").write_text("hi\n")
        git("add", "README")
        git("commit", "-q", "-m", "init")

        # A real worktree, under the fake /tmp.
        self.real_worktree = self.fake_tmp / "wt-real-lane"
        git("worktree", "add", str(self.real_worktree), "-b", "real-lane")

        # A plain file matching the naming convention: not a worktree.
        (self.fake_tmp / "wt-skipped.txt").write_text("not a worktree\n")

        # A directory git has never heard of: also not a worktree, but
        # still worth surfacing separately so it doesn't vanish silently.
        (self.fake_tmp / "wt-stale-lane").mkdir()

    def test_real_worktree_is_the_only_hard_failure(self):
        found = ws.git_worktrees_under([str(self.repo)], tmp_root=str(self.fake_tmp))
        self.assertEqual(found, [str(self.real_worktree)])

    def test_log_file_and_stray_dir_are_not_reported_as_worktrees(self):
        found = ws.git_worktrees_under([str(self.repo)], tmp_root=str(self.fake_tmp))
        joined = " ".join(found)
        self.assertNotIn("wt-skipped.txt", joined)
        self.assertNotIn("wt-stale-lane", joined)

    def test_stray_dir_is_listed_separately_not_as_a_failure(self):
        found = ws.git_worktrees_under([str(self.repo)], tmp_root=str(self.fake_tmp))
        stray = ws.stray_tmp_dirs(found, tmp_root=str(self.fake_tmp))
        self.assertEqual(stray, [str(self.fake_tmp / "wt-stale-lane")])
        self.assertNotIn(str(self.real_worktree), stray)

    def test_log_file_never_appears_in_stray_dirs(self):
        found = ws.git_worktrees_under([str(self.repo)], tmp_root=str(self.fake_tmp))
        stray = ws.stray_tmp_dirs(found, tmp_root=str(self.fake_tmp))
        self.assertTrue(all(not s.endswith(".txt") for s in stray))


class LaneManifestTest(unittest.TestCase):
    def test_open_lanes_excludes_closed_and_malformed(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            lanes = runs / ".lanes"
            lanes.mkdir(parents=True)
            (lanes / "open.json").write_text(json.dumps({
                "session": "Demo", "window": "sub-open", "status": "open", "resume": "confirm",
            }))
            (lanes / "closed.json").write_text(json.dumps({
                "session": "Demo", "window": "sub-closed", "status": "closed", "resume": "auto",
            }))
            (lanes / "broken.json").write_text("not json")
            doc = {"areas": [{"name": "demo", "runs": str(runs)}]}
            lanes_found = ws.open_lanes(doc)
            self.assertEqual(len(lanes_found), 1)
            self.assertEqual(lanes_found[0]["window"], "sub-open")

    def test_open_lanes_also_scans_unrouted_lanes(self):
        # A session with no declared area (e.g. not yet added to
        # workspace.yaml) still gets a lane manifest, written under
        # NOTES/.unrouted-lanes/.lanes by both delegate.sh and
        # runs_dir_for_session. Without this, ws adopt can never see it was
        # already adopted and keeps re-adopting the same pane forever.
        with tempfile.TemporaryDirectory() as tmp:
            notes = Path(tmp) / "notes"
            unrouted_lanes = notes / ".unrouted-lanes" / ".lanes"
            unrouted_lanes.mkdir(parents=True)
            (unrouted_lanes / "open.json").write_text(json.dumps({
                "session": "Ghost", "window": "sub-ghost", "status": "open", "resume": "confirm",
            }))
            doc = {"areas": [], "env": {"NOTES": str(notes)}}
            lanes_found = ws.open_lanes(doc)
            self.assertEqual(len(lanes_found), 1)
            self.assertEqual(lanes_found[0]["window"], "sub-ghost")

    def test_lane_manifest_dirs_ignores_process_environ(self):
        # The doc is the only source of truth for NOTES; a NOTES exported in
        # this process' shell must never leak into what gets scanned.
        with mock.patch.dict(os.environ, {"NOTES": "/should/not/be/used"}):
            dirs = ws.lane_manifest_dirs({"areas": []})
        self.assertEqual(dirs, [])


class UnitsBusRetryTest(unittest.TestCase):
    def run_with_fake_systemctl(self, script_body, declared=None):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            fake = bin_dir / "systemctl"
            fake.write_text("#!/bin/bash\n" + script_body)
            fake.chmod(0o755)
            orig_path = os.environ.get("PATH", "")
            orig_runtime = os.environ.pop("XDG_RUNTIME_DIR", None)
            os.environ["PATH"] = str(bin_dir) + os.pathsep + orig_path
            try:
                return ws.check_declared_units(declared or {"tmux.service"})
            finally:
                os.environ["PATH"] = orig_path
                if orig_runtime is not None:
                    os.environ["XDG_RUNTIME_DIR"] = orig_runtime

    def test_retries_with_derived_runtime_dir_and_recovers(self):
        status, missing = self.run_with_fake_systemctl(
            "if [ -z \"${XDG_RUNTIME_DIR:-}\" ]; then\n"
            "  echo 'Failed to connect to bus: No such file or directory' >&2\n"
            "  exit 1\n"
            "fi\n"
            "echo enabled\n"
            "exit 0\n"
        )
        self.assertEqual(status, "ok")
        self.assertEqual(missing, [])

    def test_retries_against_real_systemd_env_i_wording_and_recovers(self):
        # systemd's actual message under `env -i` (no XDG_RUNTIME_DIR AND no
        # DBUS_SESSION_BUS_ADDRESS) is worded differently from the generic
        # "Failed to connect to bus" used above; a ws check run this way
        # reported every genuinely-enabled unit as "not enabled" until this
        # wording was also recognized as a bus failure, not a real answer.
        status, missing = self.run_with_fake_systemctl(
            "if [ -z \"${XDG_RUNTIME_DIR:-}\" ]; then\n"
            "  echo 'Failed to connect to user scope bus via local transport: "
            "$DBUS_SESSION_BUS_ADDRESS and $XDG_RUNTIME_DIR not defined' >&2\n"
            "  exit 1\n"
            "fi\n"
            "echo enabled\n"
            "exit 0\n"
        )
        self.assertEqual(status, "ok")
        self.assertEqual(missing, [])

    def test_reports_unknown_when_bus_stays_unreachable(self):
        status, missing = self.run_with_fake_systemctl(
            "echo 'Failed to connect to bus: No such file or directory' >&2\n" "exit 1\n"
        )
        self.assertEqual(status, "unknown")
        self.assertEqual(missing, [])

    def test_real_not_enabled_is_distinguished_from_bus_failure(self):
        status, missing = self.run_with_fake_systemctl("echo disabled\n" "exit 1\n")
        self.assertEqual(status, "not_enabled")
        self.assertEqual(missing, ["tmux.service"])


class PiSessionFileForPidTest(unittest.TestCase):
    # cwd + newest-mtime (the previous approach) is not evidence of which
    # session a long-running process is actually in: a `pi --continue` pane
    # starts a new .jsonl without changing cwd, and switches sessions over
    # its lifetime. An open file descriptor is the only unambiguous signal.
    def _make_fd(self, proc_root, pid, fd_num, target):
        fd_dir = Path(proc_root) / str(pid) / "fd"
        fd_dir.mkdir(parents=True, exist_ok=True)
        (fd_dir / str(fd_num)).symlink_to(target)

    def test_single_open_jsonl_fd_is_unambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = "/home/example/.pi/agent/sessions/--example--/abc.jsonl"
            self._make_fd(tmp, 111, 5, target)
            self._make_fd(tmp, 111, 6, "/dev/null")
            found = ws.pi_session_file_for_pid(111, proc_root=tmp)
            self.assertEqual(found, target)

    def test_multiple_open_jsonl_fds_are_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_fd(tmp, 222, 5, "/home/example/.pi/agent/sessions/--a--/one.jsonl")
            self._make_fd(tmp, 222, 6, "/home/example/.pi/agent/sessions/--b--/two.jsonl")
            found = ws.pi_session_file_for_pid(222, proc_root=tmp)
            self.assertIsNone(found)

    def test_no_jsonl_fd_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_fd(tmp, 333, 5, "/dev/null")
            found = ws.pi_session_file_for_pid(333, proc_root=tmp)
            self.assertIsNone(found)

    def test_missing_proc_entry_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = ws.pi_session_file_for_pid(9999, proc_root=tmp)
            self.assertIsNone(found)

    def test_jsonl_fd_outside_sessions_dir_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_fd(tmp, 444, 5, "/home/example/notes/random.jsonl")
            found = ws.pi_session_file_for_pid(444, proc_root=tmp)
            self.assertIsNone(found)


class FindPiPidTest(unittest.TestCase):
    def test_finds_pi_descendant_of_pane_shell(self):
        ps_text = (
            "  PID  PPID COMMAND\n"
            "  100     1 zsh\n"
            "  200   100 pi\n"
            "  300   100 other\n"
        )
        self.assertEqual(ws.find_pi_pid("100", ps_text=ps_text), "200")

    def test_returns_none_when_no_pi_descendant(self):
        ps_text = "  PID  PPID COMMAND\n" "  100     1 zsh\n" "  300   100 other\n"
        self.assertIsNone(ws.find_pi_pid("100", ps_text=ps_text))


class FindPiEnvVarTest(unittest.TestCase):
    def test_reads_var_from_fake_proc_environ(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc_root = Path(tmp)
            pid_dir = proc_root / "4242"
            pid_dir.mkdir()
            (pid_dir / "environ").write_bytes(
                b"PATH=/usr/bin\x00PI_DELEGATE_PARENT=Demo:orchestrator\x00"
            )
            value = ws.find_pi_env_var("4242", "PI_DELEGATE_PARENT", proc_root=str(proc_root))
            self.assertEqual(value, "Demo:orchestrator")

    def test_missing_proc_entry_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            value = ws.find_pi_env_var("9999", "PI_DELEGATE_PARENT", proc_root=tmp)
            self.assertIsNone(value)

    def test_none_pid_returns_none(self):
        self.assertIsNone(ws.find_pi_env_var(None, "PI_DELEGATE_PARENT"))


class UnmatchedAgentPanesTest(unittest.TestCase):
    def setUp(self):
        self.doc = ws_yaml.load(FIXTURE)

    def test_skips_orchestrator_and_hermes_windows(self):
        panes = [
            {"session": "Demo", "window": "orchestrator", "pane_pid": "1", "command": "pi", "cwd": "/x"},
            {"session": "Demo", "window": "hermes", "pane_pid": "2", "command": "pi", "cwd": "/x"},
            {"session": "Demo", "window": "sub-task", "pane_pid": "3", "command": "pi", "cwd": "/x"},
        ]
        found = ws.unmatched_agent_panes(self.doc, panes=panes, lanes=[])
        self.assertEqual([p["window"] for p in found], ["sub-task"])

    def test_skips_non_pi_panes(self):
        panes = [{"session": "Demo", "window": "shell", "pane_pid": "1", "command": "zsh", "cwd": "/x"}]
        found = ws.unmatched_agent_panes(self.doc, panes=panes, lanes=[])
        self.assertEqual(found, [])

    def test_skips_panes_with_open_manifest(self):
        panes = [{"session": "Demo", "window": "sub-task", "pane_pid": "1", "command": "pi", "cwd": "/x"}]
        lanes = [{"session": "Demo", "window": "sub-task", "status": "open"}]
        found = ws.unmatched_agent_panes(self.doc, panes=panes, lanes=lanes)
        self.assertEqual(found, [])

    def test_session_filter(self):
        panes = [
            {"session": "Demo", "window": "sub-a", "pane_pid": "1", "command": "pi", "cwd": "/x"},
            {"session": "Other", "window": "sub-b", "pane_pid": "2", "command": "pi", "cwd": "/x"},
        ]
        found = ws.unmatched_agent_panes(self.doc, session_filter="Demo", panes=panes, lanes=[])
        self.assertEqual([p["window"] for p in found], ["sub-a"])


class MultiPaneAgentWindowsTest(unittest.TestCase):
    def test_detects_window_with_two_pi_panes(self):
        panes = [
            {"session": "Demo", "window": "pi", "pane_id": "%1", "pane_pid": "10", "command": "pi", "cwd": "/x"},
            {"session": "Demo", "window": "pi", "pane_id": "%2", "pane_pid": "11", "command": "pi", "cwd": "/x"},
            {"session": "Demo", "window": "sub-a", "pane_id": "%3", "pane_pid": "12", "command": "pi", "cwd": "/x"},
        ]
        found = ws.multi_pane_agent_windows(panes=panes)
        self.assertEqual(found, {"Demo:pi": ["%1", "%2"]})

    def test_ignores_non_pi_panes_sharing_a_window(self):
        panes = [
            {"session": "Demo", "window": "pi", "pane_id": "%1", "pane_pid": "10", "command": "pi", "cwd": "/x"},
            {"session": "Demo", "window": "pi", "pane_id": "%2", "pane_pid": "11", "command": "zsh", "cwd": "/x"},
        ]
        found = ws.multi_pane_agent_windows(panes=panes)
        self.assertEqual(found, {})

    def test_single_pane_windows_are_not_reported(self):
        panes = [{"session": "Demo", "window": "pi", "pane_id": "%1", "pane_pid": "10", "command": "pi", "cwd": "/x"}]
        found = ws.multi_pane_agent_windows(panes=panes)
        self.assertEqual(found, {})


class CmdAdoptTest(unittest.TestCase):
    def setUp(self):
        self.doc = ws_yaml.load(FIXTURE)

    def _args(self, workspace, dry_run=False, session=None):
        return argparse.Namespace(workspace=str(workspace), dry_run=dry_run, session=session)

    def test_adopt_writes_manifest_for_unmatched_pane(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace.yaml"
            workspace.write_text(FIXTURE)
            lane_root = Path(tmp) / "runs"
            pane = {
                "session": "Dotfiles",
                "window": "sub-fix-thing",
                "pane_id": "%555",
                "pane_pid": "555",
                "command": "pi",
                "cwd": "/home/example/sync/src/dotfiles",
            }
            with mock.patch.object(ws, "tmux_agent_panes", return_value=[pane]), \
                 mock.patch.object(ws, "open_lanes", return_value=[]), \
                 mock.patch.object(ws, "runs_dir_for_session", return_value=str(lane_root)), \
                 mock.patch.object(ws, "find_pi_pid", return_value=None), \
                 mock.patch.object(ws, "git_branch_for", return_value="main"):
                rc = ws.cmd_adopt(self._args(workspace))
            self.assertEqual(rc, 0)
            lane_dir = lane_root / ".lanes"
            matches = list(lane_dir.glob("adopted-*.json")) if lane_dir.exists() else []
            self.assertTrue(matches, f"expected an adopted manifest under {lane_dir}")
            manifest = json.loads(matches[0].read_text())
            self.assertEqual(manifest["session"], "Dotfiles")
            self.assertEqual(manifest["window"], "sub-fix-thing")
            self.assertEqual(manifest["status"], "open")
            self.assertEqual(manifest["resume"], "confirm")
            self.assertTrue(manifest["adopted"])
            self.assertEqual(manifest["branch"], "main")
            self.assertIsNone(manifest["parent"])
            self.assertIsNone(manifest["pi_session"])
            self.assertEqual(manifest["pane"], "%555")

    def test_adopt_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace.yaml"
            workspace.write_text(FIXTURE)
            lanes_root = Path(tmp) / "dry-run-runs"
            pane = {
                "session": "Dotfiles",
                "window": "sub-dry",
                "pane_pid": "556",
                "command": "pi",
                "cwd": "/home/example/sync/src/dotfiles",
            }
            with mock.patch.object(ws, "tmux_agent_panes", return_value=[pane]), \
                 mock.patch.object(ws, "open_lanes", return_value=[]), \
                 mock.patch.object(ws, "runs_dir_for_session", return_value=str(lanes_root)), \
                 mock.patch.object(ws, "find_pi_pid", return_value=None):
                rc = ws.cmd_adopt(self._args(workspace, dry_run=True))
            self.assertEqual(rc, 0)
            self.assertFalse(lanes_root.exists())

    def test_adopt_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace.yaml"
            workspace.write_text(FIXTURE)
            lane = {"session": "Dotfiles", "window": "sub-already", "status": "open"}
            pane = {
                "session": "Dotfiles",
                "window": "sub-already",
                "pane_pid": "557",
                "command": "pi",
                "cwd": "/home/example/sync/src/dotfiles",
            }
            with mock.patch.object(ws, "tmux_agent_panes", return_value=[pane]), \
                 mock.patch.object(ws, "open_lanes", return_value=[lane]):
                rc = ws.cmd_adopt(self._args(workspace))
            self.assertEqual(rc, 0)


class LaneFixTest(unittest.TestCase):
    def test_fixes_raw_session_id_and_moves_manifest_when_window_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace.yaml"
            workspace.write_text(FIXTURE)
            unrouted = root / ".unrouted-lanes" / ".lanes"
            unrouted.mkdir(parents=True)
            bad = unrouted / "bad.json"
            bad.write_text(json.dumps({"session": "$1", "window": "sub-thing", "status": "open"}))
            doc = ws_yaml.load(FIXTURE)
            doc["env"]["NOTES"] = str(root)
            dest_root = root / "dotfiles-runs"
            with mock.patch.object(ws, "load_workspace", return_value=doc), \
                 mock.patch.object(ws, "tmux_windows", return_value=["Dotfiles:sub-thing"]), \
                 mock.patch.object(ws, "resolve_tmux_session_name", return_value="Dotfiles"), \
                 mock.patch.object(ws, "runs_dir_for_session", return_value=str(dest_root)):
                args = argparse.Namespace(workspace=str(workspace), dry_run=False)
                rc = ws.cmd_lane_fix(args)
            self.assertEqual(rc, 0)
            dest = dest_root / ".lanes" / "bad.json"
            self.assertTrue(dest.exists())
            manifest = json.loads(dest.read_text())
            self.assertEqual(manifest["session"], "Dotfiles")
            self.assertFalse(bad.exists())

    def test_closes_manifest_when_window_is_gone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace.yaml"
            workspace.write_text(FIXTURE)
            unrouted = root / ".unrouted-lanes" / ".lanes"
            unrouted.mkdir(parents=True)
            bad = unrouted / "bad.json"
            bad.write_text(json.dumps({"session": "$9", "window": "sub-gone", "status": "open"}))
            doc = ws_yaml.load(FIXTURE)
            doc["env"]["NOTES"] = str(root)
            with mock.patch.object(ws, "load_workspace", return_value=doc), \
                 mock.patch.object(ws, "tmux_windows", return_value=[]), \
                 mock.patch.object(ws, "resolve_tmux_session_name", return_value="Ghost"):
                args = argparse.Namespace(workspace=str(workspace), dry_run=False)
                rc = ws.cmd_lane_fix(args)
            self.assertEqual(rc, 0)
            manifest = json.loads(bad.read_text())
            self.assertEqual(manifest["status"], "closed")
            self.assertEqual(manifest["session"], "Ghost")

    def test_leaves_normal_session_names_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace.yaml"
            workspace.write_text(FIXTURE)
            unrouted = root / ".unrouted-lanes" / ".lanes"
            unrouted.mkdir(parents=True)
            fine = unrouted / "fine.json"
            fine.write_text(json.dumps({"session": "Dotfiles", "window": "sub-ok", "status": "open"}))
            doc = ws_yaml.load(FIXTURE)
            doc["env"]["NOTES"] = str(root)
            with mock.patch.object(ws, "load_workspace", return_value=doc), \
                 mock.patch.object(ws, "tmux_windows", return_value=[]), \
                 mock.patch.object(ws, "resolve_tmux_session_name") as resolve_mock:
                args = argparse.Namespace(workspace=str(workspace), dry_run=False)
                rc = ws.cmd_lane_fix(args)
            self.assertEqual(rc, 0)
            resolve_mock.assert_not_called()
            manifest = json.loads(fine.read_text())
            self.assertEqual(manifest["status"], "open")


class CmdLaneSetTest(unittest.TestCase):
    def test_sets_allowed_fields_by_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace.yaml"
            workspace.write_text(FIXTURE)
            lanes = root / "lanes" / ".lanes"
            lanes.mkdir(parents=True)
            manifest_path = lanes / "adopted-x-2528960.json"
            manifest_path.write_text(json.dumps({
                "run_id": "adopted-x-2528960", "session": "Demo", "window": "pi",
                "pi_session": "/some/stale/path.jsonl", "status": "open",
            }))
            doc = ws_yaml.load(FIXTURE)
            doc["areas"].append({"name": "demo", "session": "Demo", "cwd": "/x", "runs": str(root / "lanes")})
            with mock.patch.object(ws, "load_workspace", return_value=doc):
                args = argparse.Namespace(
                    workspace=str(workspace), target="adopted-x-2528960",
                    assignments=["window=pi-2", "pi_session=null"], dry_run=False,
                )
                rc = ws.cmd_lane_set(args)
            self.assertEqual(rc, 0)
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest["window"], "pi-2")
            self.assertIsNone(manifest["pi_session"])
            # Untouched fields survive the repair.
            self.assertEqual(manifest["session"], "Demo")

    def test_accepts_an_explicit_path_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace.yaml"
            workspace.write_text(FIXTURE)
            manifest_path = root / "direct.json"
            manifest_path.write_text(json.dumps({"session": "Demo", "status": "open"}))
            args = argparse.Namespace(
                workspace=str(workspace), target=str(manifest_path),
                assignments=["status=closed"], dry_run=False,
            )
            rc = ws.cmd_lane_set(args)
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(manifest_path.read_text())["status"], "closed")

    def test_rejects_disallowed_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace.yaml"
            workspace.write_text(FIXTURE)
            manifest_path = root / "x.json"
            manifest_path.write_text(json.dumps({"session": "Demo"}))
            args = argparse.Namespace(
                workspace=str(workspace), target=str(manifest_path),
                assignments=["run_id=hijacked"], dry_run=False,
            )
            rc = ws.cmd_lane_set(args)
            self.assertNotEqual(rc, 0)
            manifest = json.loads(manifest_path.read_text())
            self.assertNotIn("run_id", manifest)

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace.yaml"
            workspace.write_text(FIXTURE)
            manifest_path = root / "x.json"
            original = {"session": "Demo", "window": "pi"}
            manifest_path.write_text(json.dumps(original))
            args = argparse.Namespace(
                workspace=str(workspace), target=str(manifest_path),
                assignments=["window=pi-2"], dry_run=True,
            )
            rc = ws.cmd_lane_set(args)
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(manifest_path.read_text()), original)

    def test_target_not_found_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace.yaml"
            workspace.write_text(FIXTURE)
            args = argparse.Namespace(
                workspace=str(workspace), target="does-not-exist",
                assignments=["window=pi-2"], dry_run=False,
            )
            rc = ws.cmd_lane_set(args)
            self.assertNotEqual(rc, 0)


class ParseResultLineTest(unittest.TestCase):
    def test_parses_sha_and_path(self):
        parsed = ws.parse_result_line("demo: PASS abcdef1234567 - docs/report.md")
        self.assertEqual(parsed, {
            "result": "demo: PASS abcdef1234567 - docs/report.md",
            "result_status": "PASS",
            "result_sha": "abcdef1234567",
            "result_path": "docs/report.md",
        })

    def test_parses_none_sha(self):
        parsed = ws.parse_result_line("demo: BLOCKER none - docs/report.md")
        self.assertEqual(parsed["result_sha"], "none")
        self.assertEqual(parsed["result_status"], "BLOCKER")

    def test_task_name_with_colon_still_parses(self):
        parsed = ws.parse_result_line("demo: nested task: DONE abcdef1 - docs/x.md")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["result_status"], "DONE")
        self.assertEqual(parsed["result_sha"], "abcdef1")

    def test_rejects_non_matching_line(self):
        self.assertIsNone(ws.parse_result_line("demo: ACK abcdef1234567 - docs/report.md"))
        self.assertIsNone(ws.parse_result_line("not a result line"))
        self.assertIsNone(ws.parse_result_line(None))
        self.assertIsNone(ws.parse_result_line(""))


class CmdLaneSetResultTest(unittest.TestCase):
    def test_result_sets_structured_fields_and_finished_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace.yaml"
            workspace.write_text(FIXTURE)
            manifest_path = root / "x.json"
            manifest_path.write_text(json.dumps({"session": "Demo", "status": "open"}))
            args = argparse.Namespace(
                workspace=str(workspace), target=str(manifest_path),
                assignments=[], result="demo: PASS abcdef1234567 - docs/report.md",
                dry_run=False,
            )
            rc = ws.cmd_lane_set(args)
            self.assertEqual(rc, 0)
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest["result_status"], "PASS")
            self.assertEqual(manifest["result_sha"], "abcdef1234567")
            self.assertEqual(manifest["result_path"], "docs/report.md")
            self.assertIn("finished_at", manifest)
            # Untouched: --result does not close the lane by itself.
            self.assertEqual(manifest["status"], "open")

    def test_malformed_result_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace.yaml"
            workspace.write_text(FIXTURE)
            manifest_path = root / "x.json"
            manifest_path.write_text(json.dumps({"session": "Demo"}))
            args = argparse.Namespace(
                workspace=str(workspace), target=str(manifest_path),
                assignments=[], result="not a result line", dry_run=False,
            )
            rc = ws.cmd_lane_set(args)
            self.assertNotEqual(rc, 0)
            self.assertNotIn("result_status", json.loads(manifest_path.read_text()))


class CmdLaneCloseTest(unittest.TestCase):
    def test_close_without_result_only_sets_status_and_finished_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace.yaml"
            workspace.write_text(FIXTURE)
            manifest_path = root / "x.json"
            manifest_path.write_text(json.dumps({"session": "Demo", "status": "open"}))
            args = argparse.Namespace(
                workspace=str(workspace), target=str(manifest_path),
                result=None, dry_run=False,
            )
            rc = ws.cmd_lane_close(args)
            self.assertEqual(rc, 0)
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest["status"], "closed")
            self.assertIn("finished_at", manifest)
            self.assertNotIn("result_status", manifest)

    def test_close_with_result_sets_status_and_result_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace.yaml"
            workspace.write_text(FIXTURE)
            manifest_path = root / "x.json"
            manifest_path.write_text(json.dumps({"session": "Demo", "status": "open"}))
            args = argparse.Namespace(
                workspace=str(workspace), target=str(manifest_path),
                result="demo: BLOCKER none - docs/blocker.md", dry_run=False,
            )
            rc = ws.cmd_lane_close(args)
            self.assertEqual(rc, 0)
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest["status"], "closed")
            self.assertEqual(manifest["result_status"], "BLOCKER")
            self.assertEqual(manifest["result_sha"], "none")

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace.yaml"
            workspace.write_text(FIXTURE)
            manifest_path = root / "x.json"
            original = {"session": "Demo", "status": "open"}
            manifest_path.write_text(json.dumps(original))
            args = argparse.Namespace(
                workspace=str(workspace), target=str(manifest_path),
                result="demo: PASS abcdef1 - docs/x.md", dry_run=True,
            )
            rc = ws.cmd_lane_close(args)
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(manifest_path.read_text()), original)


class CmdLanesTest(unittest.TestCase):
    def test_filters_by_finished_since_and_includes_documented_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace.yaml"
            workspace.write_text(FIXTURE)
            lanes_dir = root / "runs" / ".lanes"
            lanes_dir.mkdir(parents=True)
            (lanes_dir / "old.json").write_text(json.dumps({
                "run_id": "old", "session": "Dotfiles", "window": "w0",
                "status": "closed", "finished_at": "2026-01-01T00:00:00Z",
            }))
            (lanes_dir / "new.json").write_text(json.dumps({
                "run_id": "new", "session": "Dotfiles", "window": "w1",
                "brief": "docs/brief.md", "status": "closed",
                "result": "demo: PASS abcdef1 - docs/out.md",
                "result_status": "PASS", "result_sha": "abcdef1",
                "result_path": "docs/out.md", "finished_at": "2026-06-01T00:00:00Z",
                "cost": "$0.42", "mailbox_record": "/tmp/mailbox/new.md",
            }))
            (lanes_dir / "open.json").write_text(json.dumps({
                "run_id": "open", "session": "Dotfiles", "window": "w2", "status": "open",
            }))
            doc = ws_yaml.load(FIXTURE)
            doc["areas"][0]["runs"] = str(root / "runs")
            with mock.patch.object(ws, "load_workspace", return_value=doc):
                args = argparse.Namespace(
                    workspace=str(workspace), finished_since="2026-03-01T00:00:00Z", json=True,
                )
                with mock.patch("builtins.print") as mock_print:
                    rc = ws.cmd_lanes(args)
            self.assertEqual(rc, 0)
            printed = mock_print.call_args[0][0]
            rows = json.loads(printed)
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["run_id"], "new")
            self.assertEqual(row["session"], "Dotfiles")
            self.assertEqual(row["window"], "w1")
            self.assertEqual(row["brief"], "docs/brief.md")
            self.assertEqual(row["result_status"], "PASS")
            self.assertEqual(row["result_sha"], "abcdef1")
            self.assertEqual(row["result_path"], "docs/out.md")
            self.assertEqual(row["cost"], "$0.42")
            self.assertEqual(row["mailbox_record"], "/tmp/mailbox/new.md")

    def test_no_matches_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace.yaml"
            workspace.write_text(FIXTURE)
            doc = ws_yaml.load(FIXTURE)
            doc["areas"][0]["runs"] = str(root / "runs")
            with mock.patch.object(ws, "load_workspace", return_value=doc):
                args = argparse.Namespace(
                    workspace=str(workspace), finished_since="2026-01-01T00:00:00Z", json=False,
                )
                rc = ws.cmd_lanes(args)
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
