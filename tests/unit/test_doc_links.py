"""Keep in-repo Markdown links resolvable relative to the document containing them."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL_LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
# Entry-point docs that live in the repo. Narrative docs live in operator notes
# ($NOTES/Homelab/dotfiles/); reference those as plain `code` paths, not links.
DOCS = ("README.md", "profiles/README.md", "system/README.md", "scripts/README.md", "tests/README.md")


class DocumentationLinksTest(unittest.TestCase):
    def test_entry_point_links_resolve(self):
        for name in DOCS:
            doc = ROOT / name
            with self.subTest(doc=name):
                self.assertTrue(doc.exists(), f"{name} listed but missing")
                for target in LOCAL_LINK.findall(doc.read_text()):
                    if "://" in target or target.startswith("#"):
                        continue
                    # A `$NOTES/...` link target never resolves (backticks and
                    # env vars are literal in a URL): write it as a code path.
                    self.assertFalse(target.startswith("`") or "$" in target,
                                     f"{name}: unresolvable link target {target}")
                    path = target.split("#", 1)[0]
                    self.assertTrue((doc.parent / path).exists(), f"{name}: {target}")


if __name__ == "__main__":
    unittest.main()
