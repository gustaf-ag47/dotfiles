"""Multi-engine search for TCG (or any) online stores, with validation.

Most search engines CAPTCHA plain curl/headless-Chromium from datacentre IPs. Sending a
real Chrome TLS fingerprint via curl_cffi gets through on several of them. Results from
each engine are merged; a domain found by more engines is more likely to be a real shop.
"""

import argparse
import json
import re
import sys
import time
from urllib.parse import quote_plus

try:
    from curl_cffi import requests as cr
except ImportError:  # pragma: no cover
    sys.exit("needs curl_cffi: pip install curl_cffi  (or run inside the scraper repo's uv env)")

IMPERSONATE = "chrome131"

# Verified working from a datacentre IP with a Chrome fingerprint.
ENGINES = {
    "ecosia": "https://www.ecosia.org/search?q={q}",
    "brave": "https://search.brave.com/search?q={q}",
}

# Known blocked / JS-only from datacentre IPs - documented so nobody retries them:
#   google (JS-only shell), bing, duckduckgo (html+lite), startpage, yandex,
#   mojeek, yep, searx.be. Qwant/Marginalia/disroot respond but return junk.

SKIP_DOMAINS = {
    "google.com", "youtube.com", "facebook.com", "instagram.com", "tiktok.com",
    "linkedin.com", "reddit.com", "twitter.com", "x.com", "pinterest.com",
    "wikipedia.org", "amazon.com", "amazon.de", "amazon.co.uk", "ebay.com",
    "cardmarket.com", "tcgplayer.com", "pokemon.com", "trustpilot.com",
    "ecosia.org", "brave.com", "qwant.com", "mojeek.com", "duckduckgo.com",
    "s3.amazonaws.com", "mapbox.com", "apple.com", "microsoft.com", "discord.com",
    "vinted.com", "vinted.ee", "vinted.fi", "etsy.com", "aliexpress.com",
    "wallapop.com", "olx.pl", "allegro.pl", "tori.fi", "blocket.se",
    # restock-alert / price-comparison services - competitors, not retailers
    "tcgradar.eu", "hintaopas.fi", "pricerunner.com", "prisjakt.nu", "idealo.de",
    "kelkoo.com", "hinnavaatlus.ee", "skroutz.gr", "ceneo.pl", "heureka.cz",
}

# Localised query templates. {kw} is replaced by the search keyword set.
COUNTRY_QUERIES = {
    "FI": ["pokemon tcg kauppa suomi", "pokemon booster box verkkokauppa",
           "keräilykortit verkkokauppa", "one piece card game kauppa suomi"],
    "SE": ["pokemon tcg butik sverige", "pokemon booster box köp online",
           "samlarkort webbutik", "one piece card game butik"],
    "NO": ["pokemon tcg butikk norge", "pokemon booster box nettbutikk"],
    "DK": ["pokemon tcg butik danmark", "pokemon booster box webshop"],
    "EE": ["pokemon kaardid pood eesti", "pokemon tcg eesti e-pood"],
    "LV": ["pokemon kartes veikals latvija", "pokemon tcg latvija"],
    "LT": ["pokemon kortos parduotuve lietuva", "pokemon tcg lietuva"],
    "PL": ["pokemon tcg sklep polska", "karty pokemon booster box sklep"],
    "CZ": ["pokemon tcg obchod česko", "pokemon karty booster box eshop"],
    "SK": ["pokemon tcg obchod slovensko", "pokemon karty eshop"],
    "HU": ["pokemon tcg bolt magyarország", "pokemon kártya webáruház"],
    "RO": ["pokemon tcg magazin romania", "carti pokemon booster box magazin"],
    "BG": ["pokemon tcg магазин българия", "покемон карти магазин"],
    "DE": ["pokemon tcg shop deutschland", "pokemon booster box kaufen online"],
    "NL": ["pokemon tcg winkel nederland", "pokemon booster box kopen webshop"],
    "BE": ["pokemon tcg winkel belgie", "pokemon booster box belgique"],
    "ES": ["tienda pokemon tcg españa", "comprar caja sobres pokemon online"],
    "PT": ["loja pokemon tcg portugal", "comprar booster box pokemon"],
    "IT": ["negozio pokemon tcg italia", "comprare booster box pokemon online"],
    "FR": ["boutique pokemon tcg france", "acheter display pokemon en ligne"],
    "GR": ["pokemon tcg καταστημα ελλαδα", "pokemon karta booster box"],
    "IE": ["pokemon tcg shop ireland", "pokemon booster box buy online ireland"],
    "AT": ["pokemon tcg shop österreich", "pokemon booster box kaufen"],
    "CH": ["pokemon tcg shop schweiz", "pokemon booster box kaufen schweiz"],
}

