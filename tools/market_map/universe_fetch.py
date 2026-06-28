#!/usr/bin/env python3
"""
universe_fetch.py — build the EQUITY universe for the nightly market map from the REAL index membership of
the S&P 500, the full Nasdaq Composite, the Dow 30, and the Russell 2000 — unioned and membership-tagged.

The legacy build hard-coded a 92-name SEED list (the "~155 companies" the board ranked). This module pulls
each index from its best free / credible source, fail-soft (any source that fails is skipped; total failure
returns None so the caller falls back to SEED and the build never breaks):

  * S&P 500     FMP `sp500-constituent`  (stable; v3 `sp500_constituent` fallback)        -> tag 'S'  (SPX)
  * Nasdaq      FMP company-screener exchange=NASDAQ (full composite) + `nasdaq-constituent`
                for guaranteed sectors on the Nasdaq-100; keyless nasdaqlisted.txt fallback -> tag 'ND' (NDX)
  * Dow 30      FMP `dowjones-constituent` (stable; v3 fallback); hardcoded DOW30 fallback   -> tag 'D'  (DOW)
  * Russell 2000  keyless iShares IWM daily holdings CSV                                     -> tag 'R'  (RUT)

A name that belongs to several indices accumulates several tags (e.g. AAPL -> "S ND D"); the tags feed
build_market_map.membership() -> NDX/DOW/SPX/RUT for board labelling/filtering. Returns a list of
(ticker, name, sector, membership_code) tuples — the exact shape build_market_map.SEED uses.

Env:
  UNIVERSE_MODE     'seed' (legacy SEED) | 'all'/'nasdaq_full'/'indices' (this module; default 'all')
  UNIVERSE_INDEXES  comma list of {sp500,nasdaq,dow,russell2000} to include (default: all four)
  UNIVERSE_LIMIT    optional int cap (0/unset = the full union; S&P + Dow members are always kept)
  DOW30             optional comma-separated Dow override
"""
import os, sys

DOW30_DEFAULT = ["AAPL", "AMGN", "AMZN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS",
                 "GS", "HD", "HON", "IBM", "JNJ", "JPM", "KO", "MCD", "MMM", "MRK",
                 "MSFT", "NKE", "NVDA", "PG", "SHW", "TRV", "UNH", "V", "VZ", "WMT"]
DEFAULT_INDEXES = ["sp500", "nasdaq", "dow", "russell2000"]
_FMP_V3 = "https://financialmodelingprep.com/api/v3"
_IWM_CSV = ("https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/"
            "1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund")

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
    """Keep plain common-stock tickers: letters only, <=5 chars (drops warrants/units/dotted class shares)."""
    sym = (sym or "").strip().upper()
    return bool(sym) and sym.isalpha() and 1 <= len(sym) <= 5


def _get_json(session, url):
    try:
        import requests
        r = (session or requests).get(url, timeout=45)
        if r.status_code != 200:
            sys.stderr.write("universe_fetch: HTTP %s %s\n" % (r.status_code, url.split("?")[0]))
            return []
        d = r.json()
        return d if isinstance(d, list) else []
    except Exception as e:
        sys.stderr.write("universe_fetch: GET error %s\n" % str(e)[:160])
        return []


# ---------------- per-source fetchers / parsers ----------------
def parse_screener(rows):
    """FMP company-screener JSON -> [(ticker,name,sector,'ND')] for Nasdaq common stocks (ETFs/funds dropped)."""
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
            out.append((sym, (r.get("companyName") or r.get("name") or sym).strip(), _norm_sector(r.get("sector")), "ND"))
        except Exception:
            continue
    return out


def parse_constituent(rows, tag):
    """FMP {sp500,nasdaq,dowjones}-constituent JSON -> [(ticker,name,sector,tag)]."""
    out = []
    for r in rows or []:
        try:
            sym = (r.get("symbol") or "").strip().upper()
            if not _ok_symbol(sym):
                continue
            out.append((sym, (r.get("name") or r.get("companyName") or sym).strip(), _norm_sector(r.get("sector")), tag))
        except Exception:
            continue
    return out


