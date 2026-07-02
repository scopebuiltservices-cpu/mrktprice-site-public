#!/usr/bin/env python3
"""fmp_actions.py — GATED FMP connector: corporate ACTIONS (dividends + splits) per symbol.

  - dividends?symbol=X -> trailing-12-month cash dividend total (income leg of total return) + next ex-date
  - splits?symbol=X    -> most recent split (date + ratio), for the timeline + liquidity context
Emits data/actions.json {ticker: {div12m, nextExDate, lastSplit:{date,ratio}}}. FMP EOD prices are already
split-adjusted, so splits are informational; the dividend total feeds the total-return income component.
Network runs ONLY in CI (gated); parsers pure + offline-tested. Research only, not advice."""
import argparse, datetime as dt, json, os, sys

STABLE = "https://financialmodelingprep.com/stable"


def _key():
    v = os.environ.get("FMP_ULTIMATE_API_KEY", "").strip()
    return v if v else ""


def _num(x):
    try:
        if x in (None, ""):
            return None
        v = float(x)
        return v if v == v else None
    except Exception:
        return None


def _pick(r, *names):
    for n in names:
        if isinstance(r, dict) and r.get(n) not in (None, ""):
            return r.get(n)
    return None


def _d(r, *names):
    s = str(_pick(r, *names) or "")[:10]
    try:
        return dt.date.fromisoformat(s)
    except Exception:
        return None


def parse_dividends(payload, today=None):
    """Sum cash dividends in the trailing 365 days; find the next future ex-date."""
    today = today or dt.date.today()
    if not isinstance(payload, list) or not payload:
        return None
    div12 = 0.0; got = False; nxt = None
    for r in payload:
        d = _d(r, "date", "recordDate")
        amt = _num(_pick(r, "dividend", "adjDividend", "amount"))
        if d is None:
            continue
        if amt is not None and 0 <= (today - d).days <= 365:
            div12 += amt; got = True
        if d >= today and (nxt is None or d < nxt):
            nxt = d
    if not got and nxt is None:
        return None
    return {"div12m": round(div12, 4) if got else None,
            "nextExDate": nxt.isoformat() if nxt else None}


def parse_splits(payload):
    """Most recent split: date + ratio 'num:den'."""
    if not isinstance(payload, list) or not payload:
        return None
    best = None; bd = None
    for r in payload:
        d = _d(r, "date")
        if d is None:
            continue
        if bd is None or d > bd:
            bd = d; best = r
    if best is None:
        return None
    num = _pick(best, "numerator", "splitTo", "to")
    den = _pick(best, "denominator", "splitFrom", "from")
    ratio = (str(num) + ":" + str(den)) if (num is not None and den is not None) else (_pick(best, "label", "split") or "?")
    return {"date": bd.isoformat(), "ratio": ratio}


def fetch_one(symbol, sess, key, timeout=20):
    out = {}
    for path, parse, kkey in (
        ("dividends?symbol=%s&limit=12" % symbol, parse_dividends, None),
        ("splits?symbol=%s&limit=5" % symbol, parse_splits, "lastSplit"),
    ):
        try:
            r = sess.get("%s/%s&apikey=%s" % (STABLE, path, key), timeout=timeout)
            if r.status_code == 200:
                v = parse(r.json())
                if v:
                    if kkey:
                        out[kkey] = v
                    else:
                        out.update(v)
        except Exception:
            pass
    return out or None


def build(symbols, key=None, sleep=0.04):
    import requests, time
    key = key or _key()
    if not key:
        sys.stderr.write("fmp_actions: no FMP key — skipped\n")
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
    ap.add_argument("--out", default="data/actions.json")
    a = ap.parse_args()
    names = _names(a.marketmap)
    if not names:
        sys.stderr.write("fmp_actions: no universe — skipped\n")
        return 0
    res = build(names)
    if not res:
        return 0
    res["_meta"] = {"names": len(res), "source": "FMP dividends + splits"}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    tmp = a.out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(res, f, separators=(",", ":"))
    os.replace(tmp, a.out)
    sys.stderr.write("fmp_actions: wrote %s for %d names\n" % (a.out, len(res) - 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
