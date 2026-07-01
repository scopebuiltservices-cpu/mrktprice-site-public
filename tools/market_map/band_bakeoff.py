#!/usr/bin/env python3
"""band_bakeoff.py — leakage-free walk-forward comparison of interval-band methods (pure stdlib).

The Validation Report requires an experiment that compares at least six band constructions, "because
otherwise it will be impossible to separate gains from better scaling versus gains from better
calibration." This is that committed artifact. For a horizon H it walks forward through the series,
issues a drift-free (mu=0, log-return space) predictive band with each method using ONLY information
available at issue time, matures each forecast H steps later, and scores every method by realized
coverage, average width, and Gneiting-Raftery interval (Winkler) score.

Methods (matches the report's table):
  1 sqrt_gauss           sigma_d*sqrt(H),            parametric normal
  2 hv_gauss             sigma_d*sqrt(H*VR(H)),      parametric normal  (variance-ratio corrected)
  3 ewma_gauss           EWMA sigma * sqrt(H),       parametric normal
  4 garch_gauss          GARCH(1,1) n-step variance, parametric normal
  5 conformal_sym        empirical |raw residual| quantile           (any scale)
  6 conformal_stud_sym   studentized |scaled residual| radius        (horizon-specific scale)
  7 conformal_stud_asym  separate lower/upper studentized tails      (skew + heteroskedasticity)

REUSES metrics (stdev/ewma_vol/variance_ratio/_logret), lineage.garch11_fit/garch11_nstep_var, and
anti_deviation.interval_score. Verified in test_band_bakeoff.py against iid-normal (all methods ~nominal)
and a skewed/heteroskedastic series (asymmetric conformal wins on interval score).
"""
from __future__ import annotations

import math

from metrics import _clean, _logret, ewma_vol, stdev, variance_ratio
from anti_deviation import interval_score
from dm_test import diebold_mariano
import vol_loss

METHODS = ("sqrt_gauss", "hv_gauss", "ewma_gauss", "garch_gauss",
           "conformal_sym", "conformal_stud_sym", "conformal_stud_asym")


def _ppf(p: float) -> float:
    """Standard-normal inverse CDF (Acklam's rational approximation; ~1e-9 accuracy)."""
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


def _quantile(sorted_vals, p):
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return float(sorted_vals[0])
    h = (n - 1) * p
    lo = int(math.floor(h)); hi = min(lo + 1, n - 1)
    return float(sorted_vals[lo] * (1 - (h - lo)) + sorted_vals[hi] * (h - lo))


def _agg():
    return {"n": 0, "cov": 0, "width": 0.0, "isc": 0.0}


