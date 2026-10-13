"""Docs live in operator notes ($NOTES/Homelab/dotfiles/), not in this repo.

Only the root README, CLAUDE.md and Markdown that tools load at runtime (pi
skills/prompts, the Hermes persona) may be tracked. Repo links must resolve.
"""

import re
import subprocess
import unittest
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL_LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
ALLOWED_MD = (
    "README.md",
    "CLAUDE.md",
    "config/pi/APPEND_SYSTEM.md",
    "config/pi/skills/*/SKILL.md",
    "config/pi/skills/*/references/*.md",
    "config/hermes/SOUL.md",
)


def tracked_markdown():
    out = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line]


class DocumentationPolicyTest(unittest.TestCase):
    def test_no_narrative_docs_in_repo(self):
        stray = [f for f in tracked_markdown() if not any(fnmatch(f, pat) for pat in ALLOWED_MD)]
        self.assertEqual(stray, [], "move docs to $NOTES/Homelab/dotfiles/ (see CLAUDE.md)")

    def test_readme_links_resolve(self):
        doc = ROOT / "README.md"
        for target in LOCAL_LINK.findall(doc.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            # `$NOTES/...` never resolves as a link target: write it as a code path.
            self.assertFalse(target.startswith("`") or "$" in target, f"unresolvable link {target}")
            self.assertTrue((ROOT / target.split("#", 1)[0]).exists(), target)


if __name__ == "__main__":
    unittest.main()
