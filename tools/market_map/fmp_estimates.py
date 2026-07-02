#!/usr/bin/env python3
"""fmp_estimates.py — GATED FMP connector: forward analyst ESTIMATES + earnings SURPRISES + EBITDA (per symbol).

Fetched per symbol (no bulk endpoint):
  - analyst-estimates?symbol=X&period=annual  -> next fiscal period consensus revenue/EPS/EBITDA (avg, n)
  - earnings?symbol=X                          -> most recent epsActual vs epsEstimated -> surprise %
  - income-statement?symbol=X&period=quarter   -> latest quarter EBITDA (GAAP) -> 'last quarter' EBITDA
Emits data/estimates.json {ticker: {fy, revAvg, epsAvg, nEst, ebitdaNextQ, surprisePct, surpriseDate,
ebitdaLastQ, ebitdaLastQDate}}. The board folds these into n.fund for the daily report's EBITDA + forward
panels. Network runs ONLY in CI (gated); parsers pure + offline-tested. Research only, not advice."""
import argparse, datetime as dt, json, os, sys

STABLE = "https://financialmodelingprep.com/stable"


def _key():
    v = os.environ.get("FMP_ULTIMATE_API_KEY", "").strip()
    return v if v else ""


def _num(x):
    try:
        if x is None or x == "":
            return None
        v = float(x)
        return v if v == v else None
    except Exception:
        return None


def _pick(rec, *names):
    for n in names:
        if isinstance(rec, dict) and rec.get(n) not in (None, ""):
            return rec.get(n)
    return None


def parse_estimates(payload, today=None):
    """analyst-estimates list (per fiscal period). Pick the nearest FUTURE period; else the newest."""
    today = today or dt.date.today()
    if not isinstance(payload, list) or not payload:
        return None
    def d(r):
        s = str(_pick(r, "date", "fiscalDate") or "")[:10]
        try:
            return dt.date.fromisoformat(s)
        except Exception:
            return None
    future = [r for r in payload if d(r) and d(r) >= today]
    rec = min(future, key=d) if future else max(payload, key=lambda r: (d(r) or dt.date.min))
    return {
        "fy": str(_pick(rec, "date", "fiscalDate") or "")[:10],
        "revAvg": _num(_pick(rec, "estimatedRevenueAvg", "revenueAvg", "estimatedRevenue")),
        "epsAvg": _num(_pick(rec, "estimatedEpsAvg", "epsAvg", "estimatedEps")),
        "nEst": _num(_pick(rec, "numberAnalystsEstimatedRevenue", "numberAnalystEstimatedEps", "numberAnalysts")),
        "ebitdaNextQ": _num(_pick(rec, "estimatedEbitdaAvg", "ebitdaAvg", "estimatedEbitda")),
    }


def parse_income(payload):
    """income-statement list (newest first). Latest period's EBITDA -> 'last quarter' EBITDA (GAAP)."""
    if not isinstance(payload, list) or not payload:
        return None
    rec = payload[0]
    eb = _num(_pick(rec, "ebitda", "EBITDA"))
    return {"ebitdaLastQ": eb, "ebitdaLastQDate": str(_pick(rec, "date") or "")[:10]} if eb is not None else None


def parse_surprise(payload):
    """earnings list (newest first). Most recent row with BOTH actual+estimated -> surprise %."""
    if not isinstance(payload, list):
        return None
    for rec in payload:
        a = _num(_pick(rec, "epsActual", "epsActuals"))
        e = _num(_pick(rec, "epsEstimated", "epsEstimate"))
        if a is not None and e not in (None, 0):
            return {"surprisePct": round((a - e) / abs(e) * 100.0, 2),
                    "surpriseDate": str(_pick(rec, "date") or "")[:10]}
    return None


def fetch_one(symbol, sess, key, timeout=20):
    out = {}
    try:
        r = sess.get("%s/analyst-estimates?symbol=%s&period=annual&page=0&limit=8&apikey=%s" % (STABLE, symbol, key), timeout=timeout)
        if r.status_code == 200:
            est = parse_estimates(r.json())
            if est:
                out.update(est)
    except Exception:
        pass
    try:
        r = sess.get("%s/earnings?symbol=%s&limit=8&apikey=%s" % (STABLE, symbol, key), timeout=timeout)
        if r.status_code == 200:
            sp = parse_surprise(r.json())
            if sp:
                out.update(sp)
    except Exception:
        pass
    try:
        r = sess.get("%s/income-statement?symbol=%s&period=quarter&limit=1&apikey=%s" % (STABLE, symbol, key), timeout=timeout)
        if r.status_code == 200:
            inc = parse_income(r.json())
            if inc:
                out.update(inc)
    except Exception:
        pass
    return out or None


def build(symbols, key=None, sleep=0.04):
    import requests, time
    key = key or _key()
    if not key:
        sys.stderr.write("fmp_estimates: no FMP key — skipped\n")
        return {}
    s = requests.Session()
    out = {}
    for t in symbols:
        d = fetch_one(t, s, key)
        if d:
            out[t] = d
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
    ap.add_argument("--out", default="data/estimates.json")
    a = ap.parse_args()
    names = _names(a.marketmap)
    if not names:
        sys.stderr.write("fmp_estimates: no universe — skipped\n")
        return 0
    res = build(names)
    if not res:
        return 0
    res["_meta"] = {"names": len(res), "source": "FMP analyst-estimates + earnings + income-statement EBITDA"}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    tmp = a.out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(res, f, separators=(",", ":"))
    os.replace(tmp, a.out)
    sys.stderr.write("fmp_estimates: wrote %s for %d names\n" % (a.out, len(res) - 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
