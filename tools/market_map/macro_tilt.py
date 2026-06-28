#!/usr/bin/env python3
"""
macro_tilt.py — pure-stdlib REFERENCE for the FULL macro contribution to a name's expected return.

The old Bull/Bear board dotted each name's macro betas against only 4 drivers (OIL, DXY, RATE, VIX),
so ~26 commodities and the real-rate curve never entered the rank. This engine integrates the complete
complex, the CORRECT way:

  macro_tilt(betas, moves)        Σ_k betas[k]*moves[k] over EVERY shared macro factor — DXY, VIX and the
                                  full commodity panel (oil, brent, gold, silver, copper, natgas, ags...).
                                  betas are the PARTIAL (multivariate Lasso) sensitivities already fit in
                                  build_market_map.py, so this is a proper multi-factor attribution, not a
                                  sum of double-counting univariate betas. 'MKT' is excluded (the board
                                  scores market beta separately as drag).
  rate_real_tilt(rate, move)      real-rate curve contribution = bL*dL + bS*dS + bC*dC, where bL/bS/bC are
                                  the Diebold-Li level/slope/curvature DURATION betas (rate_real.py, fit vs
                                  the REAL yields DFII5/10/30) and dL/dS/dC are the recent real-curve moves.
                                  This is the real discount-rate driver, not the TLT price proxy.
  combined_tilt(...)              the headline term the board feeds into alpha. When the real-rate curve is
                                  present, the NOMINAL 'RATE' factor is excluded from macro_tilt so rates are
                                  counted once (via the real curve); otherwise nominal RATE is the fallback.

Verified-engine pattern: this is authoritative; macro_tilt.js is locked to tools/macro_golden.json.
"""
import json, os

__all__ = ["macro_tilt", "rate_real_tilt", "combined_tilt", "gen_fixture"]

_DEFAULT_EXCLUDE = ("MKT",)


def macro_tilt(betas, moves, exclude=_DEFAULT_EXCLUDE):
    """Σ betas[k]*moves[k] over shared keys, skipping `exclude` and any None/NaN."""
    if not betas or not moves:
        return 0.0
    ex = set(exclude or ())
    s = 0.0
    for k, b in betas.items():
        if k in ex:
            continue
        m = moves.get(k)
        if b is None or m is None or b != b or m != m:
            continue
        s += b * m
    return s


def rate_real_tilt(rate, move):
    """Real-rate curve contribution bL*dL + bS*dS + bC*dC (level/slope/curvature duration betas × moves)."""
    if not rate or not move:
        return 0.0
    s = 0.0
    for bk, mk in (("bL", "dL"), ("bS", "dS"), ("bC", "dC")):
        b = rate.get(bk)
        m = move.get(mk)
        if b is None or m is None or b != b or m != m:
            continue
        s += b * m
    return s


def combined_tilt(betas, moves, rate=None, ratemove=None, w_real=1.0, use_real=True):
    """Full macro contribution. With a real-rate curve present, rates come from the real curve only
    (nominal RATE excluded from macro_tilt to avoid double-counting the rate level)."""
    have_real = bool(rate and ratemove and use_real)
    if have_real:
        mt = macro_tilt(betas, moves, exclude=("MKT", "RATE"))
        return mt + w_real * rate_real_tilt(rate, ratemove)
    return macro_tilt(betas, moves, exclude=("MKT",))


# ---- committed golden fixture (both languages lock to it) ----
def gen_fixture():
    cases = [
        {  # energy/materials name: long oil & copper, short USD; real curve steepening
            "betas": {"MKT": 1.1, "OIL": 0.42, "COPPER": 0.31, "GOLD": 0.05, "DXY": -0.22, "VIX": -0.18, "RATE": -0.30, "NATGAS": 0.12},
            "moves": {"OIL": 0.031, "COPPER": -0.012, "GOLD": 0.004, "DXY": 0.006, "VIX": -0.02, "RATE": 0.008, "NATGAS": 0.05, "SILVER": 0.01},
            "rate": {"bMKT": 1.0, "bL": -3.2, "bS": 1.1, "bC": -0.4, "class": "long-duration"},
            "ratemove": {"dL": 0.015, "dS": -0.006, "dC": 0.002},
        },
        {  # rate-sensitive name, no real curve available -> nominal RATE fallback
            "betas": {"MKT": 0.9, "RATE": 0.55, "DXY": 0.10, "GOLD": -0.08},
            "moves": {"RATE": 0.012, "DXY": -0.004, "GOLD": 0.006, "OIL": 0.02},
            "rate": None,
            "ratemove": None,
        },
        {  # broad commodity exposure, flat curve move
            "betas": {"MKT": 1.0, "OIL": 0.2, "BRENT": 0.18, "WHEAT": 0.09, "CORN": 0.07, "DXY": -0.15},
            "moves": {"OIL": -0.01, "BRENT": -0.008, "WHEAT": 0.02, "CORN": 0.015, "DXY": 0.003},
            "rate": {"bMKT": 0.8, "bL": -1.0, "bS": 0.3, "bC": 0.1, "class": "neutral"},
            "ratemove": {"dL": 0.0, "dS": 0.0, "dC": 0.0},
        },
    ]
    rows = []
    for c in cases:
        rows.append({
            "betas": c["betas"], "moves": c["moves"], "rate": c["rate"], "ratemove": c["ratemove"],
            "macroTilt": macro_tilt(c["betas"], c["moves"]),
            "macroTiltExRate": macro_tilt(c["betas"], c["moves"], exclude=("MKT", "RATE")),
            "rateRealTilt": rate_real_tilt(c["rate"], c["ratemove"]) if c["rate"] else 0.0,
            "combined": combined_tilt(c["betas"], c["moves"], c["rate"], c["ratemove"]),
        })
    return {"fixture_version": 1, "case": "macro-tilt-core", "w_real": 1.0, "rows": rows}


def main():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "macro_golden.json")
    json.dump(gen_fixture(), open(p, "w"), separators=(",", ":"))
    print("wrote", os.path.normpath(p))


if __name__ == "__main__":
    main()
