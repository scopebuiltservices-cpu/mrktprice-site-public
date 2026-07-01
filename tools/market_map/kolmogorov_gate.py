#!/usr/bin/env python3
"""kolmogorov_gate.py — the Kolmogorov-Smirnov advanced DUAL GATE (pure stdlib).

A forward path/cone forecast is only admissible when two conditions hold together:
  1. SUFFICIENCY  — enough effective observations in both the reference and current windows.
  2. STATIONARITY — the current return distribution has NOT drifted from the reference distribution,
     judged by the two-sample Kolmogorov-Smirnov test (D = sup|F_ref - F_cur|, asymptotic Kolmogorov
     p-value with the Stephens small-sample correction). High p ⇒ fail to reject "same law" ⇒ stationary.

Both must pass (the DUAL gate). When the gate FAILS, the market has regime-shifted relative to the
window the cone was calibrated on, so the path odds / MFE-MAE / touch probabilities are unreliable and
should be shown flagged, not as fact. This is the on/off validity layer over path_probability.

Verified in test_kolmogorov_gate.py: identical windows ⇒ D≈0,p≈1,pass; a planted vol-jump or mean-shift
⇒ low p, stationarity fails; tiny windows ⇒ sufficiency fails.
"""
from __future__ import annotations

import math


def _ecdf_at(sorted_vals, x):
    # fraction of sorted_vals <= x  (binary search)
    lo, hi = 0, len(sorted_vals)
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_vals[mid] <= x:
            lo = mid + 1
        else:
            hi = mid
    return lo / len(sorted_vals)


def ks_two_sample(a, b):
    """Two-sample KS distance D = sup|F_a - F_b| and its asymptotic p-value (Stephens-corrected).
    Returns (D, p, n_eff). Empty input -> (0.0, 1.0, 0)."""
    a = sorted(float(x) for x in a if x == x)
    b = sorted(float(x) for x in b if x == x)
    na, nb = len(a), len(b)
    if na == 0 or nb == 0:
        return 0.0, 1.0, 0
    # D over the union of jump points
    D = 0.0
    for x in a:
        D = max(D, abs(_ecdf_at(a, x) - _ecdf_at(b, x)))
    for x in b:
        D = max(D, abs(_ecdf_at(a, x) - _ecdf_at(b, x)))
    ne = na * nb / (na + nb)
    sn = math.sqrt(ne)
    lam = (sn + 0.12 + 0.11 / sn) * D          # Stephens correction
    return D, _probks(lam), ne


def _probks(alam):
    """Kolmogorov Q(lambda) = P(sqrt(n)*D > lambda) — Numerical-Recipes series. Returns a p-value in [0,1]."""
    if alam <= 0:
        return 1.0
    a2 = -2.0 * alam * alam
    fac, s, termbf = 2.0, 0.0, 0.0
    for j in range(1, 101):
        term = fac * math.exp(a2 * j * j)
        s += term
        if abs(term) <= 1e-3 * termbf or abs(term) <= 1e-8 * s:
            return max(0.0, min(1.0, s))
        fac = -fac
        termbf = abs(term)
    return 1.0


def dual_gate(returns, ref_window: int = 120, cur_window: int = 60, alpha: float = 0.05,
              min_n: int = 30) -> dict:
    """Split `returns` (chronological) into a reference window (older) and current window (most recent),
    then apply the dual gate. Returns a UI-ready verdict dict."""
    r = [float(x) for x in returns if x == x]
    n = len(r)
    cur = r[-cur_window:] if n >= cur_window else r
    ref = r[-(cur_window + ref_window):-cur_window] if n >= cur_window + ref_window else r[:-len(cur)] if len(cur) < n else []
    nref, ncur = len(ref), len(cur)

    sufficient = (nref >= min_n and ncur >= min_n)
    D, p, ne = (ks_two_sample(ref, cur) if sufficient else (0.0, 1.0, 0.0))
    stationary = sufficient and (p >= alpha)
    passed = bool(sufficient and stationary)

    if not sufficient:
        reason = "insufficient history (need %d in each window; have ref=%d cur=%d)" % (min_n, nref, ncur)
    elif not stationary:
        reason = "regime shift: current return law differs from reference (KS p=%.3f < %.2f)" % (p, alpha)
    else:
        reason = "stationary vs reference (KS p=%.3f)" % p

    # graded confidence in [0,1]: stationarity p scaled by a sufficiency ramp
    suff_ramp = max(0.0, min(1.0, (min(nref, ncur) - min_n) / max(1, min_n))) if sufficient else 0.0
    grade = round((p if stationary else 0.0) * (0.5 + 0.5 * suff_ramp), 4)

    return {"passed": passed, "sufficient": bool(sufficient), "stationary": bool(stationary),
            "ksD": round(D, 4), "ksP": round(p, 4), "nRef": nref, "nCur": ncur,
            "nEff": round(ne, 1), "alpha": alpha, "grade": grade, "reason": reason,
            "status": ("admissible" if passed else ("regime-shifted" if sufficient else "thin"))}
