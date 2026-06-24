#!/usr/bin/env python3
"""Close the Black-Scholes feedback loop: for each *matured* valuation snapshot in
bs_history.jsonl (older than its own option horizon), look up what the underlying
actually did, attach the realized forward return as an outcome, then print/persist
a calibration summary the mrktprice equation can learn from.

Idempotent: a snapshot that already has an outcome is skipped. Needs yfinance for the
realized price; snapshots whose ticker can't be priced are left for a later run.

Run:  python calibrate_outcomes.py            (uses BS_HISTORY or data/bs_history.jsonl)
CI:   weekly, after the nightly snapshot, with the history file restored from cache."""
import os, sys, json, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bs_record as rec

def _parse_ts(ts):
    try: return datetime.datetime.fromisoformat(ts.replace("Z", ""))
    except Exception: return None

def _realized_fwd_return(ticker, start_dt, spot, days):
    """(price ~days after start)/spot - 1, using daily closes. None if unavailable."""
    try:
        import yfinance as yf
    except Exception:
        return None, None
    try:
        end = start_dt + datetime.timedelta(days=int(days) + 7)
        h = yf.download(ticker, start=start_dt.date().isoformat(),
                        end=end.date().isoformat(), interval="1d", progress=False)
        if h is None or not len(h): return None, None
        closes = [float(x) for x in h["Close"].dropna().tolist()]
        if len(closes) < 2 or not spot: return None, None
        target = closes[min(int(days), len(closes) - 1)]
        fwd = target / float(spot) - 1.0
        # realized vol over the life (annualized, close-to-close)
        import math
        rets = [math.log(closes[i] / closes[i-1]) for i in range(1, len(closes)) if closes[i-1] > 0]
        rv = (sum(r*r for r in rets) / len(rets)) ** 0.5 * (252 ** 0.5) if rets else None
        return round(fwd, 5), (round(rv, 4) if rv else None)
    except Exception:
        return None, None

def main():
    path = os.environ.get("BS_HISTORY", rec.DEFAULT)
    rows = rec.load(path)
    snaps = [r for r in rows if r.get("kind") == "snapshot" and r.get("summary")]
    done = {o.get("refTs") for o in rows if o.get("kind") == "outcome"}
    now = datetime.datetime.utcnow()
    attached = 0; pending = 0; skipped_demo = 0
    for s in snaps:
        ts = s.get("ts"); 
        if not ts or ts in done: continue
        summ = s["summary"]; tk = s.get("ticker"); spot = summ.get("spot"); days = summ.get("days") or 30
        if not tk or tk.upper() in ("DEMO", "TEST"):
            skipped_demo += 1; continue
        st = _parse_ts(ts)
        if not st: continue
        if (now - st).days < int(days):       # not matured yet — wait for a later run
            pending += 1; continue
        fwd, rv = _realized_fwd_return(tk, st, spot, days)
        if fwd is None:
            pending += 1; continue
        rec.attach_outcome(tk, ts, {"fwdRet": fwd, "realizedVolPct": (rv*100 if rv else None),
                                    "horizonDays": int(days)}, path=path)
        attached += 1

    summ = rec.calibration_summary(path)
    summ["maturedAttachedThisRun"] = attached
    summ["pendingNotYetMatured"] = pending
    summ["skippedDemo"] = skipped_demo
    summ["generatedUtc"] = now.isoformat() + "Z"
    out = os.path.join(os.path.dirname(path), "calibration_summary.json")
    try:
        with open(out, "w") as f: json.dump(summ, f, indent=2)
    except Exception: pass
    print(json.dumps(summ, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
