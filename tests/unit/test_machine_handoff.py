import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "config" / "pi" / "skills" / "machine-handoff"
MACHINES = SKILL_DIR / "scripts" / "machines.sh"
INVENTORY = SKILL_DIR / "scripts" / "inventory.sh"

FIXTURE_CONF = """\
# comment
[boxa]
user=alice
ssh=alice@boxa
sync_root=/home/alice/sync
src_root=/home/alice/sync/src
handover_dir=/home/alice/.hermes/handovers
hermes=hermes

[boxb]
user=bob
ssh=bob@boxb
src_root=/data/sync/src  # trailing comment
"""

FAKE_TMUX = """#!/usr/bin/env bash
case "$1" in
list-panes) cat "$FAKE_TMUX_DIR/panes.tsv" ;;
capture-pane)
  while [ $# -gt 0 ]; do
    case "$1" in -t) t="$2"; shift 2 ;; *) shift ;; esac
  done
  cat "$FAKE_TMUX_DIR/pane-${t#%}.txt"
  ;;
esac
"""

GIT_ENV = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}


def git(cwd, *args, **env):
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        env={"PATH": "/usr/bin:/bin", "HOME": str(cwd), **GIT_ENV, **env},
        check=True,
        capture_output=True,
    )


class MachinesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conf = Path(self.tmp.name) / "machines.conf"
        self.conf.write_text(FIXTURE_CONF)

    def tearDown(self):
        self.tmp.cleanup()

    def run_machines(self, *args, conf=None):
        return subprocess.run(
            ["bash", str(MACHINES), *args],
            env={
                "PATH": "/usr/bin:/bin",
                "MACHINE_HANDOFF_CONF": str(conf or self.conf),
            },
            capture_output=True,
            text=True,
        )

    def test_list_names_every_machine(self):
        result = self.run_machines("list")
        self.assertEqual(result.stdout.split(), ["boxa", "boxb"])

    def test_get_machine_prints_all_keys(self):
        result = self.run_machines("get", "boxa")
        self.assertIn("ssh=alice@boxa", result.stdout)
        self.assertIn("src_root=/home/alice/sync/src", result.stdout)
        self.assertNotIn("bob", result.stdout)

    def test_get_single_key_prints_value_only(self):
        result = self.run_machines("get", "boxb", "ssh")
        self.assertEqual(result.stdout.strip(), "bob@boxb")

    def test_trailing_comment_is_stripped_from_value(self):
        result = self.run_machines("get", "boxb", "src_root")
        self.assertEqual(result.stdout.strip(), "/data/sync/src")

    def test_unknown_machine_exits_4_and_lists_known(self):
        result = self.run_machines("get", "nosuch")
        self.assertEqual(result.returncode, 4)
        self.assertIn("boxa", result.stderr)

    def test_unknown_key_exits_5(self):
        result = self.run_machines("get", "boxb", "hermes")
        self.assertEqual(result.returncode, 5)

    def test_missing_config_exits_3(self):
        result = self.run_machines("list", conf=Path(self.tmp.name) / "nope")
        self.assertEqual(result.returncode, 3)

    def test_example_conf_parses_with_required_keys(self):
        example = SKILL_DIR / "machines.conf.example"
        for machine in ("laptop", "server"):
            result = self.run_machines("get", machine, conf=example)
            self.assertEqual(result.returncode, 0, result.stderr)
            for key in ("user", "ssh", "sync_root", "src_root", "handover_dir", "hermes"):
                self.assertIn(f"{key}=", result.stdout, f"{machine} missing {key}")

    def test_no_shipped_machines_conf_only_the_example(self):
        # The real registry is private and lives in the local overlay.
        self.assertFalse((SKILL_DIR / "machines.conf").exists())
        self.assertTrue((SKILL_DIR / "machines.conf.example").exists())


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = self.root / "sync" / "src"
        self.src.mkdir(parents=True)
        bindir = self.root / "bin"
        bindir.mkdir()
        self.fake_tmux_dir = self.root / "faketmux"
        self.fake_tmux_dir.mkdir()
        tmux = bindir / "tmux"
        tmux.write_text(FAKE_TMUX)
        tmux.chmod(tmux.stat().st_mode | stat.S_IEXEC)
        self.env = {
            "PATH": f"{bindir}:/usr/bin:/bin",
            "HOME": str(self.root),
            "FAKE_TMUX_DIR": str(self.fake_tmux_dir),
            **GIT_ENV,
        }

    def tearDown(self):
        self.tmp.cleanup()

    def make_repo(self, name, dirty=False, remote=False, commit_date=None):
        repo = self.src / name
        repo.mkdir()
        git(repo, "init", "-q")
        (repo / "f").write_text("v1\n")
        git(repo, "add", "f")
        env = {}
        if commit_date:
            env = {"GIT_AUTHOR_DATE": commit_date, "GIT_COMMITTER_DATE": commit_date}
        git(repo, "commit", "-q", "-m", "init", **env)
        if remote:
            bare = self.root / f"{name}.git"
            git(repo, "init", "-q", "--bare", str(bare))
            git(repo, "remote", "add", "origin", str(bare))
            git(repo, "push", "-q", "origin", "HEAD")
        if dirty:
            (repo / "f").write_text("v2\n")
        return repo

    def set_panes(self, panes):
        lines = []
        for pane_id, target, cmd, text in panes:
            lines.append(f"{pane_id}\t{target}\t{cmd}")
            (self.fake_tmux_dir / f"pane-{pane_id.lstrip('%')}.txt").write_text(text)
        (self.fake_tmux_dir / "panes.tsv").write_text("".join(f"{l}\n" for l in lines))

    def run_inventory(self, *args, **env):
        return subprocess.run(
            ["bash", str(INVENTORY), "--sync-root", str(self.src), *args],
            env={**self.env, **env},
            capture_output=True,
            text=True,
        )

    def rows(self, result, kind):
        return [
            line.split("\t")
            for line in result.stdout.splitlines()
            if line.startswith(kind + "\t")
        ]

    def test_dirty_unpushed_repo_is_reported_with_counts(self):
        self.make_repo("wip", dirty=True)
        result = self.run_inventory("--no-tmux")
        self.assertEqual(result.returncode, 0, result.stderr)
        (row,) = self.rows(result, "REPO")
        self.assertEqual(row[1], str(self.src / "wip"))
        self.assertIn("dirty=1", row)
        self.assertIn("unpushed=1", row)  # no remote: every commit is local-only
        self.assertEqual(row[-1], "current")

    def test_clean_pushed_repo_is_not_reported(self):
        self.make_repo("done", remote=True)
        result = self.run_inventory("--no-tmux")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows(result, "REPO"), [])

    def test_old_last_commit_classifies_stale(self):
        self.make_repo("old", dirty=True, commit_date="2023-01-01T00:00:00 +0000")
        result = self.run_inventory("--no-tmux")
        (row,) = self.rows(result, "REPO")
        self.assertEqual(row[-1], "stale")

    def test_stash_alone_makes_a_repo_interesting(self):
        repo = self.make_repo("stashed", remote=True)
        (repo / "f").write_text("stash me\n")
        git(repo, "stash")
        result = self.run_inventory("--no-tmux")
        (row,) = self.rows(result, "REPO")
        self.assertIn("stashes=1", row)

    def test_linked_worktree_outside_sync_root_is_reported(self):
        repo = self.make_repo("main", remote=True)
        wt = self.root / "worktrees" / "lane"
        git(repo, "worktree", "add", "-q", str(wt), "-b", "lane")
        (wt / "g").write_text("wip\n")
        result = self.run_inventory("--no-tmux")
        (row,) = self.rows(result, "WORKTREE")
        self.assertEqual(row[1], str(self.src / "main"))
        self.assertEqual(row[2], str(wt))
        self.assertEqual(row[3], "lane")
        self.assertIn("dirty=1", row)

    def test_linked_worktree_found_first_is_attributed_to_its_main_repo(self):
        # "aaa-lane" sorts before "mainrepo", so find discovers the linked
        # worktree first; it must not claim the main repo or its siblings.
        repo = self.make_repo("mainrepo", dirty=True)
        git(repo, "worktree", "add", "-q", str(self.src / "aaa-lane"), "-b", "lane")
        result = self.run_inventory("--no-tmux")
        self.assertEqual(result.returncode, 0, result.stderr)
        (repo_row,) = self.rows(result, "REPO")
        self.assertEqual(repo_row[1], str(repo))
        (wt_row,) = self.rows(result, "WORKTREE")
        self.assertEqual(wt_row[1], str(repo))
        self.assertEqual(wt_row[2], str(self.src / "aaa-lane"))

    def test_agent_panes_classified_and_own_pane_skipped(self):
        self.set_panes(
            [
                ("%0", "ho:handoff.1", "pi", "Working hard"),
                ("%1", "wk:lane-a.1", "pi", "doing things\nWorking..."),
                ("%2", "wk:lane-b.1", "hermes", "crashed\nResume this session with id 123"),
                ("%3", "wk:lane-c.1", "pi", "Should I use option (a) or (b)?"),
                ("%4", "wk:lane-d.1", "pi", "all done, result pushed"),
                ("%5", "wk:shell.1", "zsh", "$"),
            ]
        )
        result = self.run_inventory(TMUX_PANE="%0")
        self.assertEqual(result.returncode, 0, result.stderr)
        states = {row[1]: row[3] for row in self.rows(result, "PANE")}
        self.assertEqual(
            states,
            {
                "wk:lane-a.1": "active",
                "wk:lane-b.1": "dead",
                "wk:lane-c.1": "waiting",
                "wk:lane-d.1": "idle",
            },
        )

    def test_no_tmux_suppresses_pane_rows(self):
        self.set_panes([("%1", "wk:lane-a.1", "pi", "Working...")])
        result = self.run_inventory("--no-tmux")
        self.assertEqual(self.rows(result, "PANE"), [])

    def test_summary_counts_on_stderr(self):
        self.make_repo("wip", dirty=True)
        self.set_panes([("%1", "wk:lane-a.1", "pi", "Working...")])
        result = self.run_inventory()
        self.assertIn("active=1", result.stderr)
        self.assertIn("repos with WIP=1", result.stderr)


if __name__ == "__main__":
    unittest.main()
