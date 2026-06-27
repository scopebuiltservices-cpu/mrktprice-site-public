#!/usr/bin/env python3
"""Options conventions registry + data-quality gate (pure stdlib).

Implements the two controls the BSM audit ("Audit Framework for Black-Scholes and Black-Scholes-Merton
Implementations") flags as IMMEDIATE: a single source of truth for pricing conventions, and a hard gate
that rejects stale/crossed/locked quotes, bad timestamps, wrong vol units, missing contract adjustments,
and mismatched exercise style BEFORE the pricer runs. The whole point is to make every downstream price,
Greek, IV, and band reproducible under one documented convention rather than silently drifting.

No third-party deps. Mirrors the audit's `conventions_registry` and `data_quality_gate` modules.
"""

# --------------------------------------------------------------------------- conventions registry
# Frozen, documented house conventions. Anything that prices an option reads from HERE, so day-count,
# annualization, scaling, curve choice, and exercise-style policy can never disagree across modules.
CONVENTIONS = {
    "version": "1.0",
    "day_count": "ACT/365F",          # calendar-day count, 365-day year (matches black_scholes T in years)
    "annualization": 365.0,           # days per year for T = days/annualization
    "theta_scaling": "per_year",      # greeks() returns dV/dt in price-per-year (divide by 365 for per-day)
    "vega_scaling": "per_1.00_vol",   # vega is dV/dsigma per 1.00 (=100 vol pts); /100 for per-vol-point
    "rho_scaling": "per_1.00_rate",   # rho per 1.00 (=100bp*100); /10000 for per-1bp
    "rate_curve": "UST_par_then_SOFR",# official risk-free: Treasury par curve, SOFR/OIS fallback
    "dividend": "continuous_yield_q", # q as continuous yield; discrete-cash schedule overrides when known
    "exercise_style_default": "american",  # standard OCC-cleared single-name equity options are American
    "index_exercise_style": "european",    # cash-settled index options are European
    "contract_multiplier": 100,       # standard OCC equity option multiplier (adjusted by corporate actions)
    "quote_basis": "mid_bidask_aware",# calibrate to bid/ask-aware mid, never last/stale
    "vol_units": "decimal",           # 0.20 == 20% (NOT 20.0)
}

def style_for(instrument_kind):
    """Exercise-style policy: 'index'/'etf-cash' -> European; everything else (single-name equity) -> American."""
    k = (instrument_kind or "").lower()
    if k in ("index", "cash_index", "european"):
        return "european"
    return CONVENTIONS["exercise_style_default"]

def years_from_days(days):
    """Time-to-expiry in years under the registered day-count. Single choke point so no module
    silently uses 252 or 360."""
    return max(0.0, float(days)) / CONVENTIONS["annualization"]


# --------------------------------------------------------------------------- data-quality gate
def _is_num(x):
    try:
        return x is not None and x == x and abs(float(x)) != float("inf")
    except (TypeError, ValueError):
        return False

def bsm_input_gate(S, K, T, sigma, r=0.0, q=0.0):
    """Positivity / finiteness gate for the pricer inputs (audit row 1). Returns (ok, rejects)."""
    rej = []
    for name, v, lo in (("S", S, 0.0), ("K", K, 0.0), ("T", T, -1e-12), ("sigma", sigma, -1e-12)):
        if not _is_num(v):
            rej.append("%s_not_finite" % name)
        elif (v <= lo if name in ("S", "K") else v < lo):
            rej.append("%s_nonpositive" % name)
    for name, v in (("r", r), ("q", q)):
        if not _is_num(v):
            rej.append("%s_not_finite" % name)
    return (not rej, rej)

def quote_gate(quote, asof_ts=None, max_stale_sec=120, conv=None):
    """Reject a single option quote that violates the audit's data-quality table. `quote` keys:
        bid, ask, ts (epoch sec), expiry_days, sigma (IV, decimal), style, kind, multiplier,
        underlying_kind (for exercise-style coherence), spot, strike.
    Returns {ok, rejects, mid}. Only `bid`/`ask` are strictly required; others checked when present.
    """
    conv = conv or CONVENTIONS
    rej = []
    bid = quote.get("bid"); ask = quote.get("ask")
    # quote sanity: present, finite, non-negative, not crossed/locked
    if not _is_num(bid) or not _is_num(ask):
        rej.append("bidask_not_finite")
    else:
        if bid < 0 or ask < 0:
            rej.append("negative_quote")
        if ask < bid:
            rej.append("crossed_market")        # ask below bid
        elif ask == bid and bid != 0:
            rej.append("locked_market")          # bid == ask (non-zero) = locked
    mid = ((bid + ask) / 2.0) if (_is_num(bid) and _is_num(ask)) else None
    # timestamp coherence (staleness)
    ts = quote.get("ts")
    if ts is not None and asof_ts is not None:
        if not _is_num(ts) or (asof_ts - ts) > max_stale_sec:
            rej.append("stale_quote")
        if ts - asof_ts > 1:
            rej.append("future_timestamp")
    # vol units: IV must be decimal (0<sigma<5); a value like 20.0 means percent points were passed
    sig = quote.get("sigma")
    if sig is not None:
        if not _is_num(sig) or sig <= 0:
            rej.append("iv_nonpositive")
        elif sig > 5.0:
            rej.append("iv_units_look_like_percent")   # 20.0 not 0.20
    # exercise-style coherence with the underlying
    style = quote.get("style"); ukind = quote.get("underlying_kind")
    if style and ukind:
        if style_for(ukind) != style.lower():
            rej.append("exercise_style_mismatch")
    # contract adjustment sanity: a non-standard multiplier must be flagged adjusted
    mult = quote.get("multiplier")
    if mult is not None and mult != conv["contract_multiplier"] and not quote.get("adjusted"):
        rej.append("nonstandard_multiplier_unflagged")
    # expiry sanity
    ed = quote.get("expiry_days")
    if ed is not None and (not _is_num(ed) or ed < 0):
        rej.append("negative_time_to_expiry")
    return {"ok": not rej, "rejects": rej, "mid": mid}

def curve_coverage_ok(tenors_years, max_expiry_years):
    """Curve-coverage check (audit): the rate curve must span the longest option maturity, else
    discounting/rho for long-dated options is extrapolated. Returns (ok, note)."""
    if not tenors_years:
        return (False, "no_curve")
    if max_expiry_years <= max(tenors_years) + 1e-9:
        return (True, "covered")
    return (False, "extrapolated_beyond_%.2fy" % max(tenors_years))


if __name__ == "__main__":
    print("conventions v%s day_count=%s" % (CONVENTIONS["version"], CONVENTIONS["day_count"]))
    print(quote_gate({"bid": 1.20, "ask": 1.25, "sigma": 0.22}))
    print(quote_gate({"bid": 1.30, "ask": 1.25}))             # crossed
    print(quote_gate({"bid": 1.0, "ask": 1.1, "sigma": 22.0}))  # percent IV
