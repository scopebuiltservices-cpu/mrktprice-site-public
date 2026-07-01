#!/usr/bin/env python3
"""volarb_board.py — POST-BUILD enrichment: land the VolatilityArbiter's blended horizon sigma.

Assembles physical volatility components (HV_H, EWMA) plus a variance-ratio overlay from each name's
committed price history (hist/{T}.json rows [date, close, vol]) and writes:

    n["volArb"] = {sigma, sigma2, weights, reliability, components, vr, horizon, nObs, version}

This is the report's "Scale upgrade" landed NON-DESTRUCTIVELY: it adds a NEW field and does not touch
the existing fib_ref / lineage sigma that the golden tests depend on, so the arbiter's reliability-
weighted sigma becomes available to the UI and cone as an additional, auditable estimate. Keyless
(uses only committed history), idempotent, verified in test_volarb_board.py. Research only.
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics
import volatility_arbiter as VA


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def volarb_for(closes, horizon=21):
    """Pure: a list of closes -> the n['volArb'] block (or None if too little history). Network-free."""
    c = [float(x) for x in (closes or []) if x is not None and float(x) > 0]
    if len(c) < 40:
        return None
    lr = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
    n = len(lr)
    sd1 = metrics.stdev(lr)
    if not sd1 or sd1 != sd1 or sd1 <= 0:
        return None
    hsig = sd1 * math.sqrt(horizon)                                  # HV: per-period sd scaled to horizon
    comps = [VA.component("hv", hsig, reliability=_clip((n - 30) / 120.0, 0.2, 0.95))]
    ew1 = metrics.ewma_vol(lr, lam=0.94, annualize=1)                # per-period EWMA (RiskMetrics)
    if ew1 == ew1 and ew1 and ew1 > 0:
        comps.append(VA.component("ewma", ew1 * math.sqrt(horizon), reliability=_clip((n - 30) / 90.0, 0.2, 0.9)))
    vr = metrics.variance_ratio(c, q=5)                              # Lo-MacKinlay VR on closes
    lam = VA.vr_lambda(vr, n) if vr is not None else 0.0
    svr = sd1 * math.sqrt(horizon * max(vr, 1e-6)) if vr is not None else None   # VR-implied horizon sigma
    try:
        r = VA.blend(comps, sigma_vr=svr, vr_reliability=lam)
    except ValueError:
        return None
    r["sigma"] = round(r["sigma"], 8)
    r["sigma2"] = round(r["sigma2"], 10)
    r["reliability"] = round(r["reliability"], 4)
    r["components"] = {k: round(v, 8) for k, v in r["components"].items()}
    r["horizon"] = horizon
    r["vr"] = (round(vr, 4) if vr is not None else None)
    r["nObs"] = n
    return r


def _load_hist(hist_dir, ticker):
    p = os.path.join(hist_dir, ticker + ".json")
    if not os.path.exists(p):
        return None
    try:
        rows = json.load(open(p))
        return [r[1] for r in rows if isinstance(r, (list, tuple)) and len(r) > 1 and r[1] is not None]
    except Exception:
        return None


def _is_equity(n):
    idx = n.get("idx") or []
    return bool(n.get("t")) and "FACTOR" not in idx and not n.get("etf")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--hist", default="hist")
    ap.add_argument("--horizon", type=int, default=21)
    a = ap.parse_args()
    mm = json.load(open(a.map))
    names = mm.get("names") or mm.get("nodes") or []
    done = 0
    for n in names:
        if not _is_equity(n):
            continue
        closes = _load_hist(a.hist, n.get("t", ""))
        if not closes:
            continue
        block = volarb_for(closes, horizon=a.horizon)
        if block:
            n["volArb"] = block; done += 1
    tmp = a.map + ".tmp"
    json.dump(mm, open(tmp, "w"))
    os.replace(tmp, a.map)
    sys.stderr.write("volarb_board: enriched %d names with blended sigma -> %s\n" % (done, a.map))


if __name__ == "__main__":
    main()
