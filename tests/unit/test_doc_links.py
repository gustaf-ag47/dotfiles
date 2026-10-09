"""Keep entry-point Markdown links relative to the document containing them."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL_LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")


class DocumentationLinksTest(unittest.TestCase):
    def test_readme_links_resolve(self):
        for doc in (ROOT / "README.md", ROOT / "docs/README.md"):
            with self.subTest(doc=doc.relative_to(ROOT)):
                for target in LOCAL_LINK.findall(doc.read_text()):
                    if "://" in target or target.startswith("#"):
                        continue
                    path = target.split("#", 1)[0]
                    self.assertTrue((doc.parent / path).exists(), f"{doc}: {target}")


if __name__ == "__main__":
    unittest.main()
