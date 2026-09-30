#!/usr/bin/env python3
"""Read-only monitor for official OpenAI and Anthropic public news surfaces."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import tempfile
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urldefrag, urlparse

SCHEMA = "llm-news.v1"
MAX_AGE = 12 * 60 * 60
MAX_ITEMS = 100
SOURCES = {
    "openai-news": {"provider": "openai", "url": "https://openai.com/news/"},
    "openai-changelog": {"provider": "openai", "url": "https://platform.openai.com/docs/changelog"},
    "anthropic-news": {"provider": "anthropic", "url": "https://www.anthropic.com/news"},
    "anthropic-release-notes": {"provider": "anthropic", "url": "https://docs.anthropic.com/en/release-notes/api"},
}
CATEGORIES = ("quota", "billing", "model", "routing", "general")
KEYWORDS = {
    "quota": r"\b(rate limit|limit|usage|reset|credits?|overage|plan|capacity)\b",
    "billing": r"\b(price|pricing|billing|credit|wallet|auto[- ]?reload|refund|cost)\b",
    "model": r"\b(model|launch|released?|deprecat|retir|availability|available|preview|version)\b",
    "routing": r"\b(route|routing|endpoint|api|compatib|availability|available|deprecat|retir)\b",
}


def canonical_url(value: str) -> str:
    value = urldefrag(value)[0]
    parsed = urlparse(value)
    return parsed._replace(query="").geturl().rstrip("/") or value


def classify(title: str, text: str = "") -> str:
    haystack = f"{title} {text}".lower()
    matches = [(category, len(re.findall(pattern, haystack))) for category, pattern in KEYWORDS.items()]
    best, count = max(matches, key=lambda pair: pair[1])
    return best if count else "general"


def _date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        pass
    match = re.search(r"\b(20\d{2})[-/]([01]?\d)[-/]([0-3]?\d)\b", value)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return None


class PageParser(HTMLParser):
    """Deliberately conservative parser: links/headings only, no script execution."""
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.heading = None
        self.link = None
        self.time_value = None
        self.entries = []
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"h1", "h2", "h3", "h4"}:
            self.heading = tag
            self.buffer = []
        elif tag == "a" and attrs.get("href"):
            self.link = urljoin(self.base_url, attrs["href"])
            self.buffer = []
        elif tag == "time":
            self.time_value = attrs.get("datetime")

    def handle_data(self, data):
        if self.heading or self.link:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "time":
            if self.time_value and self.entries:
                title, link, _published = self.entries[-1]
                self.entries[-1] = (title, link, self.time_value)
            self.time_value = None
        if self.heading == tag:
            title = " ".join("".join(self.buffer).split())
            if title and len(title) > 2:
                self.entries.append((title, self.link, self.time_value))
            self.heading = None
            self.buffer = []
        elif tag == "a" and self.link:
            title = " ".join("".join(self.buffer).split())
            if title and len(title) > 2:
                self.entries.append((title, self.link, self.time_value))
            self.link = None
            self.buffer = []


def parse_html(body: str, source: dict) -> list[dict]:
    parser = PageParser(source["url"])
    parser.feed(body)
    result = []
    seen = set()
    for title, link, published in parser.entries:
        link = canonical_url(link or source["url"])
        # Navigation labels and the page's own heading are not news items.
        if link == canonical_url(source["url"]) or len(title) < 8:
            continue
        key = (link, title.lower())
        if key in seen:
            continue
        seen.add(key)
        published = _date(published)
        content_hash = hashlib.sha256(f"{title}\n{published or ''}\n{link}".encode()).hexdigest()
        result.append({"provider": source["provider"], "source": source.get("name"),
                       "url": link, "title": html.unescape(title), "date": published,
                       "category": classify(title), "content_hash": content_hash})
    return result


def deduplicate(items: list[dict]) -> list[dict]:
    result, seen = [], set()
    for item in items:
        key = (item.get("provider"), item.get("url"), item.get("title", "").casefold(), item.get("date"), item.get("content_hash"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return sorted(result, key=lambda item: (item.get("date") or "", item.get("title", "").casefold()), reverse=True)


def _cache_path() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "llm-usage" / "news.json"


def _freshness(fetched_at: int, status: str = "ok", now: int | None = None) -> dict:
    age = max(0, (int(time.time()) if now is None else now) - int(fetched_at))
    if status != "ok":
        state = "unavailable"
    else:
        state = "fresh" if age < MAX_AGE else "stale"
    return {"status": state, "age_seconds": age}


def fetch(source: dict, opener=urlopen, cached=None) -> dict:
    headers = {"User-Agent": "llm-news/1.0 (read-only; official sources)"}
    if cached:
        if cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]
        if cached.get("last_modified"):
            headers["If-Modified-Since"] = cached["last_modified"]
    request = Request(source["url"], headers=headers)
    now = int(time.time())
    try:
        with opener(request, timeout=20) as response:
            status = getattr(response, "status", 200)
            if status == 304 and cached:
                result = {**cached, "status": "ok", "http_status": 304, "fetched_at": now,
                          "not_modified": True}
                result["freshness"] = _freshness(now)
                return result
            body = response.read().decode("utf-8", "replace")
            items = parse_html(body, source)
            if not items:
                raise ValueError("parser found no news items")
            result = {"status": "ok", "http_status": status, "items": items, "fetched_at": now}
            headers = getattr(response, "headers", {})
            if headers.get("ETag"):
                result["etag"] = headers["ETag"]
            if headers.get("Last-Modified"):
                result["last_modified"] = headers["Last-Modified"]
            result["freshness"] = _freshness(now)
            return result
    except HTTPError as exc:
        if exc.code == 304 and cached:
            result = {**cached, "status": "ok", "http_status": 304, "fetched_at": now,
                      "not_modified": True}
            result["freshness"] = _freshness(now)
            return result
        return {"status": "unavailable", "http_status": exc.code, "error": f"HTTP {exc.code}",
                "items": [], "fetched_at": now, "freshness": _freshness(now, "unavailable")}
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}", "items": [],
                "fetched_at": now, "freshness": _freshness(now, "unavailable")}


def collect(refresh=False, provider=None, opener=urlopen, cache_path=None) -> dict:
    path = Path(cache_path or _cache_path())
    now = int(time.time())
    cached = None
    if path.exists():
        try:
            cached = json.loads(path.read_text())
            if (not refresh and cached.get("provider") == provider
                    and now - int(cached.get("fetched_at", 0)) < MAX_AGE):
                cached["cache"] = {"status": "fresh", "age_seconds": max(0, now - int(cached["fetched_at"]))}
                for source in cached.get("sources", {}).values():
                    source["freshness"] = _freshness(source.get("fetched_at", cached["fetched_at"]), source.get("status", "ok"), now)
                return cached
        except (OSError, ValueError, TypeError):
            cached = None
    sources = {}
    for name, definition in SOURCES.items():
        if provider and definition["provider"] != provider:
            continue
        source = {**definition, "name": name}
        sources[name] = fetch(source, opener, (cached or {}).get("sources", {}).get(name))
    items = deduplicate([item for result in sources.values() for item in result.get("items", [])])[:MAX_ITEMS]
    failed = bool(sources) and all(result.get("status") != "ok" for result in sources.values())
    if failed and cached and cached.get("provider") == provider and cached.get("items"):
        # Never turn a network outage into an apparently empty feed. Keep the
        # last good items while exposing the current per-source failures.
        items = cached["items"]
        cache_status = "stale"
    else:
        cache_status = "fresh" if items or sources else "empty"
    report = {"schema": SCHEMA, "provider": provider, "fetched_at": now, "sources": sources, "items": items,
              "cache": {"status": cache_status, "age_seconds": max(0, now - int(cached.get("fetched_at", now))) if cache_status == "stale" and cached else 0}}
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent)
        with os.fdopen(fd, "w") as stream:
            json.dump(report, stream)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except OSError:
        pass
    return report


def render(report: dict, since=None) -> str:
    lines = [f"official news (cache {report.get('cache', {}).get('status', 'unknown')})"]
    for item in report.get("items", []):
        if since and (item.get("date") or "") < since:
            continue
        lines.append(f"[{item['category']}] {item['provider']} {item['title']} ({item.get('date') or 'undated'})")
        lines.append(f"  {item['url']}")
    for name, source in report.get("sources", {}).items():
        if source.get("status") != "ok":
            lines.append(f"! {name}: {source.get('error', 'unavailable')}" + (f" (HTTP {source['http_status']})" if source.get('http_status') else ""))
    return "\n".join(lines)


def _since_items(items, since):
    if not since:
        return items
    return [item for item in items if (item.get("date") or "") >= since]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--provider", choices=("openai", "anthropic"))
    parser.add_argument("--since", help="Only show items on/after YYYY-MM-DD")
    args = parser.parse_args(argv)
    report = collect(args.refresh, args.provider)
    report["items"] = _since_items(report.get("items", []), args.since)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
