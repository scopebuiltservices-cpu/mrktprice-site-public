#!/usr/bin/env python3
"""pit_stream.py — turn the matured studentized-residual ledger into a PIT stream and run the conformal
e-process calibration alarm on it. This CLOSES the calibration loop end-to-end:

    matured residuals z_t  ->  expanding-window predictive CDF  F̂_{t-1}  ->  randomized PIT U_t = F̂_{t-1}(z_t)
                            ->  conformal e-process (test martingale)  ->  anytime-valid alarm

Why this is a genuine (non-circular) calibration test: the predictive CDF at step t is built ONLY from
residuals seen strictly before t (predictable / no look-ahead), so under a well-specified, stationary model
the PIT is Uniform(0,1) by construction — and any DRIFT or misspecification (the mean or dispersion of the
residuals changing over time) pushes the PIT off-uniform, which the e-process detects with a level that is
controlled uniformly over time (Ville). Pure stdlib; composes predictive_cdf + eprocess.

Source of `z`: anti_deviation's matured records already carry a studentized residual `z` per forecast
(z = (y - mu)/sigma), so no new data is needed — feed those records here."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import predictive_cdf as PC
import eprocess as EP


def pit_series(matured, min_train=40, seed=12345):
    """Expanding-window randomized PIT of matured studentized residuals (time-ordered).
    `matured`: list of dicts each with a numeric 'z' (studentized residual). Returns the PIT list (may be [])."""
    z = [float(m["z"]) for m in (matured or [])
         if isinstance(m, dict) and isinstance(m.get("z"), (int, float)) and m["z"] == m["z"]]
    n = len(z)
    if n < min_train + 20:
        return []
    rng = random.Random(seed)
    out = []
    for t in range(min_train, n):
        try:
            cdf = PC.PredictiveCDF(0.0, 1.0, z[:t])       # predictive for z is the empirical law of PAST z
        except Exception:
            continue
        out.append(cdf.randomized_pit(z[t], u=rng.random()))
    return out


def calibration_alarm(matured, warn=20.0, kill=100.0, min_train=40):
    """Full chain: matured residual ledger -> PIT stream -> conformal e-process alarm.
    Returns the eprocess dict augmented with {source, nPit}, or None if too little matured history."""
    pit = pit_series(matured, min_train=min_train)
    if len(pit) < 20:
        return None
    res = EP.conformal_eprocess(pit, warn=warn, kill=kill)
    if res is not None:
        res["source"] = "matured studentized residuals (expanding-window predictive CDF, no look-ahead)"
        res["nPit"] = len(pit)
    return res
