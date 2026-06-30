#!/usr/bin/env python3
"""
composite_gate.py — deflated-Sharpe gate on the COMPOSITE signal (stdlib).

The deep-research spec is explicit: a deflated-Sharpe gate belongs on the composite itself, not only on
the individual factors. A composite can look great purely because many variants, horizons, thresholds,
and factor subsets were tried before landing on the current configuration. This module:

  1. Builds the composite IC time series  C_t = Σ_f w_f · IC_{f,t}  from the per-period factor IC history
     and the (already BH-FDR-gated, sign-aware) factor weights.
  2. Computes the composite's realized Sharpe over that history (annualized by the rebalance cadence).
  3. Deflates it with an HONEST trial count (from trial_ledger) via factor_eval.deflated_sharpe.
  4. Emits a conviction SCALE in [0,1] that degrades gracefully when the composite fails the DSR hurdle
     or when factor breadth is thin — instead of silently pretending the signal is intact.

Pure stdlib; unit-tested against planted structure. Research only.
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import factor_eval as fe


def composite_series(ic_history, weights):
    """C_t = Σ_f w_f · IC_{f,t}, aligned on the shortest common length (most recent overlap)."""
    facs = [f for f in weights if f in ic_history and ic_history[f]]
    if not facs:
        return []
    L = min(len(ic_history[f]) for f in facs)
    if L <= 0:
        return []
    out = []
    for k in range(L):
        s = 0.0
        for f in facs:
            ser = ic_history[f]
            s += float(weights[f]) * float(ser[len(ser) - L + k])
        out.append(s)
    return out


def sharpe(series, periods_per_year):
    """Annualized Sharpe of a per-rebalance series. periods_per_year ties the cadence to a year."""
    n = len(series)
    if n < 2:
        return None
    mu = sum(series) / n
    var = sum((x - mu) ** 2 for x in series) / (n - 1)
    sd = math.sqrt(var)
    if sd <= 0:
        return None
    return (mu / sd) * math.sqrt(max(periods_per_year, 1e-9))


def _moments(series):
    n = len(series)
    if n < 3:
        return 0.0, 3.0
    mu = sum(series) / n
    m2 = sum((x - mu) ** 2 for x in series) / n
    if m2 <= 0:
        return 0.0, 3.0
    m3 = sum((x - mu) ** 3 for x in series) / n
    m4 = sum((x - mu) ** 4 for x in series) / n
    sd = math.sqrt(m2)
    return m3 / (sd ** 3), m4 / (m2 ** 2)


def gate(ic_history, weights, *, horizon, n_trials, breadth=1.0,
         dsr_hurdle=0.95, min_breadth=0.30, ann_base=252.0):
    """Composite DSR gate. Returns a dict with the composite Sharpe, deflated Sharpe (DSR), pass flag,
    and a conviction SCALE in [0,1] for the board to multiply into its displayed conviction.

      - DSR >= dsr_hurdle AND breadth >= min_breadth  -> pass, scale 1.0
      - DSR below the hurdle                            -> scale = DSR/hurdle (linear degrade)
      - breadth below min_breadth                       -> scale also multiplied by breadth/min_breadth
    The scale is the graceful-degradation knob: weak/over-searched composites quietly lose conviction
    rather than masquerading as intact signal.
    """
    series = composite_series(ic_history, weights)
    n_obs = len(series)
    ppy = ann_base / max(horizon, 1)                 # rebalance cadence -> periods per year
    # UNITS: the Bailey-Lopez de Prado DSR compares the PER-OBSERVATION Sharpe against the expected-max
    # Sharpe under the null (sr0), which is in the same per-observation units. So deflate sr_raw, and keep
    # the annualized Sharpe only for human-facing display.
    sr_raw = sharpe(series, 1.0)
    sr_ann = sharpe(series, ppy)
    if sr_raw is None:
        return {"compositeSharpe": None, "compositeSharpeRaw": None, "dsr": None, "sr0": None, "pass": False,
                "convictionScale": 0.0, "nObs": n_obs, "nTrials": int(n_trials),
                "reason": "insufficient composite history"}
    skew, kurt = _moments(series)
    # Cross-trial Sharpe DISPERSION estimated from the actual trial ledger (each factor's IC series is one
    # tried configuration). DSR's expected-max-Sharpe null scales with this dispersion, not the trial count
    # alone. Fall back to the conservative 1.0 prior only when fewer than 2 usable trials exist.
    trial_series = [ic_history[f] for f in weights if f in ic_history and ic_history.get(f)]
    sr_disp = fe.estimate_sr_trials_std(trial_series)
    sr_trials_std = sr_disp if sr_disp is not None else 1.0
    # Honest provenance for the dispersion input: did we MEASURE it from the trial ledger, or fall back
    # to the conservative 1.0 prior (and if so, why)? The board can flag a provisional DSR accordingly.
    disp_status = ("measured" if sr_disp is not None
                   else ("insufficient_trials" if len(trial_series) < 2 else "fallback_prior"))
    d = fe.deflated_sharpe(sr_raw, n_obs, skew=skew, kurt=kurt, n_trials=int(n_trials), sr_trials_std=sr_trials_std)
    dsr = d.get("dsr")
    passed = bool(dsr is not None and dsr >= dsr_hurdle and breadth >= min_breadth)
    scale = 1.0
    if dsr is not None and dsr < dsr_hurdle:
        scale *= max(0.0, dsr / dsr_hurdle)
    if breadth < min_breadth:
        scale *= max(0.0, breadth / min_breadth)
    scale = max(0.0, min(1.0, scale))
    reason = "composite passes DSR + breadth" if passed else (
        "composite below DSR hurdle" if (dsr is not None and dsr < dsr_hurdle) else "thin breadth")
    return {"compositeSharpe": round(sr_ann, 4), "compositeSharpeRaw": round(sr_raw, 4),
            "dsr": dsr, "sr0": d.get("sr0"), "pass": passed,
            "convictionScale": round(scale, 4), "nObs": n_obs, "nTrials": int(n_trials),
            "skew": round(skew, 3), "kurt": round(kurt, 3), "breadth": round(breadth, 3),
            "srTrialsStd": (round(sr_trials_std, 4) if sr_disp is not None else None),
            "dispersionStatus": disp_status,   # measured | fallback_prior | insufficient_trials
            "dsrProvisional": (disp_status != "measured"),
            "dsrHurdle": dsr_hurdle, "reason": reason}
