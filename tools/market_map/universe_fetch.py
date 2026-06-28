#!/usr/bin/env python3
"""
universe_fetch.py — build the EQUITY universe for the nightly market map.

The legacy build hard-coded a 92-name SEED list (the "~155 companies" the board ranked). This module
fetches the FULL Nasdaq Composite (every Nasdaq-listed common stock) plus the Dow 30, so the Bull/Bear
board ranks the real index membership instead of a hand-picked cross-section.

Sources (fail-soft; any failure returns None so the caller falls back to SEED — the build never breaks):
  1. FMP company-screener (PRIMARY): exchange=NASDAQ, actively-trading, ETFs/funds excluded. Returns
     symbol + companyName + sector + marketCap, so names arrive PRE-SORTED by market cap (the per-pull
     caps for options/IV/earnings then naturally cover the most liquid names first) and carry a sector.
  2. Nasdaq Trader symbol directory (KEYLESS fallback): nasdaqlisted.txt, filtered to ETF='N',
     Test Issue='N'. No sector/mcap, but fully keyless.
  3. DOW30 is a fixed 30-name set merged in (many are NYSE-listed, so they extend beyond Nasdaq).

Returns a list of (ticker, name, sector, membership_code) tuples — the exact shape build_market_map.SEED
uses — so wiring is a one-line swap of the iteration source.

Env:
  UNIVERSE_MODE   'seed' (default, legacy SEED) | 'nasdaq_full' (this module)
  UNIVERSE_LIMIT  optional int cap on the equity count (0/unset = no cap = the full composite)
"""
import os, sys, json

# Dow Jones Industrial Average components (as-of 2025-06; DJIA changes ~once/yr). Overridable via DOW30 env
# (comma-separated). Code 'D' marks Dow membership; names also on Nasdaq are tagged 'ND D' after the merge.
DOW30_DEFAULT = ["AAPL", "AMGN", "AMZN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS",
                 "GS", "HD", "HON", "IBM", "JNJ", "JPM", "KO", "MCD", "MMM", "MRK",
                 "MSFT", "NKE", "NVDA", "PG", "SHW", "TRV", "UNH", "V", "VZ", "WMT"]

# FMP sector strings -> the board's canonical sector buckets (matches build_market_map.SECMAP intent).
_SECTOR_MAP = {
    "Technology": "Technology", "Information Technology": "Technology",
    "Financial Services": "Financials", "Financials": "Financials", "Financial": "Financials",
    "Healthcare": "Health Care", "Health Care": "Health Care",
    "Consumer Cyclical": "Consumer Disc.", "Consumer Discretionary": "Consumer Disc.",
    "Consumer Defensive": "Consumer Staples", "Consumer Staples": "Consumer Staples",
    "Communication Services": "Communication", "Communication": "Communication",
    "Industrials": "Industrials", "Industrial Goods": "Industrials",
    "Energy": "Energy", "Basic Materials": "Materials", "Materials": "Materials",
    "Utilities": "Utilities", "Real Estate": "Real Estate",
}


def _norm_sector(s):
    return _SECTOR_MAP.get((s or "").strip(), (s or "").strip() or "Unknown")


def _ok_symbol(sym):
    """Keep plain common-stock tickers: letters only, <=5 chars (drop warrants/units/preferreds like ABCDW, ABCDU, ABC.PR)."""
    sym = (sym or "").strip().upper()
    return bool(sym) and sym.isalpha() and 1 <= len(sym) <= 5


def parse_screener(rows):
    """FMP company-screener JSON -> [(ticker,name,sector,code)] for Nasdaq common stocks (ETFs/funds dropped)."""
    out = []
    for r in rows or []:
        try:
            sym = (r.get("symbol") or "").strip().upper()
            if not _ok_symbol(sym):
                continue
            if r.get("isEtf") or r.get("isFund") or r.get("isAdr"):
                continue
            exch = (r.get("exchangeShortName") or r.get("exchange") or "").upper()
            if exch and "NASDAQ" not in exch:
                continue
            nm = (r.get("companyName") or r.get("name") or sym).strip()
            out.append((sym, nm, _norm_sector(r.get("sector")), "ND"))
        except Exception:
            continue
    return out


