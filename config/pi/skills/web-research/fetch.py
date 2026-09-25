#!/usr/bin/env python3
"""Fetch a URL and extract its readable content as Markdown.

Uses a real Chrome TLS fingerprint (curl_cffi) so Cloudflare-protected and
datacentre-blocked pages still return content, then trafilatura to strip nav /
ads / boilerplate and emit clean Markdown with the title, author and date.

Usage:
    fetch.py https://example.com/article
    fetch.py https://example.com/article --json      # metadata + text as JSON
    fetch.py https://example.com/article --max 6000  # truncate to N chars
    fetch.py https://example.com/article --raw        # raw HTML, no extraction
"""
import argparse
import json
import sys

try:
    from curl_cffi import requests as cr
except ImportError:
    sys.exit("needs curl_cffi. Run via the skill's venv: "
             "~/.pi/agent/skills/web-research/.venv/bin/python fetch.py ...")

import trafilatura

IMPERSONATE = "chrome131"


def fetch_html(url: str, timeout: int = 30) -> tuple[int, str]:
    r = cr.get(url, impersonate=IMPERSONATE, timeout=timeout, allow_redirects=True)
    return r.status_code, r.text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--raw", action="store_true", help="print raw HTML, skip extraction")
    ap.add_argument("--max", type=int, default=0, help="truncate content to N chars (0 = no limit)")
    args = ap.parse_args()

    try:
        status, htmltext = fetch_html(args.url)
    except Exception as e:  # noqa: BLE001
        print(f"fetch failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    if status >= 400:
        print(f"HTTP {status} for {args.url}", file=sys.stderr)
        # still try to extract; some sites 403 the body but include content

    if args.raw:
        print(htmltext)
        return 0

    md = trafilatura.extract(
        htmltext, url=args.url, output_format="markdown",
        include_links=True, include_tables=True, with_metadata=False,
    )
    meta = trafilatura.extract_metadata(htmltext, default_url=args.url)

    if not md:
        print(f"No readable content extracted (HTTP {status}). "
              f"Try --raw to inspect the HTML.", file=sys.stderr)
        return 1

    if args.max and len(md) > args.max:
        md = md[: args.max] + f"\n\n[... truncated at {args.max} chars ...]"

    title = getattr(meta, "title", None) or ""
    author = getattr(meta, "author", None) or ""
    date = getattr(meta, "date", None) or ""
    sitename = getattr(meta, "sitename", None) or ""

    if args.json:
        print(json.dumps({
            "url": args.url, "status": status, "title": title,
            "author": author, "date": date, "sitename": sitename,
            "content": md,
        }, indent=2, ensure_ascii=False))
        return 0

    if title:
        print(f"# {title}\n")
    byline = " | ".join(x for x in (sitename, author, date) if x)
    if byline:
        print(f"_{byline}_\n")
    print(f"Source: {args.url}\n")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
