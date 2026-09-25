---
name: web-research
description: Research a question on the open web the way Claude Code's web research works — search multiple engines, fetch and read the actual pages, then synthesize a cited answer. No API key required (uses a real Chrome TLS fingerprint that gets clean results from a datacentre IP). Use whenever the user asks you to look something up online, research a topic, gather docs/facts/current info, compare options, or verify a claim against sources.
---

# Web Research

Search the web and read the real pages behind the results, from this host, without an
API key. Two scripts, both run through the skill's own Python venv:

```bash
BASE=~/.pi/agent/skills/web-research
$BASE/.venv/bin/python $BASE/search.py "query" [-n N] [--json]
$BASE/.venv/bin/python $BASE/fetch.py  <url>    [--json] [--max N] [--raw]
```

Set `PY="$BASE/.venv/bin/python"` once, then call `$PY $BASE/search.py ...`.

## Why these scripts (don't use plain curl)

From this machine's IP, plain `curl`/`wget`/headless Chromium get CAPTCHA'd or served
JS-only shells by most search engines, and many content sites 403 a bare request. These
scripts send a genuine Chrome TLS/JA3 fingerprint (`curl_cffi`), which gets clean HTML
out of **Ecosia and Brave** and past most Cloudflare/anti-bot walls. Use them, not curl.

## The research loop

Do this iteratively — do not answer from a single search.

1. **Plan.** Break the question into 2-4 distinct sub-queries. Vary the wording; include
   specific nouns, error strings, versions, or dates.
2. **Search.** Run `search.py` for each sub-query. Results found by **both** engines
   (`agreement 2`) are the strongest leads.
3. **Read.** `fetch.py` the 3-6 most promising URLs to get the full page as Markdown —
   snippets alone are not evidence. Prefer **primary sources**: official docs, source
   repos, specs, standards, first-party blogs, original announcements. Treat SEO
   listicles and content farms with suspicion.
4. **Follow leads.** Fetch links a good page cites; re-search with better terms you
   learned. Stop when sources converge and new pages stop adding facts.
5. **Cross-check.** Confirm each material claim in at least two independent sources.
   Note disagreements and dates (is this current?).
6. **Synthesize.** Answer the actual question, then a **Sources** list: each claim
   traceable to the URL it came from. Flag anything you could not verify. Do not present
   a single unconfirmed page as settled fact.

## search.py

```bash
$PY $BASE/search.py "rust axum websocket example"          # 10 merged results
$PY $BASE/search.py "postgres logical replication limits" -n 20
$PY $BASE/search.py "query" --json                          # for scripting/piping
$PY $BASE/search.py "query" --engines brave                 # one engine only
```

Merges Ecosia + Brave, de-duplicates by URL, ranks by cross-engine agreement. Each
result has title, url, engines, agreement, and (usually) a snippet. Search-engine chrome
is filtered out. If `BRAVE_API_KEY` is set it is added as a third source automatically
(better recall + real snippets); it is not required.

## fetch.py

```bash
$PY $BASE/fetch.py https://example.com/article              # readable Markdown + title/author/date
$PY $BASE/fetch.py https://example.com/article --max 6000   # cap long pages
$PY $BASE/fetch.py https://example.com/article --json       # {title,author,date,sitename,content}
$PY $BASE/fetch.py https://example.com/page --raw           # raw HTML when extraction misses
```

Strips nav/ads/boilerplate with `trafilatura` and emits clean Markdown (links + tables
kept), with the title, site, author and publish date when available. If extraction is
empty (heavy-JS SPA, paywall), try `--raw`, or use the `website-screenshot` skill to see
what actually renders.

## Tips

- Quote multi-word queries. Add a year (e.g. `2024`) for anything time-sensitive.
- Non-English topics: search in the local language — recall is far higher.
- If both engines return little, rephrase rather than retrying the same words.
- Be reasonably polite; don't hammer one domain with dozens of rapid fetches.
- For deep multi-hour research you want to keep, write findings to a Markdown file in the
  repo (see the `research` skill's convention).

## Setup (already done; only if the venv is missing)

```bash
cd ~/.pi/agent/skills/web-research
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python curl_cffi trafilatura
```
