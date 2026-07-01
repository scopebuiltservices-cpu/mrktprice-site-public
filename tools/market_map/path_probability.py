#!/usr/bin/env python3
"""path_probability.py — path-dependent forecast probabilities for the cone (pure stdlib).

The cone reports flag path-dependence as the biggest missing piece: a terminal cone "is blind to how it
gets there." lineage.py already has the Brownian-bridge barrier correction and reflection first-passage;
this module adds the rest of the path suite the Institutional Blueprint lists — expected MAXIMUM FAVORABLE
and MAXIMUM ADVERSE EXCURSION, the running-max/min distribution and quantiles, and P(end above a level |
first touched a barrier) — with exact closed forms for the driftless case and a drift-capable Monte-Carlo
that doubles as the verification oracle.

All quantities are in LOG-RETURN space relative to S0 (barrier b = ln(B/S0), level k = ln(K/S0)); the
total-horizon scale is s = sigma_daily * sqrt(T) and drift m = mu_daily * T. Convert to price with
price_to_return()/return_to_price(). Every closed form is checked against Monte-Carlo in test_path_probability.py.
"""
from __future__ import annotations

import math
import random

SQRT2 = math.sqrt(2.0)
SQRT_2_OVER_PI = math.sqrt(2.0 / math.pi)


def _ncdf(x):
    return 0.5 * math.erfc(-x / SQRT2)


def _npdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _nppf(p):
    if p <= 0:
        return -math.inf
    if p >= 1:
        return math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def price_to_return(price, s0):
    return math.log(price / s0)


def return_to_price(r, s0):
    return s0 * math.exp(r)


# ---- first-passage (running max/min crossing a barrier) --------------------------------------
def touch_up(b, s, m=0.0):
    """P( max_{t<=T} X_t >= b ) for arithmetic BM X ~ (drift m, scale s), b > 0. Driftless -> 2*Phi(-b/s)."""
    if s <= 0:
        return 1.0 if b <= 0 else 0.0
    if b <= 0:
        return 1.0
    return min(1.0, _ncdf((m - b) / s) + math.exp(2.0 * m * b / (s * s)) * _ncdf((-b - m) / s))


def touch_down(b, s, m=0.0):
    """P( min_{t<=T} X_t <= b ) for b < 0 (barrier below start). By symmetry: touch_up(-b, s, -m)."""
    return touch_up(-b, s, -m)


# ---- running-max / -min distribution + quantiles + expected excursions -----------------------
def running_max_cdf_ge(b, s, m=0.0):
    """P(M >= b) where M = running max (b can be any real; <=0 -> 1)."""
    return touch_up(b, s, m) if b > 0 else 1.0


def running_max_quantile(p, s, m=0.0):
    """p-quantile of the running max M. Driftless closed form: s * Phi^{-1}((1+p)/2). Drift: invert the CDF."""
    if s <= 0:
        return max(0.0, m)
    if abs(m) < 1e-15:
        return s * _nppf((1.0 + p) / 2.0)
    lo, hi = 0.0, m + 12.0 * s
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if (1.0 - running_max_cdf_ge(mid, s, m)) < p:   # P(M < mid)
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def expected_max_favorable(s, m=0.0):
    """E[ running MAX ] over [0,T] — Maximum Favorable Excursion. Driftless: s*sqrt(2/pi)."""
    if s <= 0:
        return max(0.0, m)
    if abs(m) < 1e-15:
        return s * SQRT_2_OVER_PI
    # E[M] = integral_0^inf P(M>=b) db  (numerical Simpson; integrand decays like a Gaussian tail)
    hi = max(0.0, m) + 12.0 * s
    n = 2000
    h = hi / n
    tot = running_max_cdf_ge(0.0, s, m) + running_max_cdf_ge(hi, s, m)
    for i in range(1, n):
        tot += (4 if i % 2 else 2) * running_max_cdf_ge(i * h, s, m)
    return tot * h / 3.0


def expected_max_adverse(s, m=0.0):
    """E[ |running MIN| ] over [0,T] — Maximum Adverse Excursion (positive magnitude). By symmetry of the
    running min: min X (drift m) =_d -max(-X) (drift -m), so MAE = expected_max_favorable(s, -m)."""
    return expected_max_favorable(s, -m)


# ---- conditional: P(end above level K | first touched barrier B) -----------------------------
def prob_end_above_given_touch_up(b, k, s, m=0.0, mc=None):
    """P( X_T >= k | max_{t<=T} X_t >= b ), b > 0. Exact reflection for m==0; MC for drift (mc = n paths)."""
    if s <= 0:
        return 1.0 if (m >= b and m >= k) else 0.0
    denom = touch_up(b, s, m)
    if denom <= 0:
        return 0.0
    if abs(m) < 1e-15:
        # joint P(M>=b, X_T>=k):  k<=b -> 2*Phi(-b/s) - Phi(-(2b-k)/s);  k>b -> Phi(-k/s)
        joint = (2.0 * _ncdf(-b / s) - _ncdf(-(2.0 * b - k) / s)) if k <= b else _ncdf(-k / s)
        return max(0.0, min(1.0, joint / denom))
    n = int(mc or 40000)
    hit = end_above_and_hit = 0
    for _ in range(n):
        x, mx = 0.0, 0.0
        steps = 64
        dt = 1.0 / steps
        sd = s * math.sqrt(dt)
        md = m * dt
        for _ in range(steps):
            x += md + sd * random.gauss(0, 1)
            if x > mx:
                mx = x
        if mx >= b:
            hit += 1
            if x >= k:
                end_above_and_hit += 1
    return (end_above_and_hit / hit) if hit else 0.0


def path_report(s0, sigma_daily, T, barrier_up=None, barrier_dn=None, level=None, drift_daily=0.0) -> dict:
    """Assemble the path-dependent panel for one horizon in PRICE space. Returns MFE/MAE (as price moves),
    touch odds to the given barriers, and P(end above level | touched the up barrier)."""
    s = sigma_daily * math.sqrt(T)
    m = drift_daily * T
    out = {"T": T, "s": round(s, 6), "m": round(m, 6),
           "mfeRet": round(expected_max_favorable(s, m), 6),
           "maeRet": round(expected_max_adverse(s, m), 6)}
    out["mfePrice"] = round(return_to_price(out["mfeRet"], s0), 4)
    out["maePrice"] = round(return_to_price(-out["maeRet"], s0), 4)
    if barrier_up is not None and barrier_up > s0:
        out["touchUp"] = round(touch_up(price_to_return(barrier_up, s0), s, m), 4)
    if barrier_dn is not None and 0 < barrier_dn < s0:
        out["touchDn"] = round(touch_down(price_to_return(barrier_dn, s0), s, m), 4)
    if barrier_up is not None and level is not None and barrier_up > s0:
        out["pEndAboveGivenTouchUp"] = round(
            prob_end_above_given_touch_up(price_to_return(barrier_up, s0), price_to_return(level, s0), s, m), 4)
    return out
