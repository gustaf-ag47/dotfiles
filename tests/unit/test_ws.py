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


class PiSessionFileForCwdTest(unittest.TestCase):
    def test_picks_newest_jsonl_in_mapped_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_dir = root / "--home-example-src-widgetco--"
            session_dir.mkdir()
            old = session_dir / "old.jsonl"
            new = session_dir / "new.jsonl"
            old.write_text("{}")
            new.write_text("{}")
            os.utime(old, (1000, 1000))
            os.utime(new, (2000, 2000))
            found = ws.pi_session_file_for_cwd("/home/example/src/widgetco", sessions_root=root)
            self.assertEqual(found, str(new))

    def test_returns_none_when_no_session_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = ws.pi_session_file_for_cwd("/home/example/missing", sessions_root=Path(tmp))
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
                "pane_pid": "555",
                "command": "pi",
                "cwd": "/home/example/sync/src/dotfiles",
            }
            with mock.patch.object(ws, "tmux_agent_panes", return_value=[pane]), \
                 mock.patch.object(ws, "open_lanes", return_value=[]), \
                 mock.patch.object(ws, "runs_dir_for_session", return_value=str(lane_root)), \
                 mock.patch.object(ws, "find_pi_pid", return_value=None), \
                 mock.patch.object(ws, "git_branch_for", return_value="main"), \
                 mock.patch.object(ws, "pi_session_file_for_cwd", return_value=None):
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


if __name__ == "__main__":
    unittest.main()
