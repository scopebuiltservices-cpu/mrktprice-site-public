"""One canonical per-maturity risk-free accessor.

Both alpaca_options.py and eodhd_options.py previously carried a byte-identical
``_rate(days)`` clone that did ``_CURVE.rate_for(days/365)`` off a module-global
curve. This module is the single source of truth for that lookup so the two
fetchers can't silently diverge.

``rate_for_days(days)`` returns the continuously-compounded ZERO rate for the
given tenor (in calendar days), built from rate_curve's default curve. The curve
is cached at module load. Live FRED is used when MRKT_FETCH_CURVE=1, else the
static fallback curve. Numerically identical to the old ``_rate`` clones:
``rate_for(max(days, 1) / 365.0)`` with a scalar MRKT_RISK_FREE fallback on error.
"""
import os
import rate_curve as _rc

_R = float(os.environ.get("MRKT_RISK_FREE", "0.04"))   # scalar fallback
_CURVE = None


def _curve():
    """Lazily build and cache the default zero curve (live FRED if MRKT_FETCH_CURVE=1)."""
    global _CURVE
    if _CURVE is None:
        if os.environ.get("MRKT_FETCH_CURVE") == "1":
            _CURVE = _rc.Curve(_rc.fetch_curve())
        else:
            _CURVE = _rc.default_curve()
    return _CURVE


def rate_for_days(days):
    """Per-maturity continuously-compounded zero rate for a tenor of ``days`` calendar days.

    Mirrors the old _rate(days) clones exactly: rate_for(max(days, 1) / 365.0),
    falling back to the scalar MRKT_RISK_FREE on any error."""
    try:
        return _curve().rate_for(max(days, 1) / 365.0)
    except Exception:
        return _R
