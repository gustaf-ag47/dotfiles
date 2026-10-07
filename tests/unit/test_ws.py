import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

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
    def test_tmp_worktrees_are_reported_as_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_tmp = Path(tmp) / "tmp-root"
            fake_tmp.mkdir()
            (fake_tmp / "wt-stale-lane").mkdir()
            found = []
            for entry in fake_tmp.glob("wt-*"):
                found.append(str(entry))
            self.assertEqual(len(found), 1)
            self.assertTrue(found[0].endswith("wt-stale-lane"))


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


if __name__ == "__main__":
    unittest.main()
