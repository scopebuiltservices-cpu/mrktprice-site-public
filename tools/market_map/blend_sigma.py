#!/usr/bin/env python3
"""blend_sigma.py — 4-way convex blended volatility scale (pure stdlib).

The Validation Report ("Replacing Square-Root-Time Volatility Scaling and Gaussian Sigma Bands")
recommends replacing a single volatility estimate with a convex BLEND of complementary estimators:

    sigma_{t,H}^2 = w_H·sigma_HV^2 + u_H·sigma_EWMA^2 + v_H·sigma_GARCH^2 + m_H·sigma_RV^2 ,
    weights nonnegative and summing to 1, re-estimated leakage-free against MATURED realized variance.

Each estimator answers a different question: HV = horizon-aligned backward look; EWMA = fast reaction to
recent shocks (RiskMetrics); GARCH = conditional-variance clustering; RV = intraday-informed realized
variance (fed in when available). The optimal convex combiner is the diagonal Bates-Granger rule
(w_i proportional to 1/MSE_i vs matured realized variance) — always nonnegative, sums to 1, and provably
dominates any single arm when errors are imperfectly correlated.

REUSES: metrics (ewma_vol/stdev/variance_ratio/parkinson_vol) and lineage.garch11_fit (real GARCH QMLE).
Verified in test_blend_sigma.py against planted clustering + a planted best-arm.
"""
from __future__ import annotations

import math

from metrics import _clean, ewma_vol, stdev

COMPONENTS = ("hv", "ewma", "garch", "rv")


def _garch_var(rets):
    """1-step conditional variance from lineage.garch11_fit (lazy import to avoid a heavy top-level dep)."""
    try:
        from lineage import garch11_fit, garch11_nstep_var
        fit = garch11_fit(rets)
        if not fit:
            return None
        v = garch11_nstep_var(fit, rets, 1)
        return v if (v is not None and v == v and v > 0) else fit.get("uncondVar")
    except Exception:
        return None


def component_variances(rets, window: int = 20, lam: float = 0.94, use_garch: bool = True,
                        rv_var=None, highs=None, lows=None) -> dict:
    """Daily VARIANCE from each available estimator. Missing/degenerate arms are omitted (not zero-filled).
    rv_var: a realized daily variance fed from intraday (preferred); else Parkinson from highs/lows if given."""
    r = _clean(rets)
    out = {}
    if len(r) >= 2:
        w = r[-window:] if len(r) >= window else r
        s = stdev(w)
        if s == s and s > 0:
            out["hv"] = s * s
        ew = ewma_vol(r, lam=lam, annualize=0)
        if ew == ew and ew > 0:
            out["ewma"] = ew * ew
        if use_garch:
            gv = _garch_var(r)
            if gv is not None and gv == gv and gv > 0:
                out["garch"] = gv
    if rv_var is not None and rv_var == rv_var and rv_var > 0:
        out["rv"] = float(rv_var)
    elif highs is not None and lows is not None:
        try:
            from metrics import parkinson_vol
            pv = parkinson_vol(highs, lows, n=min(window, len(highs)))
            if pv is not None and pv == pv and pv > 0:
                out["rv"] = pv * pv
        except Exception:
            pass
    return out


def bates_granger_weights(mse_by_comp: dict, eps: float = 1e-12) -> dict:
    """Diagonal Bates-Granger optimal convex weights: w_i ∝ 1/MSE_i, normalized. Nonneg, sums to 1.
    Components with non-finite / nonpositive MSE are dropped. Empty -> {}."""
    inv = {}
    for c, m in mse_by_comp.items():
        if m is not None and m == m and m > eps:
            inv[c] = 1.0 / m
    z = sum(inv.values())
    if z <= 0:
        return {}
    return {c: v / z for c, v in inv.items()}


def weights_from_history(history, comps=COMPONENTS) -> dict:
    """Leakage-free weight estimate from MATURED (forecastVar_by_comp, realizedVar) pairs.
    history: list of (dict_of_component_variance_forecasts, realized_variance). Returns convex weights."""
    sq_err = {c: [] for c in comps}
    for fc, realized in history:
        if realized is None or realized != realized:
            continue
        for c in comps:
            f = fc.get(c)
            if f is not None and f == f:
                sq_err[c].append((f - realized) ** 2)
    mse = {c: (sum(v) / len(v)) for c, v in sq_err.items() if v}
    return bates_granger_weights(mse)


def blend_variance(comps: dict, weights: dict | None = None) -> float:
    """Convex blend of available component variances. weights None -> equal over available comps.
    Weights are always renormalized over the components actually present (so a missing arm never
    silently shrinks the total)."""
    keys = [c for c in comps if comps[c] is not None and comps[c] == comps[c] and comps[c] > 0]
    if not keys:
        return float("nan")
    if weights:
        w = {c: max(0.0, weights.get(c, 0.0)) for c in keys}
        z = sum(w.values())
        if z <= 0:
            w = {c: 1.0 / len(keys) for c in keys}
        else:
            w = {c: v / z for c, v in w.items()}
    else:
        w = {c: 1.0 / len(keys) for c in keys}
    return sum(w[c] * comps[c] for c in keys)


def blended_sigma_daily4(rets, weights: dict | None = None, gamma: float = 0.0,
                         window: int = 20, lam: float = 0.94, use_garch: bool = True,
                         rv_var=None, highs=None, lows=None):
    """Daily sigma from the 4-way convex variance blend, with a strictly-positive scale floor gamma
    (the studentization floor from the report). Returns (sigma, detail) where detail carries the
    component variances and the weights actually used — for the reporting pack."""
    comps = component_variances(rets, window=window, lam=lam, use_garch=use_garch,
                                rv_var=rv_var, highs=highs, lows=lows)
    bv = blend_variance(comps, weights)
    sig = math.sqrt(bv) if (bv == bv and bv > 0) else float("nan")
    if sig == sig:
        sig = max(sig, gamma)
    keys = [c for c in comps if comps[c] and comps[c] > 0]
    used = weights if weights else {c: 1.0 / len(keys) for c in keys} if keys else {}
    detail = {"components": comps, "weights": used, "blendVar": bv, "gamma": gamma, "arms": keys}
    return sig, detail
