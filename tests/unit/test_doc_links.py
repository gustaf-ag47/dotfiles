"""Keep entry-point Markdown links relative to the document containing them."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL_LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")


class DocumentationLinksTest(unittest.TestCase):
    def test_readme_links_resolve(self):
        # docs/ moved to operator notes (220df33); check the entry points that
        # still live in the repo, and skip `$NOTES/...`-style note pointers --
        # they resolve on the operator's machine, not in a checkout.
        for doc in (ROOT / "README.md", ROOT / "docs/README.md"):
            if not doc.exists():
                continue
            with self.subTest(doc=doc.relative_to(ROOT)):
                for target in LOCAL_LINK.findall(doc.read_text()):
                    if "://" in target or target.startswith("#"):
                        continue
                    if target.startswith("`") or "$" in target:
                        continue
                    path = target.split("#", 1)[0]
                    self.assertTrue((doc.parent / path).exists(), f"{doc}: {target}")


if __name__ == "__main__":
    unittest.main()
