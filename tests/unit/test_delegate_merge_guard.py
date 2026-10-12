"""Only an explicit current-PR merge hold blocks; safety prose is not a hold."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MERGE = ROOT / "config/pi/skills/delegate/scripts/merge-pr.sh"


class MergeGuardTests(unittest.TestCase):
    def run_guard(self, brief):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brief.md").write_text(brief)
            fake = root / "gh"
            payload = json.dumps({"state": "OPEN", "author": {"login": "fixture"},
                                  "headRefOid": "a" * 40, "commits": [{"authors": [{"login": "fixture"}]}]})
            fake.write_text(f"#!/bin/bash\ncase \"$1\" in api) echo fixture ;; pr) printf '%s\\n' '{payload}' ;; *) exit 99 ;; esac\n")
            fake.chmod(0o755)
            return subprocess.run([str(MERGE), "73", "--brief", str(root / "brief.md"), "--dry-run"],
                                  env=os.environ | {"PATH": f"{root}:{os.environ['PATH']}"}, capture_output=True, text=True)

    def test_conditional_red_base_safety_is_not_a_merge_hold(self):
        for text in [
            "A red base branch is a blocker: do not merge onto it silently.",
            "Do not merge onto a red base branch.",
            "Do not merge if required checks fail.",
            "Do not merge this PR until required CI is green.",
            "Use --no-merge when doing a dry run.",
            "The old brief said don't merge, but the hold is released.",
        ]:
            with self.subTest(text=text):
                result = self.run_guard(text)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_standalone_current_pr_holds_block(self):
        for text in ["Do not merge.", "- **Merge:** no-merge", "Don't merge this PR.",
                     "Do not merge PR #73.", "Merge: do not merge: coordinator owns the merge.",
                     "- Do not merge this pull request — parent merges it."]:
            with self.subTest(text=text):
                self.assertEqual(self.run_guard(text).returncode, 2)

    def test_other_pr_and_quoted_examples_do_not_block(self):
        for text in ["Do not merge PR #74.", "```\nDo not merge.\n```", "> Do not merge."]:
            with self.subTest(text=text):
                result = self.run_guard(text)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
