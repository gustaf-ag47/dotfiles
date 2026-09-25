---
name: tcg-store-search
description: Find online stores (TCG/Pokemon retailers or any e-commerce niche) across multiple search engines from a datacentre IP, with automatic validation of platform and currency. Use when discovering new shops to scrape, researching a national market, or when normal search/curl gets CAPTCHA'd. Handles the engine-blocking problem that defeats plain curl and headless Chromium.
---

# TCG / e-commerce store search

## The problem this solves

From a datacentre or heavily-scraping IP, **plain `curl` and headless Chromium get
CAPTCHA'd by nearly every search engine**, and Google serves a JavaScript-only shell with
no results in the HTML. A real browser does not help - it is the IP that is flagged.

**What works:** sending a genuine Chrome TLS fingerprint via `curl_cffi`. That is the same
impersonation trick used to scrape Cloudflare-protected shops, and it gets clean HTML
results out of Ecosia and Brave.

## Usage

```bash
# list countries that have localised queries built in
python ~/.pi/agent/skills/tcg-store-search/search_stores.py

# search one or more countries (localised queries are used automatically)
python ~/.pi/agent/skills/tcg-store-search/search_stores.py FI EE LV LT

# add your own queries, emit JSON
python ~/.pi/agent/skills/tcg-store-search/search_stores.py --query "one piece tcg shop ireland" --json

# faster sweep without liveness/product validation
python ~/.pi/agent/skills/tcg-store-search/search_stores.py PL --no-validate
```

Needs `curl_cffi`. If it is not on the system Python, run it inside the scraper repo's
environment:

```bash
cd /mnt/my_encrypted_nvme/sync/src/InStockachu/instockachu-scraper
uv run python ~/.pi/agent/skills/tcg-store-search/search_stores.py FI
```

## What it does

1. Runs several **localised** queries per country (Finnish, Estonian, Polish, Romanian…),
   because English queries miss most national shops.
2. Queries each working engine and **merges** the results. The `agreement` column shows how
   many engines returned a domain - higher agreement is a stronger signal it is a real shop.
3. Filters out social networks, marketplaces (Vinted, eBay, Allegro, Tori…), and price
   aggregators, which are not scrapeable retailers.
4. **Validates** each survivor: loads the homepage, requires at least two product signals
   (`pokemon`, `booster`, `kaardid`, `kortit`…), then fingerprints the platform via
   `/meta.json` (Shopify, also yields the shop's authoritative currency) and
   `/wp-json/wc/store/products` (WooCommerce).

## Engine status (verified from this host)

| Engine | Works | Notes |
|---|---|---|
| **Ecosia** | ✅ | clean HTML results |
| **Brave** | ✅ | good recall, finds shops Ecosia misses |
| Google | ❌ | 200 but JS-only shell, no results in HTML |
| Bing, DuckDuckGo (html+lite), Startpage, Yandex, Mojeek, Yep | ❌ | CAPTCHA |
| Qwant, Marginalia, searx instances | ⚠️ | respond, but results are junk for these queries |

Do not waste time retrying the blocked ones - use the two that work, or add an API key.

## Getting better recall

Use **more, more varied localised queries** rather than more engines. Vary the product
noun (booster box / display / elite trainer box / sealed), the shop noun (kauppa, veikals,
sklep, magazin, webshop), and add city names for physical stores.

If you have a `BRAVE_API_KEY` (free tier ~2000 queries/month), the official API gives
better coverage and pagination than scraping the HTML page:

```bash
curl -s -H "X-Subscription-Token: $BRAVE_API_KEY" -H "Accept: application/json" \
  "https://api.search.brave.com/res/v1/web/search?q=pokemon+tcg+kauppa&country=fi&count=20"
```

## Feeding results into the InStockachu catalogue

`instockachu-scraper/scripts/discover_shops.py` wraps the same technique and additionally
POSTs validated shops to the catalogue's `/api/sites`, where the build loop picks them up
and drives investigate → implement automatically:

```bash
cd /mnt/my_encrypted_nvme/sync/src/InStockachu/instockachu-scraper
uv run python scripts/discover_shops.py FI EE --token "$RALPH_TOKEN"
```

## Cautions

- Be polite: the script sleeps between queries (`--delay`, default 3s). Do not remove it.
- Validation only proves a shop mentions the products; it does **not** prove sealed stock,
  prices, or international shipping. Verify those before committing to build a scraper.
- Marketplaces and price-comparison sites are filtered out deliberately - they are not
  retailers and are not useful for stock monitoring.
