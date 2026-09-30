import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

SPEC = importlib.util.spec_from_file_location("llm_news", Path(__file__).resolve().parents[2] / "scripts/llm_news.py")
news = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(news)

FIXTURE = """
<html><body>
  <nav><a href='/news/'>News</a></nav>
  <article><a href='/news/model-update'><h2>New model availability</h2></a><time datetime='2026-09-30T10:00:00Z'>Sep 30</time></article>
  <article><a href='/news/model-update'>New model availability</a></article>
  <article><a href='/news/limits'>Usage limits changed</a></article>
</body></html>
"""


class Response:
    status = 200

    def __init__(self, body):
        self.body = body.encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


class NewsTests(unittest.TestCase):
    def test_parser_deduplicates_links_and_classifies(self):
        source = {"name": "fixture", "provider": "openai", "url": "https://example.test/news/"}
        items = news.parse_html(FIXTURE, source)
        self.assertEqual(len(items), 2)
        self.assertEqual({item["category"] for item in items}, {"model", "quota"})
        self.assertTrue(all(item["content_hash"] for item in items))

    def test_http_failure_is_visible(self):
        def blocked(_request, timeout):
            raise HTTPError("https://example.test", 403, "blocked", {}, None)

        result = news.fetch({"name": "fixture", "provider": "openai", "url": "https://example.test"}, blocked)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["http_status"], 403)

    def test_failed_refresh_keeps_stale_items(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "news.json"
            old = {"schema": news.SCHEMA, "provider": None, "fetched_at": 1,
                   "items": [{"provider": "openai", "title": "Old", "url": "https://x/old"}]}
            path.write_text(json.dumps(old))

            def blocked(_request, timeout):
                raise HTTPError("https://example.test", 429, "slow down", {}, None)

            with patch.object(news, "SOURCES", {"fixture": {"provider": "openai", "url": "https://example.test"}}):
                result = news.collect(refresh=True, cache_path=path, opener=blocked)
            self.assertEqual(result["cache"]["status"], "stale")
            self.assertEqual(result["items"][0]["title"], "Old")
            self.assertEqual(result["sources"]["fixture"]["http_status"], 429)


if __name__ == "__main__":
    unittest.main()
