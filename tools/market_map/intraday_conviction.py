#!/usr/bin/env python3
"""
intraday_conviction.py — explicit intraday conviction-flip gate with PUBLISHED cutoffs (stdlib).

Per the deep-research spec, the intraday board should not merely display 15-minute information; it should
change conviction state only when evidence crosses a predeclared threshold set, and it must PUBLISH both
the current observed value and the active cutoff for every metric so an operator never has to guess why
conviction flipped. This turns a dashboard into an audit trail.

Long-side flip (short-side is the sign-reversed mirror):
    FlipLong = 1{RVOL >= θ_rvol} · 1{z-disp >= θ_z} · 1{VWAP reclaim} · 1{OBV slope t >= θ_obv}
    optional confirmation: MFI >= θ_mfi_hi (or <= θ_mfi_lo short) and breakout/ATR >= θ_atr

Estimators (exactly as specified):
    z-displacement  = (P - VWAP) / σ_tod      σ_tod = same-slot empirical std of price-VWAP residuals
    OBV slope       = t-stat of OLS slope of OBV over the last `win` bars (default 8)
    breakout/ATR    = (P - breakout_level) / ATR(14)
Defaults come from the indicator literature (RVOL 2.0, |z| 2.0σ, OBV |t| 2.0, MFI 80/20, breakout 1.0 ATR);
live cutoffs should be re-estimated walk-forward (see threshold_calib.py) and passed in via `cutoffs`.

Pure stdlib; unit-tested. Research only — not advice.
"""
import math

DEFAULT_CUTOFFS = {"rvol": 2.0, "z": 2.0, "obv_t": 2.0, "mfi_hi": 80.0, "mfi_lo": 20.0, "atr": 1.0}


def sigma_tod_displacement(price, vwap, sigma_tod):
    """(P - VWAP) / σ_tod, where σ_tod is the same-time-of-day empirical std of price-VWAP residuals."""
    if sigma_tod is None or sigma_tod <= 0:
        return None
    return (price - vwap) / sigma_tod


def breakout_atr(price, breakout_level, atr):
    """(P - breakout_level) / ATR(14). Positive = above the breakout pivot in ATR units."""
    if atr is None or atr <= 0:
        return None
    return (price - breakout_level) / atr


def obv_slope_t(obv, win=8):
    """t-stat of the OLS slope of OBV over the last `win` bars. Sign = accumulation/distribution direction."""
    y = [float(v) for v in (obv or []) if v is not None][-win:]
    n = len(y)
    if n < 3:
        return None
    xs = list(range(n))
    mx = sum(xs) / n; my = sum(y) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    sxy = sum((xs[i] - mx) * (y[i] - my) for i in range(n))
    b = sxy / sxx
    yh = [my + b * (xs[i] - mx) for i in range(n)]
    sse = sum((y[i] - yh[i]) ** 2 for i in range(n))
    if n - 2 <= 0:
        return None
    s2 = sse / (n - 2)
    se = math.sqrt(s2 / sxx) if s2 > 0 and sxx > 0 else 0.0
    if se <= 0:
        return None if s2 > 0 else (math.copysign(99.0, b) if b else 0.0)
    return b / se


def _passes(value, cutoff, side):
    if value is None:
        return False
    return value >= cutoff if side == "ge" else value <= cutoff


def evaluate(metrics, cutoffs=None, side="long"):
    """Evaluate the conviction flip and return BOTH the boolean flip and a per-metric publication ledger.

    metrics keys (any subset; missing => that gate is not met / not shown):
        rvol, z (sigma displacement), vwap_reclaim (bool), obv_t, mfi, breakout_atr
    side: 'long' or 'short' (mirrors the comparators).
    Returns {flip, side, gates:[{metric,value,cutoff,cmp,pass}], row} where `row` is the literal,
    operator-facing audit string.
    """
    c = dict(DEFAULT_CUTOFFS); c.update(cutoffs or {})
    m = metrics or {}
    long = side == "long"
    gates = []

    def add(metric, value, cutoff, cmp_side, fmt):
        ok = _passes(value, cutoff, cmp_side)
        gates.append({"metric": metric, "value": value, "cutoff": cutoff, "cmp": cmp_side, "pass": ok, "fmt": fmt(value, cutoff, ok)})
        return ok

    # core hard gates (must ALL pass)
    g_rvol = add("RVOL", m.get("rvol"), c["rvol"], "ge",
                 lambda v, t, ok: "RVOL %s%s%.2f" % (("%.2f" % v) if v is not None else "—", "≥" , t))
    zc = c["z"] if long else -c["z"]
    g_z = add("z-disp", m.get("z"), zc, "ge" if long else "le",
              lambda v, t, ok: "z %s%sσ %s %.2f" % (("%+.2f" % v) if v is not None else "—", "", ("≥" if long else "≤"), t))
    # VWAP gate is side-aware: long requires a RECLAIM (close back above VWAP); short requires a LOSS
    # (close below VWAP). The input `vwap_reclaim` is True when price is above VWAP.
    _vr = m.get("vwap_reclaim")
    if _vr is None:
        _vwap_val = None
    elif long:
        _vwap_val = 1.0 if _vr else 0.0
    else:
        _vwap_val = 1.0 if (not _vr) else 0.0
    g_vwap = add("VWAP", _vwap_val, 1.0, "ge",
                 lambda v, t, ok: "VWAP %s %s" % ("reclaim" if long else "loss", ("YES" if ok else "no")))
    obvc = c["obv_t"] if long else -c["obv_t"]
    g_obv = add("OBV slope", m.get("obv_t"), obvc, "ge" if long else "le",
                lambda v, t, ok: "OBV slope t=%s%s%.2f" % (("%+.2f" % v) if v is not None else "—", ("≥" if long else "≤"), t))

    core = g_rvol and g_z and g_vwap and g_obv

    # optional confirmations (shown, but do not block the core flip unless present-and-failing is desired)
    if m.get("mfi") is not None:
        if long:
            add("MFI", m.get("mfi"), c["mfi_hi"], "ge", lambda v, t, ok: "MFI %s≥%.0f" % (("%.0f" % v), t))
        else:
            add("MFI", m.get("mfi"), c["mfi_lo"], "le", lambda v, t, ok: "MFI %s≤%.0f" % (("%.0f" % v), t))
    if m.get("breakout_atr") is not None:
        bc = c["atr"] if long else -c["atr"]
        add("Breakout", m.get("breakout_atr"), bc, "ge" if long else "le",
            lambda v, t, ok: "Breakout %s ATR%s%.2f" % (("%+.2f" % v), ("≥" if long else "≤"), t))

    row = " | ".join(g["fmt"] for g in gates)
    return {"flip": bool(core), "side": side, "gates": gates, "row": row, "cutoffs": c}
