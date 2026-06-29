#!/usr/bin/env python3
"""fmp_bulk.py — GATED FMP BULK connector. THE infra win: pull the WHOLE universe per dataset in ONE call.

FMP Ultimate exposes bulk CSV endpoints that return every symbol at once (vs ~155 per-symbol calls each).
This connector fetches four bulk CSVs — ratios-ttm-bulk, key-metrics-ttm-bulk, price-target-summary-bulk,
rating-bulk — parses them defensively (field names vary across FMP versions, so every field is picked from
a candidate list), and merges by symbol into data/fundamentals.json:
    {ticker: {pe, pb, roe, netMargin, debtEq, fcfYield, divYield, targetAvg, rating, ratingScore, src}}

That's 4 calls instead of ~600, slashing nightly runtime and freeing rate-limit headroom for more datasets.
Network runs ONLY in CI (gated on the FMP key); the CSV parser + merge are pure + offline-tested. Research only."""
import argparse, csv, io, json, os, sys

STABLE = "https://financialmodelingprep.com/stable"
BULK = {
    "ratios":   "ratios-ttm-bulk",
    "metrics":  "key-metrics-ttm-bulk",
    "targets":  "price-target-summary-bulk",
    "rating":   "rating-bulk",
}


def _key():
    for k in ("FMP_ULTIMATE_API_KEY", "FMP_API_KEY", "FMP_UTIMATE_API_KEY"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return ""


def _num(x):
    try:
        if x is None or x == "":
            return None
        v = float(x)
        return v if v == v else None
    except Exception:
        return None


def parse_bulk_csv(text):
    """Bulk endpoints return CSV with a header row. Returns list[dict]. Tolerates a JSON-array body too."""
    s = (text or "").lstrip()
    if s[:1] == "[":                                   # some deployments return JSON
        try:
            d = json.loads(s)
            return d if isinstance(d, list) else []
        except Exception:
            return []
    rows = list(csv.DictReader(io.StringIO(text)))
    return rows


def _pick(row, *names):
    for n in names:
        if n in row and row[n] not in (None, ""):
            return row[n]
    # case-insensitive fallback
    low = {k.lower(): v for k, v in row.items()}
    for n in names:
        v = low.get(n.lower())
        if v not in (None, ""):
            return v
    return None


def _sym(row):
    return (_pick(row, "symbol", "Symbol", "ticker") or "").upper()


def merge(ratios_rows, metrics_rows, target_rows, rating_rows):
    """Merge the four bulk datasets by symbol into the per-name fundamentals block."""
    out = {}
    for r in ratios_rows or []:
        t = _sym(r)
        if not t:
            continue
        d = out.setdefault(t, {})
        _pe = _num(_pick(r, "priceToEarningsRatioTTM", "peRatioTTM", "priceEarningsRatioTTM"))
        d["pe"]       = _pe if (_pe is not None and 0 < _pe <= 200) else None   # winsor: drop loss-maker / pathological P/E
        d["pb"]       = _num(_pick(r, "priceToBookRatioTTM", "pbRatioTTM", "priceToBookTTM"))
        d["netMargin"]= _num(_pick(r, "netProfitMarginTTM", "netIncomeMarginTTM"))
        d["debtEq"]   = _num(_pick(r, "debtToEquityRatioTTM", "debtEquityRatioTTM", "debtToEquityTTM"))
        d["divYield"] = _num(_pick(r, "dividendYieldTTM", "dividendYielTTM"))
        d["fcfYield"] = _num(_pick(r, "freeCashFlowYieldTTM", "fcfYieldTTM"))
    for r in metrics_rows or []:
        t = _sym(r)
        if not t:
            continue
        d = out.setdefault(t, {})
        d["roe"]   = _num(_pick(r, "returnOnEquityTTM", "roeTTM"))
        if d.get("fcfYield") is None:
            d["fcfYield"] = _num(_pick(r, "freeCashFlowYieldTTM", "fcfYieldTTM"))
    for r in target_rows or []:
        t = _sym(r)
        if not t:
            continue
        d = out.setdefault(t, {})
        # prefer the most recent rolling window with data
        d["targetAvg"] = _num(_pick(r, "lastMonthAvgPriceTarget", "lastQuarterAvgPriceTarget",
                                    "lastYearAvgPriceTarget", "allTimeAvgPriceTarget"))
        d["targetN"]   = _num(_pick(r, "lastMonthCount", "lastQuarterCount", "allTimeCount"))
    for r in rating_rows or []:
        t = _sym(r)
        if not t:
            continue
        d = out.setdefault(t, {})
        d["rating"]      = _pick(r, "rating", "ratingRecommendation")
        d["ratingScore"] = _num(_pick(r, "ratingScore", "overallScore", "score"))
    for t, d in out.items():
        d["src"] = "FMP bulk (ratios+metrics+targets+rating)"
    return out


def fetch_csv(slug, sess, key, timeout=60):
    url = "%s/%s?apikey=%s" % (STABLE, slug, key)
    r = sess.get(url, timeout=timeout)
    if r.status_code != 200:
        return []
    return parse_bulk_csv(r.text)


def build(key=None):
    """CI-only (network). Returns the merged {ticker: fundamentals} dict."""
    import requests
    key = key or _key()
    if not key:
        sys.stderr.write("fmp_bulk: no FMP key — skipped\n")
        return {}
    s = requests.Session()
    data = {}
    for logical, slug in BULK.items():
        try:
            data[logical] = fetch_csv(slug, s, key)
        except Exception as ex:
            sys.stderr.write("fmp_bulk: %s (%s) failed: %s\n" % (logical, slug, str(ex)[:60]))
            data[logical] = []
    return merge(data.get("ratios"), data.get("metrics"), data.get("targets"), data.get("rating"))


def _universe(marketmap):
    try:
        mm = json.load(open(marketmap))
        return set(n["t"].upper() for n in mm.get("names", []) if n.get("t"))
    except Exception:
        return set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--marketmap", default="marketmap.json")
    ap.add_argument("--out", default="data/fundamentals.json")
    a = ap.parse_args()
    res = build()
    if not res:
        return 0
    uni = _universe(a.marketmap)
    if uni:                                            # keep only our universe (bulk returns the whole market)
        res = {k: v for k, v in res.items() if k in uni}
    import datetime as _dt
    res["_meta"] = {"names": len(res), "source": "FMP bulk: " + ",".join(BULK.values()),
                    "asof": _dt.date.today().isoformat(), "pit": False,
                    "note": "current-vintage TTM/consensus; NOT point-in-time. Do not feed into the no-lookahead ledger/IC without PIT gating."}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    tmp = a.out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(res, f, separators=(",", ":"))
    os.replace(tmp, a.out)
    sys.stderr.write("fmp_bulk: wrote %s for %d names (4 bulk calls)\n" % (a.out, len(res) - 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
