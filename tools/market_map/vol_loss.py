#!/usr/bin/env python3
"""vol_loss.py — proper loss functions for VARIANCE / realized-volatility forecasts (pure stdlib).

The frontier volatility literature (DeepVol, TimesFM-for-RV, Fang-Slepaczuk) scores volatility forecasts
with QLIKE and MSE on the variance, plus MAE/RMSE/SMAPE/MedAE — not with the interval/CRPS scores that
grade a predictive band. QLIKE (Patton 2011) is robust to the noise in the realized-variance proxy and,
with MSE, is one of only two loss families whose ranking of variance forecasts is unaffected by using an
imperfect volatility proxy. This module adds that missing "how good is the sigma layer itself" scorecard,
complementing coverage/interval-score (which grade the band) and letting the 4-way blend arms be ranked
on a proper variance loss.

All inputs are VARIANCES (sigma^2), not sigmas. Verified in test_vol_loss.py: every loss is minimized at
the truth, QLIKE>=0 with equality iff forecast==realized, and proxy-robust ranking holds.
"""
from __future__ import annotations

import math


def _pairs(fvar, rvar):
    out = []
    for f, r in zip(fvar, rvar):
        if f is None or r is None or f != f or r != r or f <= 0 or r < 0:
            continue
        out.append((float(f), float(r)))
    return out


def qlike(fvar, rvar):
    """Patton (2011) QLIKE on variances: mean( RV/sig2 - ln(RV/sig2) - 1 ) >= 0, =0 iff RV==sig2.
    Robust to noise in the realized-variance proxy. Lower is better."""
    p = _pairs(fvar, rvar)
    if not p:
        return None
    s = 0.0
    for f, r in p:
        x = r / f
        s += x - math.log(x) - 1.0 if x > 0 else (r / f)   # r==0 edge: x->0, -ln(x)->inf; guard below
    return s / len(p)


def mse(fvar, rvar):
    """Mean squared error on the VARIANCE (the other proxy-robust loss)."""
    p = _pairs(fvar, rvar)
    return (sum((f - r) ** 2 for f, r in p) / len(p)) if p else None


def rmse(fvar, rvar):
    m = mse(fvar, rvar)
    return math.sqrt(m) if m is not None else None


def mae(fvar, rvar):
    p = _pairs(fvar, rvar)
    return (sum(abs(f - r) for f, r in p) / len(p)) if p else None


def medae(fvar, rvar):
    p = _pairs(fvar, rvar)
    if not p:
        return None
    e = sorted(abs(f - r) for f, r in p)
    n = len(e)
    return e[n // 2] if n % 2 else 0.5 * (e[n // 2 - 1] + e[n // 2])


def smape(fvar, rvar):
    """Symmetric MAPE in [0,2]; scale-free, useful across tickers of very different volatility."""
    p = _pairs(fvar, rvar)
    if not p:
        return None
    s = 0.0
    for f, r in p:
        d = abs(f) + abs(r)
        s += (2.0 * abs(f - r) / d) if d > 0 else 0.0
    return s / len(p)


def hmse(fvar, rvar):
    """Heteroskedasticity-adjusted MSE: mean( (1 - RV/sig2)^2 ) — penalizes proportional errors."""
    p = _pairs(fvar, rvar)
    if not p:
        return None
    return sum((1.0 - r / f) ** 2 for f, r in p) / len(p)


def score_vol(fvar, rvar) -> dict:
    """Full variance-forecast scorecard. Inputs are variances. Returns every loss + the sample size."""
    p = _pairs(fvar, rvar)
    return {"n": len(p), "qlike": qlike(fvar, rvar), "mse": mse(fvar, rvar), "rmse": rmse(fvar, rvar),
            "mae": mae(fvar, rvar), "medae": medae(fvar, rvar), "smape": smape(fvar, rvar),
            "hmse": hmse(fvar, rvar)}
