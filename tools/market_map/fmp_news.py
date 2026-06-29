#!/usr/bin/env python3
"""fmp_news.py — FMP Ultimate company NEWS + press-release connector (uses FMP_ULTIMATE_API_KEY).

The pipeline already pulls FMP company DATA (prices, fundamentals, estimates, profile, earnings) but NOT
news. This adds it: pulls recent headlines + press releases per symbol from FMP's /stable news endpoints,
normalizes them to {symbol, date, title, summary, site, url}, and feeds news_sentiment for the daily report's
headwind/tailwind read. Parser is pure + offline-tested via an injected fetcher; the network call is gated
to CI. Defensive across FMP's field-name variants. Research only."""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
STABLE = "https://financialmodelingprep.com/stable"


def _key():
    for k in ("FMP_ULTIMATE_API_KEY", "FMP_API_KEY", "FMP_UTIMATE_API_KEY"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return ""


def _pick(d, *names):
    for n in names:
        if isinstance(d, dict) and d.get(n) not in (None, ""):
            return d[n]
    return None


def parse_news(rows, want=None):
    """FMP news JSON (list of dicts) -> {SYM: [ {symbol,date,title,summary,site,url} ]}, newest first,
    deduped by (symbol,title). `want` optionally restricts to a set of uppercase tickers."""
    out = {}
    seen = set()
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        sym = str(_pick(r, "symbol", "ticker", "tickers") or "").split(",")[0].strip().upper()
        title = (_pick(r, "title", "headline") or "").strip()
        if not sym or not title:
            continue
        if want and sym not in want:
            continue
        key = (sym, title)
        if key in seen:
            continue
        seen.add(key)
        out.setdefault(sym, []).append({
            "symbol": sym,
            "date": str(_pick(r, "publishedDate", "date", "publishedAt") or "")[:10],
            "title": title,
            "summary": (_pick(r, "text", "summary", "content") or "")[:400],
            "site": _pick(r, "site", "publisher", "source") or "",
            "url": _pick(r, "url", "link") or "",
        })
    for sym in out:
        out[sym].sort(key=lambda x: x["date"], reverse=True)
    return out


def _real_get(url, timeout=30):
    import requests
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code, (r.json() if r.status_code == 200 else [])
    except Exception as e:
        sys.stderr.write("fmp_news: GET error %s\n" % str(e)[:120])
        return 0, []


def fetch(symbols, key=None, get=None, per_symbol_limit=15, batch=20):
    """Pull stock news + press releases for `symbols`. `get(url)->(status,json)` injectable for tests.
    Returns {SYM: [headlines]}. Tries the modern /stable endpoints with defensive fallbacks."""
    key = key if key is not None else _key()
    get = get or _real_get
    if not key or not symbols:
        return {}
    want = set(s.upper() for s in symbols)
    syms = [s.upper() for s in symbols]
    merged = {}
    for i in range(0, len(syms), batch):
        chunk = ",".join(syms[i:i + batch])
        for ep in ("news/stock", "news/press-releases"):
            url = "%s/%s?symbols=%s&limit=%d&apikey=%s" % (STABLE, ep, chunk, per_symbol_limit * batch, key)
            status, body = get(url)
            if status == 200 and isinstance(body, list):
                for sym, items in parse_news(body, want).items():
                    merged.setdefault(sym, [])
                    have = set(x["title"] for x in merged[sym])
                    for it in items:
                        if it["title"] not in have:
                            merged[sym].append(it); have.add(it["title"])
    for sym in merged:
        merged[sym].sort(key=lambda x: x["date"], reverse=True)
        merged[sym] = merged[sym][:per_symbol_limit]
    return merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--marketmap", default="marketmap.json")
    ap.add_argument("--out", default="data/news.json")
    ap.add_argument("--limit", type=int, default=15)
    a = ap.parse_args()
    try:
        mm = json.load(open(a.marketmap))
        syms = [n["t"] for n in mm.get("names", []) if n.get("t") and "FACTOR" not in (n.get("idx") or [])]
    except Exception as e:
        sys.stderr.write("fmp_news: cannot read universe (%s)\n" % str(e)[:80]); return 0
    news = fetch(syms, per_symbol_limit=a.limit)
    if not news:
        sys.stderr.write("fmp_news: no news (no key / network / off-hours) — skipped\n"); return 0
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    tmp = a.out + ".tmp"
    json.dump({"_meta": {"symbols": len(news)}, "news": news}, open(tmp, "w"), separators=(",", ":"))
    os.replace(tmp, a.out)
    sys.stderr.write("fmp_news: wrote %s for %d symbols\n" % (a.out, len(news)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
