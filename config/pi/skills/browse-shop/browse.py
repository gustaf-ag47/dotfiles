"""Agent-driven interactive browser + shop structure analyser.

Keeps a real Chromium session alive between commands so an LLM can browse a shop like a
person: look, click, look again - and can then dump everything a scraper author needs
(product-card selectors, fields, stock signals, pagination, and the JSON/XHR endpoints the
page actually calls).

    browse.py goto https://shop.example/ --session s1
    browse.py click 3 --session s1            # a "Pokemon" category link
    browse.py analyze --session s1            # listing-page structure + API calls
    browse.py click 12 --session s1           # a product
    browse.py analyze --session s1            # product-page fields + stock
    browse.py buy --session s1                # prove it is purchasable
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from playwright.sync_api import sync_playwright

SESSIONS = Path("/tmp/pi-browse-sessions")
INTERACTIVE = "a, button, input[type=submit], input[type=button], [role=button], select"

CART_HINTS = [   # hints only - the agent decides, these just annotate

    r"add to (cart|basket|bag)", r"buy now", r"add to trolley",
    r"lägg i (varukorg|kundvagn)", r"köp nu", r"köp", r"handla",
    r"lisää (ostoskoriin|koriin)", r"osta",
    r"i kurv", r"læg i kurv", r"tilføj til kurv",
    r"in den warenkorb", r"kaufen",
    r"ajouter au panier", r"acheter",
    r"in winkelwagen", r"toevoegen",
    r"añadir al carrito", r"comprar",
    r"aggiungi al carrello",
    r"dodaj do koszyka", r"do koszyka",
    r"adaug[ăa] .n co[șs]", r"cump[ăa]r[ăa]",
    r"lisa ostukorvi", r"pievienot grozam", r"[įi] krep[šs]el[įi]",
]
STOCK_HINTS = [  # hints only - never used to decide, only to annotate

    r"sold out", r"out of stock", r"slutsåld", r"slut i lager", r"ei varastossa",
    r"loppu", r"udsolgt", r"ausverkauft", r"nicht verfügbar", r"rupture de stock",
    r"uitverkocht", r"agotado", r"esaurito", r"wyprzedane", r"stoc epuizat",
    r"otsas", r"nav pieejams", r"i[šs]parduota", r"tillfälligt slut", r"ennakkotilaus",
]
IN_STOCK_HINTS = [

    r"in stock", r"i lager", r"varastossa", r"på lager", r"auf lager", r"en stock",
    r"op voorraad", r"disponible", r"disponibile", r"dostępny", r"in stoc", r"laos",
]
PAGINATION_HINTS = [

    r"next", r"nästa", r"seuraava", r"næste", r"weiter", r"suivant", r"volgende",
    r"siguiente", r"successivo", r"następna", r"următor", r"järgmine", r"nākamā", r"kitas",
    r"»", r"›", r"load more", r"visa fler", r"näytä lisää", r"mehr laden",
]


def session_dir(name: str) -> Path:
    d = SESSIONS / re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    d.mkdir(parents=True, exist_ok=True)
    return d


def tag_elements(page, limit: int = 80) -> list[dict]:
    """Tag interactive elements with a stable attribute so clicks hit the right node."""
    js = """
    (sel) => {
      document.querySelectorAll('[data-pi-idx]').forEach(e => e.removeAttribute('data-pi-idx'));
      const out = []; let i = 0; const seen = new Set();
      document.querySelectorAll(sel).forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.width < 2 || r.height < 2) return;
        const st = getComputedStyle(el);
        if (st.visibility === 'hidden' || st.display === 'none') return;
        let label = (el.innerText || el.value || el.getAttribute('aria-label') || el.title || '').trim();
        label = label.replace(/\\s+/g, ' ').slice(0, 80);
        if (!label) return;
        const href = el.getAttribute('href') || '';
        const key = label + '|' + href;
        if (seen.has(key)) return;
        seen.add(key);
        el.setAttribute('data-pi-idx', String(i));
        out.push({idx: i, tag: el.tagName.toLowerCase(), label, href});
        i++;
      });
      return out;
    }"""
    try:
        return page.evaluate(js, INTERACTIVE)[:limit]
    except Exception:  # noqa: BLE001
        return []


def visible_text(page, limit: int = 2500) -> str:
    try:
        t = page.evaluate("() => document.body.innerText") or ""
    except Exception:  # noqa: BLE001
        return ""
    return re.sub(r"\n{3,}", "\n\n", t)[:limit]


def match_any(text: str, pats: list[str]) -> str | None:
    low = (text or "").lower()
    for p in pats:
        m = re.search(p, low)
        if m:
            return m.group(0)
    return None


def analyze_page(page, xhr: list[dict]) -> dict:
    """Extract everything a scraper author needs from the current page."""
    js = r"""
    () => {
      const res = {};

      // --- structured data ---
      res.jsonld = [];
      document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
        try { res.jsonld.push(JSON.parse(s.textContent)); } catch (e) {}
      });
      res.meta = {};
      document.querySelectorAll('meta[property^="product:"], meta[property^="og:"]').forEach(m => {
        res.meta[m.getAttribute('property')] = m.getAttribute('content');
      });

      // --- repeated card structures: find the class shared by most sibling blocks
      // that contain both a link and a price-looking string ---
      const priceRe = /(\d[\d\s.,]{1,12})\s*(kr|€|eur|\$|zł|kč|lei|£|huf|sek|dkk|nok)|(kr|€|\$|£)\s*\d/i;
      const counts = {};
      document.querySelectorAll('div,li,article,section').forEach(el => {
        if (!el.querySelector('a')) return;
        const t = el.innerText || '';
        if (t.length > 400 || !priceRe.test(t)) return;
        (el.className || '').split(/\s+/).filter(Boolean).forEach(c => {
          counts[c] = (counts[c] || 0) + 1;
        });
      });
      // Prefer classes whose name suggests a product card over generic layout classes
      // (bootstrap 'col', 'row', 'pt-3' etc. often tie on count but are useless selectors).
      const productish = /(product|item|card|artikel|tuote|vara|produkt|prekes)/i;
      const generic = /^(col|row|container|wrapper|grid|flex|inner|content|box)([-_]?\d+)?$/i;
      res.card_classes = Object.entries(counts)
        .filter(([c, n]) => n >= 3)
        .sort((a, b) => {
          const score = ([c, n]) => (productish.test(c) ? 1000 : 0) - (generic.test(c) ? 500 : 0) + n;
          return score(b) - score(a);
        }).slice(0, 8);

      // --- sample cards from the best candidate ---
      res.cards = [];
      if (res.card_classes.length) {
        const cls = res.card_classes[0][0];
        document.querySelectorAll('.' + CSS.escape(cls)).forEach(el => {
          if (res.cards.length >= 3) return;
          const a = el.querySelector('a');
          const img = el.querySelector('img');
          const txt = (el.innerText || '').replace(/\s+/g, ' ').trim();
          const pm = txt.match(priceRe);
          res.cards.push({
            selector: '.' + cls,
            link: a ? a.getAttribute('href') : null,
            title: (() => {
              const cand = [a && a.innerText, a && a.title, img && img.getAttribute('alt'),
                            el.querySelector('h1,h2,h3,h4,.title,.name,[class*=title],[class*=name]')?.innerText];
              const best = cand.filter(Boolean).map(t => t.replace(/\s+/g,' ').trim())
                               .sort((x, y) => y.length - x.length)[0];
              return best ? best.slice(0, 80) : null;
            })(),
            price_text: pm ? pm[0] : null,
            image: img ? (img.getAttribute('src') || img.getAttribute('data-src')) : null,
            text: txt.slice(0, 160),
            data_attrs: Object.fromEntries(
              [...el.attributes].filter(a => a.name.startsWith('data-')).map(a => [a.name, a.value.slice(0,40)])
            )
          });
        });
      }

      // --- pagination hints ---
      res.pagination_links = [];
      document.querySelectorAll('a[href]').forEach(a => {
        const h = a.getAttribute('href') || '';
        if (/[?&](page|p|sida|sivu|pagina|seite)=\d+/i.test(h) || /\/page\/\d+/i.test(h)) {
          const t = (a.innerText || '').trim().slice(0, 20);
          if (res.pagination_links.length < 8) res.pagination_links.push({text: t, href: h});
        }
      });
      const bodyText = document.body.innerText || '';
      const m = bodyText.match(/(\d+)\s*[-–]\s*(\d+)\s*(?:of|av|\/|z|din|iš|no)\s*(\d+)/i)
             || bodyText.match(/(\d+)\s*(?:products|produkter|tuotetta|produkte|producten|produse)/i);
      res.result_count_text = m ? m[0] : null;

      return res;
    }"""
    try:
        data = page.evaluate(js)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}

    body = visible_text(page, 6000)
    data["stock_signals"] = {
        "sold_out_phrase": match_any(body, STOCK_HINTS),
        "in_stock_phrase": match_any(body, IN_STOCK_HINTS),
        "add_to_cart_present": bool([e for e in tag_elements(page) if match_any(e["label"], CART_HINTS)]),
    }
    data["pagination_controls"] = [
        e for e in tag_elements(page) if match_any(e["label"], PAGINATION_HINTS)
    ][:6]
    data["api_calls_observed"] = xhr[:25]
    return data



def capture_state(page) -> dict:
    """Objective, language-independent page state for before/after comparison."""
    js = """
    () => {
      const nums = {};
      // any small integer rendered in an element whose id/class hints at a counter
      document.querySelectorAll('[class*=count],[class*=cart],[class*=basket],[id*=cart],[data-count]').forEach((el, i) => {
        const t = (el.innerText || el.getAttribute('data-count') || '').trim();
        const m = t.match(/^\\d{1,3}$/);
        if (m) nums[(el.className || el.id || 'el') + '#' + i] = parseInt(m[0], 10);
      });
      return {nums, storage: Object.keys(localStorage).length};
    }"""
    try:
        data = page.evaluate(js)
    except Exception:  # noqa: BLE001
        data = {"nums": {}, "storage": 0}
    text = visible_text(page, 8000)
    return {
        "url": page.url,
        "numbers": {**data.get("nums", {}), "_localStorage_keys": data.get("storage", 0)},
        "lines": [ln.strip() for ln in text.split("\n") if ln.strip()],
    }


def resolve_target(page, selector: str | None, els: list[dict]) -> dict | None:
    """Accept either a numeric index or a label substring.

    Indices are recomputed every command, so they shift whenever the DOM changes.
    Matching on label text is stable across re-renders and is the safer choice.
    """
    if selector is None or selector == "":
        return None
    if selector.lstrip("-").isdigit():
        return next((e for e in els if e["idx"] == int(selector)), None)
    needle = selector.lower()
    matches = [e for e in els if needle in e["label"].lower()]
    return matches[0] if matches else None

def run(args) -> int:
    sdir = session_dir(args.session)
    shot = sdir / "last.png"
    state_file = sdir / "state.json"
    xhr: list[dict] = []

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(sdir / "profile"),
            headless=not args.headed,
            viewport={"width": 1400, "height": 1000},
            locale=args.locale,
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"),
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            try:
                ct = (resp.headers or {}).get("content-type", "")
                if "json" in ct and resp.request.resource_type in ("xhr", "fetch"):
                    xhr.append({"method": resp.request.method,
                                "url": resp.url[:200], "status": resp.status})
            except Exception:  # noqa: BLE001
                pass

        page.on("response", on_response)

        if args.cmd != "goto" and state_file.exists():
            last = json.loads(state_file.read_text()).get("url")
            if last and page.url in ("about:blank", ""):
                page.goto(last, timeout=args.timeout * 1000, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)

        try:
            if args.cmd == "goto":
                page.goto(args.url, timeout=args.timeout * 1000, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
            elif args.cmd in ("click", "type"):
                els = tag_elements(page)
                target = resolve_target(page, args.arg, els)
                if target is None:
                    print(f"target {args.arg!r} not found - run snapshot again")
                    return 1
                loc = page.locator(f'[data-pi-idx="{target["idx"]}"]')
                if args.cmd == "click":
                    loc.first.click(timeout=15000)
                else:
                    loc.first.fill(args.text, timeout=15000)
                page.wait_for_timeout(3000)
            elif args.cmd == "back":
                page.go_back(timeout=args.timeout * 1000)
                page.wait_for_timeout(2000)
            elif args.cmd == "scroll":
                page.evaluate("() => window.scrollBy(0, window.innerHeight * 3)")
                page.wait_for_timeout(2500)
            elif args.cmd == "buy":
                # The AGENT chooses which element to click (pass its index). We do not
                # guess from labels - we click, then report an objective before/after
                # diff so the agent can judge whether a purchase actually started.
                els = tag_elements(page, limit=150)
                target = resolve_target(page, args.arg, els)
                if args.arg and target is None:
                    print(f"target {args.arg!r} not found - run snapshot first")
                    return 1
                if target is None:
                    hinted = [e for e in els if match_any(e["label"], CART_HINTS)]
                    if not hinted:
                        print(json.dumps({
                            "clicked": None,
                            "note": ("no element matched the cart-label hints. Pick one "
                                     "yourself from `snapshot` and run: buy <index>"),
                            "candidates": [{"idx": e["idx"], "label": e["label"]}
                                           for e in els if e["tag"] == "button"][:15],
                        }, indent=2, ensure_ascii=False))
                        return 0
                    target = hinted[0]

                before = capture_state(page)
                xhr_mark = len(xhr)
                page.locator(f'[data-pi-idx="{target["idx"]}"]').first.click(timeout=15000)
                page.wait_for_timeout(4500)
                after = capture_state(page)

                added = [ln for ln in after["lines"] if ln not in set(before["lines"])][:12]
                triggered = [c for c in xhr[xhr_mark:]][:10]
                print(json.dumps({
                    "clicked": {"idx": target["idx"], "label": target["label"],
                                "hint_matched": bool(match_any(target["label"], CART_HINTS))},
                    "url_changed": before["url"] != after["url"],
                    "url_before": before["url"], "url_after": after["url"],
                    "numbers_changed": {k: [before["numbers"].get(k), v]
                                        for k, v in after["numbers"].items()
                                        if before["numbers"].get(k) != v},
                    "requests_triggered_by_click": triggered,
                    "new_text_after_click": added,
                    "note": ("Judge for yourself: a real add-to-cart usually shows a "
                             "cart/basket counter increasing, a POST/GET to a cart endpoint, "
                             "or new confirmation text. None of those = probably not purchasable."),
                }, indent=2, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            print(f"ERROR: {type(e).__name__}: {str(e)[:200]}")

        if args.cmd == "analyze":
            page.wait_for_timeout(1500)
            data = analyze_page(page, xhr)
            out_file = sdir / "analysis.json"
            out_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            print(f"URL: {page.url}")
            print(f"FULL ANALYSIS: {out_file}")
            cards = data.get("cards") or []
            print(f"\ncard selector candidates: {data.get('card_classes')}")
            print(f"result count text     : {data.get('result_count_text')}")
            print(f"stock signals         : {json.dumps(data.get('stock_signals'), ensure_ascii=False)}")
            print(f"pagination links      : {json.dumps(data.get('pagination_links', [])[:4], ensure_ascii=False)}")
            print(f"pagination controls   : {[c['label'] for c in data.get('pagination_controls', [])]}")
            print(f"json-ld blocks        : {len(data.get('jsonld', []))}")
            print(f"og/product meta       : {json.dumps(data.get('meta', {}), ensure_ascii=False)[:300]}")
            print("\napi/xhr calls observed (scrape targets):")
            for a in data.get("api_calls_observed", [])[:10]:
                print(f"  {a['method']:5} {a['status']} {a['url'][:110]}")
            print("\nsample product cards:")
            for c in cards:
                print(f"  selector={c.get('selector')}")
                print(f"    title = {c.get('title')}")
                print(f"    price = {c.get('price_text')}")
                print(f"    link  = {c.get('link')}")
                if c.get("data_attrs"):
                    print(f"    data- = {json.dumps(c['data_attrs'], ensure_ascii=False)[:160]}")
        elif args.cmd in ("goto", "snapshot", "click", "type", "back", "scroll"):
            print(f"URL: {page.url}\nTITLE: {page.title()}\nSCREENSHOT: {shot}")
            print("\n--- INTERACTIVE ELEMENTS (use: click <n>) ---")
            for e in tag_elements(page):
                href = f"  -> {e['href'][:52]}" if e["href"] else ""
                print(f"  [{e['idx']:2}] {e['tag']:6} {e['label'][:58]}{href}")
            print("\n--- VISIBLE TEXT ---")
            print(visible_text(page))

        page.screenshot(path=str(shot))
        state_file.write_text(json.dumps({"url": page.url}))
        ctx.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["goto", "snapshot", "click", "type", "back", "scroll",
                                    "buy", "analyze"])
    ap.add_argument("arg", nargs="?", default=None)
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--session", default="default")
    ap.add_argument("--timeout", type=int, default=45)
    ap.add_argument("--locale", default="en-GB")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    args.url = args.arg if args.cmd == "goto" else None
    args.index = int(args.arg) if (args.arg or "").lstrip("-").isdigit() else -1
    if args.cmd == "goto" and not args.url:
        ap.error("goto needs a url")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
