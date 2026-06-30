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
    """No-lookahead walk-forward. Returns {H: [(predLR, realLR, sigmaH), ...]}. Forecast at bar t uses ONLY
    closes[:t+1] (data through t); realized uses close[t+H]; sigmaH = decision-time cone band σ (sd·√H,
    computed from data < t, no lookahead) so the anti-deviation layer can studentize the matured residuals.
    The forecast is the cone-style OU/EMA-blend drift (proj_server) so the universe-wide recalibration learns
    the SAME forecast family the terminal shows. Falls back to the shrunk-momentum proxy if unavailable."""
    try:
        import proj_server as _PS
        _blend = _PS.blend_drift
    except Exception:
        _blend = None
    out = {h: [] for h in horizons}
    r = _logrets(closes)
    n = len(closes)
    maxh = max(horizons)
    t = lb + 1
    while t < n - maxh:
        win = r[max(0, t - 1 - lb):t - 1]
        if len(win) >= max(5, lb // 2):
            sd = math.sqrt(sum(x * x for x in win) / len(win)) or 1e-6
            mu = shrink * (sum(win) / len(win))      # proxy fallback
            hist = closes[:t + 1]                    # data known at decision time t (no lookahead)
            for h in horizons:
                if t + h < n and closes[t] > 0 and closes[t + h] > 0:
                    pred = _blend(hist, h) if _blend else max(-cap * sd * math.sqrt(h),
                                                              min(cap * sd * math.sqrt(h), mu * h))
                    real = math.log(closes[t + h] / closes[t])
                    out[h].append((pred, real, max(sd * math.sqrt(h), 1e-6)))   # decision-time cone σ
        t += step
    return out


def build(hist_dir, names, horizons=HORIZONS):
    try:
        import anti_deviation as AD
    except Exception:
        AD = None
    pooled = {h: {"pred": [], "real": [], "samp": []} for h in horizons}
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
            for pr, rl, sg in wf[h]:
                pooled[h]["pred"].append(pr); pooled[h]["real"].append(rl)
                pooled[h]["samp"].append((pr, rl, sg)); any_h = True
        if any_h:
            used += 1
    by = {}
    total = 0
    for h in horizons:
        pr, rl = pooled[h]["pred"], pooled[h]["real"]
        rec = PL.learn(pr, rl)
        # ANTI-DEVIATION: fit the matured-residual controllers (bias/scale/asymmetric-tail) on the SAME
        # no-lookahead walk-forward samples, so the published cone band is recalibrated for systematic
        # center/scale/shape error, gated by Geyer-ESS sufficiency + an out-of-sample interval-score benefit.
        if AD is not None:
            ad = AD.fit_from_samples(pooled[h]["samp"])
            rec["antiDeviation"] = {k: ad.get(k) for k in (
                "active", "nEff", "nRaw", "biasAdj", "scaleAdj", "qLower", "qUpper",
                "iscDelta", "coverageRaw", "coverageAdj", "target", "reason")}
        by[str(h)] = rec
        total += len(pr)
    return {"asof": dt.date.today().isoformat(), "horizons": horizons, "byHorizon": by,
            "names": used, "samples": total, "schema": "projlearn/2",
            "survivorshipBias": "universe = CURRENT constituents; delisted names absent -> pooled skill is an UPWARD-biased estimate"}


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
    os.replace(tmp, a.