TCG_SIGNALS = (
    "pokemon", "pokémon", "booster", "elite trainer", "one piece", "tcg",
    "kortit", "kaardid", "kortos", "kartes", "karty", "samlarkort", "kártya",
)


def search_engine(name: str, query: str, timeout: int = 25) -> list[str]:
    tpl = ENGINES[name]
    try:
        resp = cr.get(tpl.format(q=quote_plus(query)), impersonate=IMPERSONATE, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        print(f"      {name}: failed ({type(e).__name__})", file=sys.stderr)
        return []
    if resp.status_code != 200:
        print(f"      {name}: HTTP {resp.status_code}", file=sys.stderr)
        return []
    hosts: list[str] = []
    for url in re.findall(r'href="(https?://[^"]+)', resp.text):
        m = re.match(r"https?://(?:www\.)?([a-z0-9.-]+\.[a-z]{2,6})", url)
        if not m:
            continue
        host = m.group(1)
        if host in SKIP_DOMAINS or any(host.endswith("." + s) for s in SKIP_DOMAINS):
            continue
        if host not in hosts:
            hosts.append(host)
    return hosts


def validate(host: str, signals: tuple[str, ...] = TCG_SIGNALS) -> dict | None:
    """Confirm the domain is live and looks like a real shop selling the product."""
    try:
        resp = cr.get(f"https://{host}", impersonate=IMPERSONATE, timeout=20, allow_redirects=True)
    except Exception:  # noqa: BLE001
        return None
    if resp.status_code >= 400:
        return None
    body = resp.text.lower()
    hits = [s for s in signals if s in body]
    if len(hits) < 2:
        return None
    platform, currency = "unknown", None
    try:
        meta = cr.get(f"https://{host}/meta.json", impersonate=IMPERSONATE, timeout=12)
        if meta.status_code == 200 and '"currency"' in meta.text:
            platform, currency = "shopify", meta.json().get("currency")
    except Exception:  # noqa: BLE001
        pass
    if platform == "unknown":
        try:
            woo = cr.get(f"https://{host}/wp-json/wc/store/products?per_page=1",
                         impersonate=IMPERSONATE, timeout=12)
            if woo.status_code == 200 and woo.text.strip().startswith("["):
                platform = "woocommerce"
        except Exception:  # noqa: BLE001
            pass
    return {"host": host, "platform": platform, "currency": currency, "signals": hits[:5]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("countries", nargs="*", help="ISO codes, e.g. FI EE LV. Omit to list options.")
    ap.add_argument("--query", action="append", default=[], help="extra raw query (repeatable)")
    ap.add_argument("--engines", default=",".join(ENGINES), help="comma list: " + ",".join(ENGINES))
    ap.add_argument("--no-validate", action="store_true", help="skip liveness/product validation")
    ap.add_argument("--delay", type=float, default=3.0)
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args()

    if not args.countries and not args.query:
        print("countries with localised queries:", " ".join(sorted(COUNTRY_QUERIES)))
        return 0

    engines = [e.strip() for e in args.engines.split(",") if e.strip() in ENGINES]
    queries: list[tuple[str, str]] = []
    for c in args.countries:
        for q in COUNTRY_QUERIES.get(c.upper(), []):
            queries.append((c.upper(), q))
    queries.extend(("--", q) for q in args.query)

    found: dict[str, dict] = {}
    for country, q in queries:
        print(f"  [{country}] {q}", file=sys.stderr)
        for eng in engines:
            for host in search_engine(eng, q):
                entry = found.setdefault(host, {"country": country, "engines": set()})
                entry["engines"].add(eng)
            time.sleep(args.delay)

    print(f"\n{len(found)} candidate domains from {len(queries)} queries x {len(engines)} engines",
          file=sys.stderr)

    results = []
    for host, meta in sorted(found.items(), key=lambda kv: -len(kv[1]["engines"])):
        record = {"host": host, "country": meta["country"],
                  "engines": sorted(meta["engines"]), "agreement": len(meta["engines"])}
        if not args.no_validate:
            v = validate(host)
            if not v:
                continue
            record.update({k: v[k] for k in ("platform", "currency", "signals")})
        results.append(record)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print(f"\n{'domain':36}{'cc':4}{'agree':6}{'platform':13}{'cur':5}signals")
        for r in results:
            print(f"{r['host']:36}{r['country']:4}{r['agreement']:^6}"
                  f"{r.get('platform',''):13}{r.get('currency') or '':5}"
                  f"{','.join(r.get('signals', [])[:3])}")
        print(f"\n{len(results)} validated stores")
    return 0


if __name__ == "__main__":
    sys.exit(main())
