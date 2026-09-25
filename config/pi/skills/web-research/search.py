#!/usr/bin/env python3
"""Web search from a datacentre IP without an API key.

Plain curl / headless Chromium get CAPTCHA'd by most engines from flagged IPs.
Sending a real Chrome TLS fingerprint via curl_cffi gets clean HTML out of
Ecosia and Brave. Results from both engines are merged and de-duplicated; a URL
returned by both is a stronger signal.

If BRAVE_API_KEY is set, the official Brave API is used as a third source
(better recall + real snippets).

Usage:
    search.py "query"                 # merged results (default 10)
    search.py "query" -n 20           # more results
    search.py "query" --json          # JSON out
    search.py "query" --engines ecosia,brave
"""
import argparse
import html
import json
import os
import re
import sys
from urllib.parse import quote_plus, urlparse, parse_qs, unquote

try:
    from curl_cffi import requests as cr
except ImportError:
    sys.exit("needs curl_cffi. Run via the skill's venv: "
             "~/.pi/agent/skills/web-research/.venv/bin/python search.py ...")

IMPERSONATE = "chrome131"

# Non-content hosts to drop from result lists (search infra, trackers).
JUNK_HOSTS = {
    "ecosia.org", "brave.com", "google.com", "bing.com", "duckduckgo.com",
    "gstatic.com", "googleapis.com", "cloudflare.com", "w3.org", "schema.org",
}


def _clean(u: str) -> str | None:
    """Return a normalised http(s) URL or None if it is search-engine chrome."""
    if u.startswith("//"):
        u = "https:" + u
    m = re.match(r"https?://([^/]+)", u)
    if not m:
        return None
    host = m.group(1).lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    if host in JUNK_HOSTS or any(host.endswith("." + j) for j in JUNK_HOSTS):
        return None
    return u


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def search_brave_html(query: str, timeout: int = 25) -> list[dict]:
    url = f"https://search.brave.com/search?q={quote_plus(query)}"
    r = cr.get(url, impersonate=IMPERSONATE, timeout=timeout)
    if r.status_code != 200:
        print(f"  brave: HTTP {r.status_code}", file=sys.stderr)
        return []
    out, seen = [], set()
    for block in re.split(r'data-type="web"', r.text)[1:]:
        hm = re.search(r'<a[^>]+href="(https?://[^"]+)"', block)
        tm = re.search(r'class="title search-snippet-title[^"]*"[^>]*>(.*?)</div>', block, re.S)
        if not hm or not tm:
            continue
        cu = _clean(hm.group(1))
        if not cu or cu in seen:
            continue
        title = _text(tm.group(1))
        if len(title) < 3:
            continue
        sm = re.search(r'class="content [^"]*"[^>]*>(.*?)</div>', block, re.S)
        snippet = _text(sm.group(1)) if sm else ""
        seen.add(cu)
        out.append({"title": title, "url": cu, "snippet": snippet, "engine": "brave"})
    return out


def search_ecosia(query: str, timeout: int = 25) -> list[dict]:
    url = f"https://www.ecosia.org/search?q={quote_plus(query)}"
    r = cr.get(url, impersonate=IMPERSONATE, timeout=timeout)
    if r.status_code != 200:
        print(f"  ecosia: HTTP {r.status_code}", file=sys.stderr)
        return []
    out, seen = [], set()
    for block in re.split(r'class="result web-result', r.text)[1:]:
        hm = re.search(r'<a[^>]+href="(https?://[^"]+)"', block)
        tm = re.search(r'class="result__title[^"]*"[^>]*>(.*?)</a>', block, re.S) \
            or re.search(r'class="result-title__heading[^"]*"[^>]*>(.*?)</', block, re.S)
        if not hm:
            continue
        cu = _clean(hm.group(1))
        if not cu or cu in seen:
            continue
        title = _text(tm.group(1)) if tm else ""
        if len(title) < 3:
            continue
        sm = re.search(r'class="result__description[^"]*"[^>]*>(.*?)</', block, re.S)
        snippet = _text(sm.group(1)) if sm else ""
        seen.add(cu)
        out.append({"title": title, "url": cu, "snippet": snippet, "engine": "ecosia"})
    return out


def search_brave_api(query: str, count: int = 20, timeout: int = 25) -> list[dict]:
    key = os.environ.get("BRAVE_API_KEY")
    if not key:
        return []
    r = cr.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": min(count, 20)},
        headers={"X-Subscription-Token": key, "Accept": "application/json"},
        timeout=timeout,
    )
    if r.status_code != 200:
        print(f"  brave-api: HTTP {r.status_code}", file=sys.stderr)
        return []
    out = []
    for item in r.json().get("web", {}).get("results", []):
        out.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": re.sub(r"<[^>]+>", "", item.get("description", "")),
            "engine": "brave-api",
        })
    return out


ENGINES = {
    "ecosia": search_ecosia,
    "brave": search_brave_html,
    "brave-api": search_brave_api,
}


def merge(results: list[list[dict]]) -> list[dict]:
    by_url: dict[str, dict] = {}
    for group in results:
        for item in group:
            key = item["url"].rstrip("/")
            if key in by_url:
                by_url[key]["engines"].add(item["engine"])
                if not by_url[key]["snippet"] and item["snippet"]:
                    by_url[key]["snippet"] = item["snippet"]
            else:
                by_url[key] = {**item, "engines": {item["engine"]}}
    merged = list(by_url.values())
    # More engines agreeing = higher rank; preserve first-seen order otherwise.
    merged.sort(key=lambda x: -len(x["engines"]))
    for m in merged:
        m["agreement"] = len(m["engines"])
        m["engines"] = sorted(m["engines"])
        m.pop("engine", None)
    return merged


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query")
    ap.add_argument("-n", type=int, default=10, help="max results (default 10)")
    ap.add_argument("--engines", default="", help="comma list; default = all available")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    chosen = [e.strip() for e in args.engines.split(",") if e.strip()] if args.engines else None
    if chosen is None:
        chosen = ["ecosia", "brave"]
        if os.environ.get("BRAVE_API_KEY"):
            chosen.append("brave-api")

    groups = []
    for name in chosen:
        fn = ENGINES.get(name)
        if not fn:
            print(f"  unknown engine: {name}", file=sys.stderr)
            continue
        try:
            groups.append(fn(args.query))
        except Exception as e:  # noqa: BLE001
            print(f"  {name}: failed ({type(e).__name__}: {e})", file=sys.stderr)

    merged = merge(groups)[: args.n]

    if args.json:
        print(json.dumps(merged, indent=2, ensure_ascii=False))
        return 0

    if not merged:
        print("No results. Try different terms, or run fetch.py on a known URL.", file=sys.stderr)
        return 1
    for i, r in enumerate(merged, 1):
        print(f"--- Result {i} ---")
        print(f"Title: {r['title']}")
        print(f"Link: {r['url']}")
        print(f"Engines: {','.join(r['engines'])} (agreement {r['agreement']})")
        if r["snippet"]:
            print(f"Snippet: {r['snippet']}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