def parse_nasdaqlisted(text):
    """Nasdaq Trader nasdaqlisted.txt (pipe-delimited) -> [(ticker,name,'Unknown','ND')] for common stocks."""
    out = []
    lines = (text or "").splitlines()
    if not lines:
        return out
    idx = {h.strip(): i for i, h in enumerate(lines[0].split("|"))}
    si = idx.get("Symbol", 0); ni = idx.get("Security Name", 1); ti = idx.get("Test Issue"); ei = idx.get("ETF")
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
        out.append((sym, (p[ni].strip() if ni < len(p) else sym), "Unknown", "ND"))
    return out


def parse_iwm_csv(text):
    """iShares IWM holdings CSV -> [(ticker,name,sector,'R')] for the Russell 2000 constituents."""
    import csv, io
    out = []
    rows = list(csv.reader(io.StringIO(text or "")))
    hdr = None
    for i, r in enumerate(rows):
        if "Ticker" in r and "Sector" in r:
            hdr = i; break
    if hdr is None:
        return out
    H = rows[hdr]; ci = H.index("Ticker"); si = H.index("Sector"); ni = H.index("Name") if "Name" in H else ci
    for r in rows[hdr + 1:]:
        if len(r) <= max(ci, si):
            continue
        tk = r[ci].strip().upper()
        if not _ok_symbol(tk):
            continue
        sec = _norm_sector(r[si].strip()) if si < len(r) else "Unknown"
        out.append((tk, (r[ni].strip()[:40] if ni < len(r) else tk), sec, "R"))
    return out


def fetch_constituent(session, key, base, stable_ep, v3_ep, tag):
    """FMP index-constituent with stable->v3 fallback. Returns parsed [(sym,name,sector,tag)]."""
    if not key:
        return []
    rows = _get_json(session, "%s/%s?apikey=%s" % (base.rstrip("/"), stable_ep, key))
    if not rows:
        rows = _get_json(session, "%s/%s?apikey=%s" % (_FMP_V3, v3_ep, key))
    return parse_constituent(rows, tag)


def fetch_screener_rows(session, key, base, exchange="NASDAQ", limit=10000):
    if not key:
        return []
    return _get_json(session, "%s/company-screener?exchange=%s&isActivelyTrading=true&limit=%d&apikey=%s" % (
        base.rstrip("/"), exchange, int(limit), key))


def fetch_nasdaqtrader(session):
    """KEYLESS fallback: the official Nasdaq Trader symbol directory."""
    try:
        import requests
        r = (session or requests).get("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt", timeout=45)
        return parse_nasdaqlisted(r.text) if r.status_code == 200 else []
    except Exception as e:
        sys.stderr.write("universe_fetch: nasdaqtrader error %s\n" % str(e)[:160]); return []


def fetch_iwm_holdings(session, limit=None):
    """KEYLESS Russell 2000 constituents from the iShares IWM daily holdings CSV."""
    try:
        import requests
        r = (session or requests).get(_IWM_CSV, timeout=60)
        if r.status_code != 200:
            sys.stderr.write("universe_fetch: IWM HTTP %s\n" % r.status_code); return []
        out = parse_iwm_csv(r.text)
        return out[:limit] if limit else out
    except Exception as e:
        sys.stderr.write("universe_fetch: IWM error %s\n" % str(e)[:160]); return []


def _merge_dow(rows, dow):
    """Legacy helper (kept for tests): tag Dow members present with 'D', append any missing."""
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
            out.append([d, d, "Unknown", "D"])
    return [tuple(r) for r in out]


