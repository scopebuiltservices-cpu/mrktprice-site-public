#!/usr/bin/env python3
"""fmp_float.py — GATED FMP connector for REAL free-float share counts (/stable/shares-float).

FMP does NOT provide short interest (confirmed in their docs), so the crowding numerator stays SEC
fails-to-deliver. But FMP Ultimate DOES provide real FLOAT — and short-interest-of-FLOAT is the correct
ratio (float < shares outstanding, especially for founder/insider-heavy names). This connector fetches the
free-float share count per symbol and emits float.json {ticker: {floatShares, outShares, freeFloatPct}};
crowding_board.py uses floatShares as the denominator when present, else falls back to mcap/price.

Network runs ONLY in CI (gated on the FMP key); the parser is pure + offline-tested. Research only."""
import argparse, json, os, sys

STABLE = "https://financialmodelingprep.com/stable"


def _key():
    for k in ("FMP_ULTIMATE_API_KEY", "FMP_API_KEY", "FMP_UTIMATE_API_KEY"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return ""


def _num(x):
    try:
        v = float(x)
        return v if v == v else None
    except Exception:
        return None


def parse_float(payload):
    """FMP shares-float returns a list (newest first) of records. Defensive across field-name variants:
    floatShares|float (share count), outstandingShares|sharesOutstanding (count), freeFloat (PERCENT).
    Returns {floatShares, outShares, freeFloatPct} or None. If floatShares is absent but freeFloat% +
    outShares are present, derive floatShares = freeFloat/100 * outShares."""
    rec = None
    if isinstance(payload, list) and payload:
        rec = payload[0]
    elif isinstance(payload, dict):
        rec = payload
    if not isinstance(rec, dict):
        return None
    fl = _num(rec.get("floatShares"))
    if fl is None:
        fl = _num(rec.get("float"))
    out = _num(rec.get("outstandingShares"))
    if out is None:
        out = _num(rec.get("sharesOutstanding"))
    pct = _num(rec.get("freeFloat"))
    if fl is None and pct is not None and out is not None:
        fl = (pct / 100.0) * out
    if fl is None and out is None and pct is None:
        return None
    return {"floatShares": fl, "outShares": out, "freeFloatPct": pct}


def fetch_one(symbol, sess, key, timeout=20):
    url = "%s/shares-float?symbol=%s&apikey=%s" % (STABLE, symbol, key)
    r = sess.get(url, timeout=timeout)
    if r.status_code != 200:
        return None
    return parse_float(r.json())


def build(symbols, key=None, sleep=0.05):
    """CI-only (network). Returns {ticker: {floatShares, outShares, freeFloatPct}}."""
    import requests, time
    key = key or _key()
    if not key:
        sys.stderr.write("fmp_float: no FMP key — skipped\n")
        return {}
    s = requests.Session()
    out = {}
    for t in symbols:
        try:
            d = fetch_one(t, s, key)
            if d:
                out[t] = d
        except Exception as ex:
            sys.stderr.write("fmp_float: %s failed: %s\n" % (t, str(ex)[:60]))
        time.sleep(sleep)
    return out


def _names(marketmap):
    try:
        mm = json.load(open(marketmap))
        return [n["t"] for n in mm.get("names", []) if n.get("t")]
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--marketmap", default="marketmap.json")
    ap.add_argument("--out", default="data/float.json")
    a = ap.parse_args()
    names = _names(a.marketmap)
    if not names:
        sys.stderr.write("fmp_float: no universe — skipped\n")
        return 0
    res = build(names)
    if not res:
        return 0
    res["_meta"] = {"names": len(res), "source": "FMP /stable/shares-float"}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    tmp = a.out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(res, f, separators=(",", ":"))
    os.replace(tmp, a.out)
    sys.stderr.write("fmp_float: wrote %s for %d names\n" % (a.out, len(res) - 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
