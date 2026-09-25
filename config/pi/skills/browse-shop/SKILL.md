---
name: browse-shop
description: Drive a real Chromium session interactively to explore an e-commerce site, verify you can actually buy a product (add-to-cart), and dump the structure a scraper needs - product-card selectors, fields, stock signals, pagination, and the JSON/XHR endpoints the page really calls. Use when investigating a shop before writing a scraper, verifying a site is genuinely purchasable, or reverse-engineering a listing/product page.
---

# Browse & analyse a shop

A persistent, agent-driven browser. You look at the page, choose an element, click it, look
again - the session (cookies, JS state, current URL) survives between commands.

Run it inside the scraper repo's environment (it has Playwright installed):

```bash
cd /mnt/my_encrypted_nvme/sync/src/InStockachu/instockachu-scraper
B=~/.pi/agent/skills/browse-shop/browse.py
uv run python $B goto https://shop.example/ --session myshop
```

## Commands

| Command | What it does |
|---|---|
| `goto <url>` | Navigate; prints numbered interactive elements + visible text |
| `snapshot` | Re-print elements/text for the current page |
| `click <n\|text>` | Click by index **or by label substring** (safer) |
| `type <n\|text> <value>` | Fill an input |
| `scroll` | Scroll down (triggers lazy-loading / infinite scroll) |
| `back` | Browser back |
| `analyze` | **Dump scraper-relevant structure** (see below) |
| `buy <n\|text>` | Click the element **you** choose, then report an objective before/after state diff |

Always pass `--session <name>` to keep separate shops isolated. Add `--locale sv-SE`
(or `fi-FI`, `de-DE`…) to see the site as a local visitor. A screenshot of every step is
written to `/tmp/pi-browse-sessions/<session>/last.png` - read it to *see* the page.

## `analyze` output

Full JSON is written to `/tmp/pi-browse-sessions/<session>/analysis.json`; a summary prints.

- **card selector candidates** - repeated blocks containing a link and a price, ranked so
  product-ish class names beat generic layout classes (`col`, `row`, `wrapper`)
- **sample product cards** - title, price text, link, image, and any `data-*` attributes
  (often carry product id / stock / price in machine-readable form)
- **result count text** - e.g. `331 tuotetta`, `1 - 13 of 13`; tells you the expected total
  so you can verify your scraper's coverage
- **pagination links / controls** - detected `?page=N` style URLs and next-page buttons in
  many languages
- **stock signals** - in-stock / sold-out phrases found on the page (many languages) and
  whether an add-to-cart control exists
- **json-ld + og/product meta** - structured data usually containing `price`,
  `priceCurrency` and `availability`; the most reliable field source when present
- **api/xhr calls observed** - the JSON endpoints the page actually fetched. This is
  usually the best scrape target: prefer it over parsing HTML.

## Verifying a shop is genuinely purchasable

Screenshots prove a page renders; they do not prove you can buy. Do this:

```bash
uv run python $B goto https://shop.example/ --session s1
uv run python $B click 3  --session s1      # a Pokemon category link
uv run python $B analyze  --session s1      # listing structure + item count
uv run python $B click 12 --session s1      # an in-stock product
uv run python $B analyze  --session s1      # product fields + stock signals
uv run python $B buy      --session s1      # click add-to-cart
```

### How `buy` decides - it doesn't, you do

`buy` does **not** pattern-match button labels to decide anything. You pick the element;
it clicks and reports an objective, language-independent diff:

- `numbers_changed` - every counter-ish number in the DOM, before vs after. A real
  add-to-cart moves a cart badge (e.g. `0 -> 1`).
- `requests_triggered_by_click` - the network calls that click caused (a cart POST is
  strong evidence).
- `new_text_after_click` - text that appeared (confirmation toasts, "added to cart").
- `url_changed`.

Verified discrimination on a live shop: clicking *Lisää ostoskoriin* moved **6 counters**
`0 -> 1`; clicking the *Tuotekuvaus* (description) tab moved **0**. That works in any
language without a word list.

Judge from the diff. No counter movement, no cart request and no new text means the shop
is probably catalogue-only, B2B, login-required, or out of stock - reasons not to invest
in a scraper.

The `CART_HINTS`/`STOCK_HINTS` word lists in the script are **annotations only**
(`hint_matched`) - they never gate the decision, and are always incomplete by nature.

## Watch out for

- **Geo-priced currency.** A shop can render a different currency based on the visitor's
  IP. `korttistoppi.fi` (a Finnish shop) shows `kr` from a Swedish IP, not `€`. Always
  check `json-ld priceCurrency` / `og:price:currency` rather than trusting the symbol, and
  pin the currency explicitly in the scraper if the site allows it.
- **Prefer label targeting over indices.** Indices are recomputed every command, so they
  shift whenever the DOM changes - clicking `11` twice can hit two different elements.
  `click "Pokemon"` / `buy "ostoskoriin"` is stable across re-renders.
- **Be polite and read-only.** Add-to-cart is fine; never complete a checkout, create an
  account, or submit payment details.
- Lazy-loaded grids need `scroll` before `analyze` to see the full card set.
