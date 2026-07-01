"""tail_stability.py — conformal tail-quantile stability + sample-size panel (pure stdlib).

The Validation Report requires a "tail-noise and sample-size panel": for each horizon and each tail,
report the number of matured calibration residuals, the effective sample size after overlap adjustment,
the tail quantile rank used, and — crucially — the SENSITIVITY of the tail quantile to dropping the most
recent 5% and 10% of the calibration window. If a tail quantile moves violently when a few recent
observations leave the window, the band is not production-stable even if headline coverage looks fine.

Inputs: a horizon's studentized calibration residuals `resid` (time-ordered oldest->newest), the nominal
miss rate `alpha` (band is [Q_alpha, Q_{1-alpha}] -> 1-2*alpha central... here two one-sided tails at
alpha each for a (1-2alpha) interval; we report the lower tail Q_alpha and upper tail Q_{1-alpha}), and
the label-overlap `H` (consecutive H-step labels overlap, so effective N ~ N/H).

Outputs per tail: quantile, integer rank, sensitivity to dropping the newest 5%/10%, and a stable flag.
Verified in test_tail_stability.py against a planted unstable tail (recent outlier) vs a stable one.
"""
from __future__ import annotations

import math


def quantile_sorted(sorted_vals, p: float):
    """Type-7 (linear interpolation) quantile of an already-sorted list. p in [0,1]."""
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return float(sorted_vals[0])
    h = (n - 1) * p
    lo = int(math.floor(h))
    hi = min(lo + 1, n - 1)
    frac = h - lo
    return float(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac)


def quantile_rank(n: int, p: float) -> int:
    """1-based order-statistic rank nearest the p-quantile (the residual that sets the tail bound)."""
    if n <= 0:
        return 0
    return max(1, min(n, int(math.ceil(p * (n + 1)))))


def _q(vals, p):
    return quantile_sorted(sorted(vals), p)


def effective_n(n: int, overlap: int) -> float:
    """Overlap-adjusted effective sample size: H-step labels formed on consecutive issue times overlap
    almost fully, so independent information ~ n / H. Conservative, matches the report's intent."""
    ov = max(1, int(overlap))
    return round(n / ov, 2)


def tail_panel(resid, alpha: float = 0.05, overlap: int = 1,
               drop_fracs=(0.05, 0.10), stable_tol: float = 0.25) -> dict:
    """Build the tail-noise / sample-size panel for one horizon.

    stable_tol is the max tolerated |Δquantile| (in studentized-residual units) when the newest 5%/10%
    of the window is dropped; a larger move flags the tail as unstable (band not production-stable)."""
    r = [float(x) for x in resid if x == x]        # drop NaN
    n = len(r)
    full = {"n": n, "nEff": effective_n(n, overlap), "overlap": max(1, int(overlap)), "alpha": alpha}
    if n < 5:
        full.update({"stable": False, "reason": "insufficient residuals (<5)"})
        return full

    tails = {"lower": alpha, "upper": 1.0 - alpha}
    out_tails = {}
    worst_stable = True
    for name, p in tails.items():
        q_full = _q(r, p)
        rank = quantile_rank(n, p)
        sens = {}
        tail_stable = True
        for f in drop_fracs:
            keep = n - int(math.ceil(f * n))       # drop the NEWEST f-fraction (end of the time-ordered list)
            keep = max(5, keep)
            q_drop = _q(r[:keep], p)
            delta = None if (q_full is None or q_drop is None) else round(q_drop - q_full, 4)
            unstable = (delta is not None and abs(delta) > stable_tol)
            sens[f"drop{int(f*100)}pct"] = {"kept": keep, "quantile": (None if q_drop is None else round(q_drop, 4)),
                                            "delta": delta, "unstable": bool(unstable)}
            if unstable:
                tail_stable = False
        out_tails[name] = {"quantile": round(q_full, 4), "rank": rank, "sensitivity": sens, "stable": tail_stable}
        worst_stable = worst_stable and tail_stable

    full["tails"] = out_tails
    full["stable"] = bool(worst_stable)
    full["stableTol"] = stable_tol
    if not worst_stable:
        full["reason"] = "tail quantile moves > tol when newest 5%/10% dropped — band not production-stable"
    return full