# ---------------- top-level union ----------------
def fetch_universe(mode=None, key=None, session=None, base="https://financialmodelingprep.com/stable",
                   limit=None, dow=None, indexes=None):
    """Union the requested indices into [(ticker,name,sector,code)], or None to fall back to SEED.
    code is the space-joined membership tag set (S/ND/D/R) consumed by build_market_map.membership()."""
    mode = (mode if mode is not None else os.environ.get("UNIVERSE_MODE", "all")).strip().lower()
    if mode in ("seed", "none", "off", ""):
        return None
    if indexes is None:
        indexes = [s.strip().lower() for s in os.environ.get("UNIVERSE_INDEXES", "").split(",") if s.strip()] or DEFAULT_INDEXES
    if limit is None:
        try:
            limit = int(os.environ.get("UNIVERSE_LIMIT", "0") or 0) or None
        except Exception:
            limit = None
    dow = dow or [d for d in os.environ.get("DOW30", "").split(",") if d.strip()] or DOW30_DEFAULT

    acc = {}; order = []
    def add(sym, name, sector, tag):
        s = (sym or "").strip().upper()
        if not _ok_symbol(s):
            return
        if s not in acc:
            acc[s] = [name or s, sector or "Unknown", set()]; order.append(s)
        acc[s][2].add(tag)
        if acc[s][1] in (None, "", "Unknown") and sector not in (None, "", "Unknown"):
            acc[s][1] = sector
        if (not acc[s][0]) and name:
            acc[s][0] = name

    # order matters for the limit head: S&P + Dow (large caps) first, then Nasdaq (mcap-sorted), then Russell.
    if "sp500" in indexes:
        for sym, nm, sec, tg in fetch_constituent(session, key, base, "sp500-constituent", "sp500_constituent", "S"):
            add(sym, nm, sec, tg)
    if "dow" in indexes:
        d = fetch_constituent(session, key, base, "dowjones-constituent", "dowjones_constituent", "D")
        if d:
            for sym, nm, sec, tg in d:
                add(sym, nm, sec, tg)
        else:
            for sym in dow:
                add(sym, sym, "Unknown", "D")
    if "nasdaq" in indexes:
        rows = parse_screener(fetch_screener_rows(session, key, base, "NASDAQ", (limit or 6000))) if key else []
        if not rows:
            rows = fetch_nasdaqtrader(session)
        for sym, nm, sec, tg in rows:
            add(sym, nm, sec, tg)
        for sym, nm, sec, tg in fetch_constituent(session, key, base, "nasdaq-constituent", "nasdaq_constituent", "ND"):
            add(sym, nm, sec, tg)   # guarantees sectors on the Nasdaq-100
    if "russell2000" in indexes:
        for sym, nm, sec, tg in fetch_iwm_holdings(session):
            add(sym, nm, sec, tg)

    if not acc:
        return None
    out = [(s, acc[s][0] or s, acc[s][1] or "Unknown", " ".join(sorted(acc[s][2]))) for s in order]
    if limit and len(out) > limit:
        keep = [r for r in out if ("S" in r[3].split() or "D" in r[3].split())]   # always keep S&P + Dow
        rest = [r for r in out if not ("S" in r[3].split() or "D" in r[3].split())]
        out = keep + rest[:max(0, limit - len(keep))]
    by = {"S": 0, "ND": 0, "D": 0, "R": 0}
    for r in out:
        for t in r[3].split():
            by[t] = by.get(t, 0) + 1
    sys.stderr.write("universe_fetch: mode=%s names=%d (SPX %d, NDX %d, DOW %d, RUT %d)\n" % (
        mode, len(out), by.get("S", 0), by.get("ND", 0), by.get("D", 0), by.get("R", 0)))
    return out


def main():
    """CLI smoke: prints the union size + membership breakdown (needs FMP key + network)."""
    try:
        import fmp_history as fh
        key = fh._key()
    except Exception:
        key = os.environ.get("FMP_API_KEY")
    u = fetch_universe("all", key=key)
    if not u:
        print("no universe (no key/network) — caller would keep SEED"); return
    print("universe size:", len(u))
    for r in u[:12]:
        print(r)


if __name__ == "__main__":
    main()
# verified: S&P500 + full Nasdaq + Dow30 + Russell2000 union with S/ND/D/R membership tags.
