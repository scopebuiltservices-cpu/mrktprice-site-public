#!/usr/bin/env python3
"""
drift_calib.py — learn the projection-cone drift SHRINK from realized outcomes (verified, pure-stdlib).

The cone's central path = spot + shrink*(model_target - spot); `shrink` was a fixed 0.60. This LEARNS it:
across the universe's price history, regress the realized H-day forward log-return on the model's reversion
signal (gap to a moving fair value). The OLS-through-origin slope is the fraction of the predicted move that
actually realizes = the empirically-correct shrink. Small samples shrink toward the 0.60 literature prior so
the value degrades gracefully until history accrues. Unit-tested on planted structure.
"""
import math
__all__ = ["ols_slope", "optimal_shrink", "gap_pairs", "calibrate_universe"]


def ols_slope(x, y):
    """Slope through the origin Sxy/Sxx (the multiplicative shrink on the predicted drift). NaN-safe."""
    sxx = 0.0; sxy = 0.0; n = 0
    for a, b in zip(x, y):
        if a is None or b is None or a != a or b != b:
            continue
        sxx += a * a; sxy += a * b; n += 1
    if n < 2 or sxx <= 0:
        return float("nan")
    return sxy / sxx


def optimal_shrink(pred, real, prior=0.6, prior_n=20.0, lo=0.0, hi=1.0):
    """Empirically-optimal shrink: OLS slope of realized-on-predicted, empirical-Bayes blended toward
    `prior` by sample size, clamped to [lo,hi]. Returns {'shrink','n','raw'}."""
    xs = []; ys = []
    for a, b in zip(pred, real):
        if a is None or b is None or a != a or b != b:
            continue
        xs.append(a); ys.append(b)
    n = len(xs); raw = ols_slope(xs, ys)
    if n < 2 or raw != raw:
        return {"shrink": prior, "n": n, "raw": float("nan")}
    cal = (n * raw + prior_n * prior) / (n + prior_n)
    return {"shrink": max(lo, min(hi, cal)), "n": n, "raw": raw}


def gap_pairs(closes, H=20, win=20):
    """Walk-forward (gap-to-fair-value, realized H-day fwd log-return) pairs from one name's closes.
    gap = log(SMA(win)/price) (>0 => below fair value => expect up-reversion); real = log(p[t+H]/p[t])."""
    c = [x for x in closes if x is not None and x == x and x > 0]
    out = []
    if len(c) < win + H + 1:
        return out
    for t in range(win - 1, len(c) - H):
        sma = sum(c[t - win + 1:t + 1]) / win
        if sma <= 0 or c[t] <= 0:
            continue
        out.append((math.log(sma / c[t]), math.log(c[t + H] / c[t])))
    return out


def calibrate_universe(closes_by_name, H=20, win=20, prior=0.6, prior_n=40.0):
    """Pool (gap, realized) pairs across all names and learn the universe drift shrink."""
    pred = []; real = []
    for closes in (closes_by_name or []):
        for g, r in gap_pairs(closes, H, win):
            pred.append(g); real.append(r)
    res = optimal_shrink(pred, real, prior=prior, prior_n=prior_n)
    res["H"] = H; res["win"] = win
    return res