def bakeoff(closes, H: int, alpha: float = 0.10, min_train: int = 120, min_cal: int = 40,
            gamma: float = 1e-9, refit_garch_every: int = 10) -> dict:
    """Walk-forward bake-off for one horizon H. alpha = miss rate (nominal coverage = 1-alpha).
    Returns per-method {n, coverage, avgWidth, meanIntervalScore} + the best (lowest-IS) method."""
    c = _clean(closes)
    N = len(c)
    z = _ppf(1 - alpha / 2.0)
    agg = {m: _agg() for m in METHODS}
    series = {m: [] for m in METHODS}      # per-step (t, interval_score) for DM significance testing
    volpairs = {m: [] for m in ("sqrt_gauss", "hv_gauss", "ewma_gauss", "garch_gauss")}  # (sigmaH^2, realized^2)
    # calibration buffers (leakage-free): raw H-step residuals + studentized residuals with issue-time scale
    raw_buf, stud_buf = [], []
    pending = []           # (maturity_index, raw_resid, sigma_issue)
    garch_fit = None

    t = min_train
    while t + H < N:
        # 1) mature any forecasts whose outcome is now observable (issue i with i+H <= t)
        keep = []
        for (mat, e, sig) in pending:
            if mat <= t:
                raw_buf.append(e)
                stud_buf.append(e / (sig + gamma))
            else:
                keep.append((mat, e, sig))
        pending = keep

        train = c[:t + 1]
        rets = _logret(train)
        if len(rets) < 20:
            t += 1
            continue
        sd = stdev(rets)
        realized = math.log(c[t + H] / c[t])          # drift-free target (mu = 0)

        # --- volatility-layer scales ---
        sig_sqrt = sd * math.sqrt(H)
        vr = variance_ratio(train, q=H)
        if vr is None or vr <= 0:
            vr = 1.0
        sig_hv = sd * math.sqrt(H * vr)
        ew = ewma_vol(rets, annualize=0)
        sig_ewma = (ew * math.sqrt(H)) if (ew == ew and ew > 0) else sig_sqrt
        if (t - min_train) % max(1, refit_garch_every) == 0:
            try:
                from lineage import garch11_fit
                garch_fit = garch11_fit(rets)
            except Exception:
                garch_fit = None
        sig_garch = sig_sqrt
        if garch_fit:
            try:
                from lineage import garch11_nstep_var
                gv = garch11_nstep_var(garch_fit, rets, H)
                if gv and gv > 0:
                    sig_garch = math.sqrt(gv)
            except Exception:
                pass
        sig_stud = sig_hv                              # horizon-specific studentization scale

        # --- band per method: [lo, hi] in return space around mu=0 ---
        bands = {
            "sqrt_gauss": (-z * sig_sqrt, z * sig_sqrt),
            "hv_gauss": (-z * sig_hv, z * sig_hv),
            "ewma_gauss": (-z * sig_ewma, z * sig_ewma),
            "garch_gauss": (-z * sig_garch, z * sig_garch),
        }
        if len(raw_buf) >= min_cal:
            rad = _quantile(sorted(abs(x) for x in raw_buf), 1 - alpha)
            bands["conformal_sym"] = (-rad, rad)
        if len(stud_buf) >= min_cal:
            srad = _quantile(sorted(abs(x) for x in stud_buf), 1 - alpha)
            bands["conformal_stud_sym"] = (-(sig_stud + gamma) * srad, (sig_stud + gamma) * srad)
            ss = sorted(stud_buf)
            q_lo = _quantile(ss, alpha / 2.0)
            q_hi = _quantile(ss, 1 - alpha / 2.0)
            bands["conformal_stud_asym"] = ((sig_stud + gamma) * q_lo, (sig_stud + gamma) * q_hi)

        for m, (lo, hi) in bands.items():
            a = agg[m]
            iscv = interval_score(realized, lo, hi, alpha)
            a["n"] += 1
            a["cov"] += 1 if (lo <= realized <= hi) else 0
            a["width"] += (hi - lo)
            a["isc"] += iscv
            series[m].append((t, iscv))
        r2 = realized * realized                       # 1-sample realized variance proxy (QLIKE is proxy-robust)
        volpairs["sqrt_gauss"].append((sig_sqrt * sig_sqrt, r2))
        volpairs["hv_gauss"].append((sig_hv * sig_hv, r2))
        volpairs["ewma_gauss"].append((sig_ewma * sig_ewma, r2))
        volpairs["garch_gauss"].append((sig_garch * sig_garch, r2))

        pending.append((t + H, realized, sig_stud))
        t += 1

    methods = {}
    for m, a in agg.items():
        if a["n"] > 0:
            methods[m] = {"n": a["n"], "coverage": round(a["cov"] / a["n"], 4),
                          "avgWidth": round(a["width"] / a["n"], 6),
                          "meanIntervalScore": round(a["isc"] / a["n"], 6)}
    ranked = sorted(methods.items(), key=lambda kv: kv[1]["meanIntervalScore"])
    best = ranked[0][0] if ranked else None

    # DM significance: does the lowest-interval-score method SIGNIFICANTLY beat each other method?
    # (a lower mean is not a real difference until Diebold-Mariano says so). A=best, B=other on the
    # aligned per-step interval-score series -> meanDiff<0 & significant means best genuinely wins.
    dm_vs_best = {}
    if best:
        bser = dict(series[best])
        for m in methods:
            if m == best:
                continue
            oser = dict(series[m])
            common = sorted(set(bser) & set(oser))
            if len(common) >= 8:
                r = diebold_mariano([bser[t] for t in common], [oser[t] for t in common], h=H)
                if r.get("ok"):
                    dm_vs_best[m] = {"DMstar": r["DMstar"], "pValue": r["pValue"],
                                     "bestBeats": bool(r["significant"] and r["meanDiff"] < 0)}

    # variance-forecast scorecard (QLIKE proxy-robust) for the parametric vol arms vs realized r^2
    vol_score = {}
    for m, pairs in volpairs.items():
        if len(pairs) >= 10 and m in methods:
            vs = vol_loss.score_vol([p[0] for p in pairs], [p[1] for p in pairs])
            vol_score[m] = {"qlike": (round(vs["qlike"], 6) if vs["qlike"] is not None else None),
                            "mse": (round(vs["mse"], 12) if vs["mse"] is not None else None), "n": vs["n"]}
    vol_ranked = sorted((m for m in vol_score if vol_score[m]["qlike"] is not None),
                        key=lambda m: vol_score[m]["qlike"])

    return {"H": H, "alpha": alpha, "nominal": round(1 - alpha, 4),
            "methods": methods,
            "ranking": [m for m, _ in ranked],
            "best": best,
            "dmVsBest": dm_vs_best,
            "bestSignificantlyBeats": [m for m, d in dm_vs_best.items() if d["bestBeats"]],
            "volScore": vol_score,
            "volArmByQlike": vol_ranked}


def run_bakeoff_multi(closes, horizons=(1, 5, 10, 21, 63), alpha: float = 0.10, **kw) -> dict:
    """Bake-off across horizons -> a single artifact dict (write to JSON for the reporting pack)."""
    return {"alpha": alpha, "nominal": round(1 - alpha, 4),
            "byHorizon": {str(H): bakeoff(closes, H, alpha=alpha, **kw) for H in horizons}}


if __name__ == "__main__":
    import json
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("usage: band_bakeoff.py <closes.json>  (JSON array of closes)", file=sys.stderr)
        raise SystemExit(2)
    closes = json.load(open(path))
    print(json.dumps(run_bakeoff_multi(closes), indent=2))
