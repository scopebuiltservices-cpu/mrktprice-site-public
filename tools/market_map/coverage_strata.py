"""coverage_strata.py — stratified interval-coverage diagnostics (pure stdlib).

The Validation Report ("Replacing Square-Root-Time Volatility Scaling and Gaussian Sigma Bands")
requires that realized conformal-band coverage be judged NOT only marginally but stratified by
volatility regime, time of day, event regime, and sign of move — because a band can hit 90% overall
while systematically under-covering the down-tail or the market open. Marginal coverage hides exactly
the failures that hurt in risk terms.

Input: a list of matured forecast records, each a dict with
    covered   : bool   — did the realized outcome fall inside [L, U] for that forecast?
    horizon   : int    — forecast horizon H (bars/days)
    volRegime : str    — "low" | "mid" | "high" (or any label; caller derives from sigma percentile)
    tod       : str    — time-of-day bucket, e.g. "open" | "mid" | "close" (intraday); optional
    event     : str    — "calm" | "event" (near earnings/macro); optional
    sign      : str    — "up" | "down" (sign of the realized move); optional
Output: per-dimension, per-level coverage with a Wilson CI and a miscalibration flag (nominal outside CI).

No numpy; every number reproducible. Verified against planted mis-coverage in test_coverage_strata.py.
"""
from __future__ import annotations

import math

Z_95 = 1.959963984540054   # two-sided 95% normal quantile for the Wilson interval


def wilson_interval(k: int, n: int, z: float = Z_95):
    """Wilson score interval for a binomial proportion k/n (robust at small n / extreme p). Returns
    (phat, lo, hi). n==0 -> (None, 0.0, 1.0)."""
    if n <= 0:
        return None, 0.0, 1.0
    phat = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (phat + z2 / (2 * n)) / denom
    half = (z * math.sqrt(phat * (1 - phat) / n + z2 / (4 * n * n))) / denom
    return phat, max(0.0, center - half), min(1.0, center + half)


def _cell(records, nominal: float, z: float):
    n = len(records)
    k = sum(1 for r in records if r.get("covered"))
    phat, lo, hi = wilson_interval(k, n, z)
    # miscalibrated when the nominal coverage target lies OUTSIDE the Wilson CI (i.e. the deviation is
    # statistically resolved, not just noise). direction: "under" if we cover too little, "over" if too much.
    mis = (n > 0) and (nominal < lo or nominal > hi)
    direction = None
    if mis:
        direction = "under" if (phat is not None and phat < nominal) else "over"
    return {"n": n, "k": k, "coverage": (None if phat is None else round(phat, 4)),
            "wilsonLo": round(lo, 4), "wilsonHi": round(hi, 4),
            "miscalibrated": bool(mis), "direction": direction}


def stratified_coverage(records, nominal: float = 0.90, dims=("volRegime", "tod", "event", "sign"),
                        min_n: int = 20, z: float = Z_95) -> dict:
    """Stratify coverage by each dimension in `dims` (skipping records missing that key) and by horizon.
    Cells with fewer than `min_n` matured records are reported but marked lowN (never flagged
    miscalibrated on thin data). Returns {marginal, byHorizon, byDim:{dim:{level:cell}}, flags:[...]}."""
    out = {"nominal": nominal, "nTotal": len(records)}
    out["marginal"] = _cell(records, nominal, z)

    byh = {}
    for r in records:
        byh.setdefault(r.get("horizon"), []).append(r)
    out["byHorizon"] = {str(h): _cell(v, nominal, z) for h, v in sorted(byh.items(), key=lambda kv: (kv[0] is None, kv[0]))}

    bydim = {}
    flags = []
    for dim in dims:
        levels = {}
        grouped = {}
        for r in records:
            if dim in r and r[dim] is not None:
                grouped.setdefault(r[dim], []).append(r)
        for lvl, recs in grouped.items():
            c = _cell(recs, nominal, z)
            c["lowN"] = c["n"] < min_n
            if c["lowN"]:
                c["miscalibrated"] = False       # do not flag on thin data
                c["direction"] = None
            levels[str(lvl)] = c
            if c["miscalibrated"]:
                flags.append({"dim": dim, "level": str(lvl), "coverage": c["coverage"],
                              "direction": c["direction"], "n": c["n"]})
        if levels:
            bydim[dim] = levels
    out["byDim"] = bydim
    out["flags"] = flags
    out["ok"] = (len(flags) == 0)
    return out
