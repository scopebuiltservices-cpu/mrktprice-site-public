#!/usr/bin/env python3
"""projledger.py — SERVER-SIDE, universe-wide projClose-vs-priceNow learning.

Runs a NO-LOOKAHEAD walk-forward over every name's committed price history: at each past session t it
forms a reproducible projClose forecast from data strictly BEFORE t, then reads the realized outcome at
t+H. Pooled across the whole universe per horizon, this yields an immediate Mincer-Zarnowitz recalibration
(projlearn_engine) shipped as projlearn.json so every browser starts already-calibrated (and the client
panel then personalizes from the user's own outcomes). Keyless: uses only the committed hist/. Verified.

Reproducible server forecast (documented; the browser cone is a richer member of the same family — the
(alpha,beta) recalibration it learns corrects systematic over/under-shoot, which transfers):
    muDaily(t) = shrink * mean( logret[t-LB .. t-1] )           # momentum, shrunk; uses only data < t
    predLR_H   = clamp( muDaily(t) * H , ±cap*sigma_t*sqrt(H) )  # horizon scaling, capped
    realLR_H   = ln( close[t+H] / close[t] )                     # realized (no lookahead: t+H > t)

Emits projlearn.json: {asof, horizons, byHorizon:{H:{alpha,beta,skill,theilU2,bias,mae,n,applied,wAlpha,wBeta,shrink}}, names, samples}.
CLI: python3 projledger.py --hist hist --marketmap marketmap.json --out projlearn.json"""
import argparse, json, math, os, sys, datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projlearn_engine as PL

HORIZONS = [5, 10, 21]


def _logrets(closes):
    r = []
    for i in range(1, len(closes)):
        if closes[i] > 0 and closes[i - 1] > 0:
            r.append(math.log(closes[i] / closes[i - 1]))
        else:
            r.append(0.0)
    return r


def walk_forward(closes, horizons=HORIZONS, lb=21, shrink=0.5, step=3, cap=2.0):
    """No-lookahead walk-forward. Returns {H: [(predLR, realLR), ...]}. Forecast at bar t uses returns
    strictly before t; realized uses close[t+H]. step subsamples to keep overlap modest."""
    out = {h: [] for h in horizons}
    r = _logrets(closes)                      # r[i] is the return INTO close[i+1]; r[0..t-2] are < t
    n = len(closes)
    maxh = max(horizons)
    t = lb + 1
    while t < n - maxh:
        # returns strictly before t: r indices [t-1-lb .. t-2]  (return into close[t-lb..t-1])
        win = r[max(0, t - 1 - lb):t - 1]
        if len(win) >= max(5, lb // 2):
            mu = shrink * (sum(win) / len(win))
            sd = math.sqrt(sum(x * x for x in win) / len(win)) or 1e-6
            for h in horizons:
                if t + h < n and closes[t] > 0 and closes[t + h] > 0:
                    pred = mu * h
                    lim = cap * sd * math.sqrt(h)
                    pred = max(-lim, min(lim, pred))
                    real = math.log(closes[t + h] / closes[t])
                    out[h].append((pred, real))
        t += step
    return out


def build(hist_dir, names, horizons=HORIZONS):
    pooled = {h: {"pred": [], "real": []} for h in horizons}
    used = 0
    for tk in names:
        p = os.path.join(hist_dir, "%s.json" % tk)
        if not os.path.exists(p):
            continue
        try:
            rows = (json.load(open(p)) or {}).get("rows") or []
            closes = [float(x[1]) for x in rows if x and len(x) > 1 and x[1] is not None]
        except Exception:
            continue
        if len(closes) < 80:
            continue
        wf = walk_forward(closes, horizons)
        any_h = False
        for h in horizons:
            for pr, rl in wf[h]:
                pooled[h]["pred"].append(pr); pooled[h]["real"].append(rl); any_h = True
        if any_h:
            used += 1
    by = {}
    total = 0
    for h in horizons:
        pr, rl = pooled[h]["pred"], pooled[h]["real"]
        by[str(h)] = PL.learn(pr, rl)
        total += len(pr)
    return {"asof": dt.date.today().isoformat(), "horizons": horizons, "byHorizon": by,
            "names": used, "samples": total, "schema": "projlearn/1"}


def _names(marketmap):
    try:
        mm = json.load(open(marketmap))
        return [n["t"] for n in mm.get("names", []) if n.get("t")]
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hist", default="hist")
    ap.add_argument("--marketmap", default="marketmap.json")
    ap.add_argument("--out", default="projlearn.json")
    a = ap.parse_args()
    names = _names(a.marketmap)
    if not names:
        sys.stderr.write("projledger: no universe (marketmap.json) — skipped\n")
        return 0
    rep = build(a.hist, names)
    tmp = a.out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rep, f, separators=(",", ":"))
    os.replace(tmp, a.out)
    sys.stderr.write("projledger: %d names, %d matured samples -> %s (beta@21=%s skill@21=%s)\n" % (
        rep["names"], rep["samples"], a.out, rep["byHorizon"].get("21", {}).get("beta"),
        rep["byHorizon"].get("21", {}).get("skill")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