def parse_nasdaqlisted(text):
    """Nasdaq Trader nasdaqlisted.txt (pipe-delimited) -> [(ticker,name,'',code)] for common stocks."""
    out = []
    lines = (text or "").splitlines()
    if not lines:
        return out
    hdr = lines[0].split("|")
    idx = {h.strip(): i for i, h in enumerate(hdr)}
    si = idx.get("Symbol", 0); ni = idx.get("Security Name", 1)
    ti = idx.get("Test Issue"); ei = idx.get("ETF")
    for ln in lines[1:]:
        if ln.startswith("File Creation Time"):
            continue
        p = ln.split("|")
        if len(p) <= si:
            continue
        sym = p[si].strip().upper()
        if not _ok_symbol(sym):
            continue
        if ti is not None and ti < len(p) and p[ti].strip().upper() == "Y":
            continue
        if ei is not None and ei < len(p) and p[ei].strip().upper() == "Y":
            continue
        nm = p[ni].strip() if ni < len(p) else sym
        out.append((sym, nm, "Unknown", "ND"))
    return out


def _merge_dow(rows, dow):
    """Tag Dow members already present with 'D', and append any Dow names missing from the Nasdaq set."""
    have = {r[0]: i for i, r in enumerate(rows)}
    out = [list(r) for r in rows]
    for d in dow:
        d = d.strip().upper()
        if not _ok_symbol(d):
            continue
        if d in have:
            code = out[have[d]][3]
            if "D" not in code.split():
                out[have[d]][3] = (code + " D").strip()
        else:
            out.append([d, d, "Unknown", "ND D" if False else "D"])
    return [tuple(r) for r in out]


def fetch_screener_rows(session, key, base, exchange="NASDAQ", limit=10000):
    """GET the FMP stable company-screener. Returns the raw JSON list, or [] on any failure."""
    try:
        import requests
        sess = session or requests
        url = "%s/company-screener?exchange=%s&isActivelyTrading=true&limit=%d&apikey=%s" % (
            base.rstrip("/"), exchange, int(limit), key)
        r = sess.get(url, timeout=45)
        if r.status_code != 200:
            sys.stderr.write("universe_fetch: screener HTTP %s\n" % r.status_code)
            return []
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        sys.stderr.write("universe_fetch: screener error %s\n" % str(e)[:160])
        return []


def fetch_nasdaqtrader(session):
    """KEYLESS fallback: the official Nasdaq Trader symbol directory."""
    try:
        import requests
        sess = session or requests
        url = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
        r = sess.get(url, timeout=45)
        if r.status_code != 200:
            return []
        return parse_nasdaqlisted(r.text)
    except Exception as e:
        sys.stderr.write("universe_fetch: nasdaqtrader error %s\n" % str(e)[:160])
        return []


def fetch_universe(mode=None, key=None, session=None, base="https://financialmodelingprep.com/stable",
                   limit=None, dow=None):
    """Top-level: return [(ticker,name,sector,code)] for the requested universe, or None to use SEED.
    mode 'nasdaq_full' -> full Nasdaq Composite + Dow 30. Anything else -> None (caller keeps SEED)."""
    mode = (mode if mode is not None else os.environ.get("UNIVERSE_MODE", "seed")).strip().lower()
    if mode not in ("nasdaq_full", "nasdaq", "full"):
        return None
    if limit is None:
        try:
            limit = int(os.environ.get("UNIVERSE_LIMIT", "0") or 0) or None
        except Exception:
            limit = None
    dow = dow or [d for d in os.environ.get("DOW30", "").split(",") if d.strip()] or DOW30_DEFAULT

    rows = []
    if key:
        rows = parse_screener(fetch_screener_rows(session, key, base, "NASDAQ", limit or 10000))
    if not rows:
        rows = fetch_nasdaqtrader(session)            # keyless fallback (no sector/mcap)
    if not rows:
        return None                                   # total failure -> caller falls back to SEED

    # de-dup (screener can repeat), keep first (screener is mcap-sorted so first = larger cap)
    seen = set(); dedup = []
    for r in rows:
        if r[0] in seen:
            continue
        seen.add(r[0]); dedup.append(r)
    merged = _merge_dow(dedup, dow)
    if limit and len(merged) > limit:
        # keep the Dow names + the top-`limit` by screener order (already mcap-sorted)
        dow_set = set(d.strip().upper() for d in dow)
        head = [r for r in merged if r[0] in dow_set]
        rest = [r for r in merged if r[0] not in dow_set]
        merged = head + rest[:max(0, limit - len(head))]
    sys.stderr.write("universe_fetch: mode=%s names=%d (incl. Dow %d)\n" % (mode, len(merged), len(dow)))
    return merged


def main():
    """CLI smoke: `python3 universe_fetch.py` prints the count + first rows (needs FMP key or network)."""
    try:
        import fmp_history as fh
        key = fh._key()
    except Exception:
        key = os.environ.get("FMP_API_KEY")
    u = fetch_universe("nasdaq_full", key=key)
    if not u:
        print("no universe (no key/network) — caller would keep SEED"); return
    print("universe size:", len(u))
    for r in u[:10]:
        print(r)


if __name__ == "__main__":
    main()
