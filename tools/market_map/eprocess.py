#!/usr/bin/env python3
"""eprocess.py — a CONFORMAL E-PROCESS (test-martingale) calibration alarm: an ANYTIME-VALID sequential
test of the null "the forecasts are calibrated", driven by the stream of matured randomized-PIT values.

Why not a fixed-window KS/coverage check: those spend a fixed alpha at a fixed time. A calibration monitor
watches an ever-growing stream and we want to raise an alarm the moment evidence accumulates, with the
false-alarm rate controlled UNIFORMLY over time. A test martingale M_t (E_{H0}[M_t] = 1, M_t >= 0) gives
exactly that: by Ville's inequality  P(sup_t M_t >= 1/alpha) <= alpha.  So M crossing 20 is ~5% level, 100
is ~1% level, anytime — no multiplicity correction needed.

Construction (Waudby-Smith & Ramdas 2024, "betting" / hedged capital):
  Under calibration, PIT U_t ~ iid Uniform(0,1). We bet on two bounded statistics whose null means are known:
    * LOCATION  x = U           , null mean m = 1/2   (catches a biased centerline: PIT mean != 1/2)
    * DISPERSION x = |U - 1/2|   , null mean m = 1/4   (catches over/under-dispersed bands: PIT U-shaped/humped)
  For each statistic we run the HEDGED capital process  M = (M+ + M-)/2, where
    M±_t = Π_{s<=t} ( 1 ± λ_s (x_s - m) ),   λ_s predictable (aGRAPA), truncated so every factor stays > 0.
  M+ grows if x drifts ABOVE m, M- if BELOW — so the hedge catches deviation in either direction. The overall
  calibration e-value is the MIXTURE E = mean of the 4 wealths (a mixture of e-processes is an e-process,
  so E_{H0}[E] <= 1 and Ville still applies). eMax = running sup; the anytime p-value bound is 1/eMax.

Caveat (per the spec): exchangeability/calibration supermartingales are powerless against pure ordering, so
this alarms on CALIBRATION DRIFT (location bias / dispersion mismatch), NOT on price direction. Feed it only
MATURED, out-of-sample PIT values. Pure stdlib, deterministic."""


def _agrapa_hedged(xs, m, xmin, xmax, c=0.5, w0=1.0):
    """Run the hedged capital process for one bounded statistic. xs: observed statistic values in [xmin,xmax];
    m: null mean; returns (final_hedged, running_max_hedged, final_Mplus, final_Mminus)."""
    dev = max(m - xmin, xmax - m)
    if dev <= 0:
        return 1.0, 1.0, 1.0, 1.0
    lam_cap = c / dev                              # keep 1 ± λ(x-m) > 0 with margin (c < 1)
    v0 = (dev * dev) / 3.0                          # prior variance (uniform-on-[m-dev,m+dev] scale)
    Mp = Mm = 1.0
    eMax = 1.0
    sx = 0.0; sxx = 0.0; n = 0                      # accumulators over data seen SO FAR (predictable)
    for x in xs:
        n1 = n
        mu_hat = (m * w0 + sx) / (w0 + n1)
        var_hat = ((v0 + 0.0) * w0 + (sxx - 2 * mu_hat * sx + n1 * mu_hat * mu_hat)) / (w0 + n1)
        if var_hat < 1e-12:
            var_hat = 1e-12
        lam = (mu_hat - m) / var_hat                # GRAPA growth-optimal tilt (predictable: uses x_1..x_{t-1})
        L = min(abs(lam), lam_cap)                  # magnitude; hedge supplies both signs
        d = x - m
        Mp *= (1.0 + L * d)
        Mm *= (1.0 - L * d)
        if Mp < 0.0: Mp = 0.0
        if Mm < 0.0: Mm = 0.0
        if Mp > 1e12: Mp = 1e12          # saturate (we only test crossing of warn/kill; avoids overflow)
        if Mm > 1e12: Mm = 1e12
        hedged = 0.5 * (Mp + Mm)
        if hedged > eMax:
            eMax = hedged
        sx += x; sxx += x * x; n += 1
    return 0.5 * (Mp + Mm), eMax, Mp, Mm


def conformal_eprocess(pits, warn=20.0, kill=100.0, c=0.5):
    """Calibration e-process over a stream of PIT values (each in [0,1]).

    Returns a dict:
      n           : number of usable PIT values
      eValue      : final mixture e-value
      eMax        : running supremum of the mixture (the thing Ville bounds)
      pAnytime    : anytime-valid p-value bound = min(1, 1/eMax)
      level       : 'ok' | 'warn' | 'kill'   (eMax >= warn -> warn; >= kill -> kill)
      warn, kill  : thresholds used
      components  : per-statistic {loc:{ePlus,eMinus,hedgedMax}, disp:{...}}
      note        : human-readable verdict
    None if fewer than 20 usable PIT values (too little to test)."""
    u = [float(p) for p in (pits or []) if p == p and 0.0 <= float(p) <= 1.0]
    if len(u) < 20:
        return None
    loc = u                                          # x = U,        m = 1/2
    disp = [abs(x - 0.5) for x in u]                 # x = |U-1/2|,  m = 1/4
    lf, lmax, lp, lm = _agrapa_hedged(loc, 0.5, 0.0, 1.0, c=c)
    df, dmax, dp, dm = _agrapa_hedged(disp, 0.25, 0.0, 0.5, c=c)
    e_final = 0.5 * (lf + df)
    e_max = 0.5 * (lmax + dmax)                       # mixture of the two hedged running maxima
    level = "kill" if e_max >= kill else ("warn" if e_max >= warn else "ok")
    p_any = min(1.0, 1.0 / e_max) if e_max > 0 else 1.0
    which = "location" if lmax >= dmax else "dispersion"
    note = ({"ok": "calibration consistent (no anytime-valid evidence of miscalibration)",
             "warn": "calibration drift detected (%s) — eMax=%.1f, anytime p<=%.3f" % (which, e_max, p_any),
             "kill": "STRONG calibration failure (%s) — eMax=%.1f, anytime p<=%.4f; recalibrate/refit" % (which, e_max, p_any)})[level]
    return {"n": len(u), "eValue": round(e_final, 4), "eMax": round(e_max, 4),
            "pAnytime": round(p_any, 5), "level": level, "warn": warn, "kill": kill,
            "components": {"loc": {"ePlus": round(lp, 4), "eMinus": round(lm, 4), "hedgedMax": round(lmax, 4)},
                           "disp": {"ePlus": round(dp, 4), "eMinus": round(dm, 4), "hedgedMax": round(dmax, 4)}},
            "note": note}
