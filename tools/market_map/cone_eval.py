"""cone_eval.py — walk-forward cone-coverage backtest comparing projection-band SIGMA SOURCES.

Purpose: promote a cone sigma upgrade (e.g. replacing fib_ref's champion sigma with the
VolatilityArbiter blend) on EVIDENCE, not assertion. This is the concrete "before/after coverage
check" behind the breaking change.

Protocol (no look-ahead): for each decision time t with min_train history, every sigma source
estimates sigma_H from closes[:t+1] ONLY. The symmetric band in log-return space is  mu +/- z*sigma_H
(mu=0: pure dispersion test). We then observe the realized H-ahead log return
    r_t = log(close[t+H] / close[t])
and record hit = (lo <= r_t <= hi). Per source we report:
    coverage           realized hit rate (should ~ nominal level)
    wilson             Wilson score CI on coverage (finite-sample honesty)
    meanHalfWidth      average z*sigma_H (sharpness; smaller is better AT equal calibration)
    intervalScore      Gneiting-Raftery interval score (calibration + sharpness in one; LOWER better)
    calErr             |coverage - level|
A source WINS when its |coverage-level| is within tol AND its interval score is lowest. Overlapping
H-ahead windows make hits serially correlated, so coverage CIs are advisory (documented, not hidden).

Sigma sources provided: sqrt_time (naive), champion (VR-corrected sigma_d*sqrt(H*VR)),
ewma (RiskMetrics), arbiter (volatility_arbiter blend), empirical (rolling realized H-quantile band).
Pure stdlib + the repo's own metrics / volatility_arbiter. Keyless, verified in test_cone_eval.py.
"""
import math

import metrics
import volatility_arbiter as VA


# ---- inverse normal CDF (Acklam rational approximation) ----
def _norm_ppf(p):
    if p <= 0.0 or p >= 1.0:
        raise ValueError("p in (0,1)")
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
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p <= phigh:
        q = p - 0.5; r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
               (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
           ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)


def wilson(k, n, z=1.959963984540054):
    if n <= 0:
        return (0.0, 0.0)
    p = k / n; z2 = z * z
    c = (p + z2 / (2 * n)) / (1 + z2 / n)
    h = (z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / (1 + z2 / n)
    return (max(0.0, c - h), min(1.0, c + h))


def interval_score(y, lo, hi, alpha):
    s = (hi - lo)
    if y < lo:
        s += (2.0 / alpha) * (lo - y)
    elif y > hi:
        s += (2.0 / alpha) * (y - hi)
    return s


def _lr(closes):
    return [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
            if closes[i] > 0 and closes[i - 1] > 0]


# ---- sigma sources: (closes_hist, H) -> sigma_H  (log-return-space horizon vol) ----
def sig_sqrt_time(closes, H):
    r = _lr(closes); sd = metrics.stdev(r) if len(r) > 2 else None
    return sd * math.sqrt(H) if sd and sd > 0 else None


def sig_champion(closes, H):
    r = _lr(closes); sd = metrics.stdev(r) if len(r) > 2 else None
    if not sd or sd <= 0:
        return None
    vr = metrics.variance_ratio(closes, q=min(H, max(2, len(closes) // 4)))
    vr = vr if (vr is not None and vr > 0) else 1.0
    return sd * math.sqrt(H * vr)


def sig_ewma(closes, H):
    r = _lr(closes)
    if len(r) < 5:
        return None
    e = metrics.ewma_vol(r, lam=0.94, annualize=1)
    return e * math.sqrt(H) if (e == e and e and e > 0) else None


def sig_arbiter(closes, H):
    r = _lr(closes)
    if len(r) < 10:
        return None
    sd = metrics.stdev(r)
    if not sd or sd <= 0:
        return None
    comps = [VA.component("hv", sd * math.sqrt(H), reliability=0.9)]
    e = metrics.ewma_vol(r, lam=0.94, annualize=1)
    if e == e and e and e > 0:
        comps.append(VA.component("ewma", e * math.sqrt(H), reliability=0.8))
    vr = metrics.variance_ratio(closes, q=min(H, max(2, len(closes) // 4)))
    lam = VA.vr_lambda(vr, len(r)) if vr is not None else 0.0
    svr = sd * math.sqrt(H * max(vr, 1e-6)) if vr is not None else None
    try:
        return VA.blend(comps, sigma_vr=svr, vr_reliability=lam)["sigma"]
    except ValueError:
        return None


DEFAULT_SOURCES = {"sqrt_time": sig_sqrt_time, "champion": sig_champion,
                   "ewma": sig_ewma, "arbiter": sig_arbiter}


def backtest(closes, H=21, level=0.90, min_train=60, sources=None, stride=1):
    """Walk-forward coverage backtest. Returns {source: metrics}, plus 'recommend' + 'n'.
    stride>1 subsamples decision times (cheaper in CI; coverage estimate is unbiased, just fewer points)."""
    c = [float(x) for x in closes if x is not None and float(x) > 0]
    sources = sources or DEFAULT_SOURCES
    z = _norm_ppf((1.0 + level) / 2.0)
    alpha = 1.0 - level
    acc = {k: {"hit": 0, "n": 0, "wsum": 0.0, "isum": 0.0} for k in sources}
    for t in range(min_train, len(c) - H, max(1, int(stride))):
        hist = c[:t + 1]
        r_real = math.log(c[t + H] / c[t])
        for name, fn in sources.items():
            sH = fn(hist, H)
            if sH is None or sH <= 0:
                continue
            lo, hi = -z * sH, z * sH
            a = acc[name]
            a["hit"] += 1 if (lo <= r_real <= hi) else 0
            a["n"] += 1
            a["wsum"] += z * sH
            a["isum"] += interval_score(r_real, lo, hi, alpha)
    out = {}
    for name, a in acc.items():
        if a["n"] == 0:
            out[name] = {"n": 0}; continue
        cov = a["hit"] / a["n"]
        out[name] = {
            "n": a["n"], "coverage": round(cov, 4), "wilson": [round(x, 4) for x in wilson(a["hit"], a["n"])],
            "meanHalfWidth": round(a["wsum"] / a["n"], 6), "intervalScore": round(a["isum"] / a["n"], 6),
            "calErr": round(abs(cov - level), 4),
        }
    # recommend: among sources within 'tol' of nominal coverage, the lowest interval score; else the
    # source with the smallest calibration error.
    tol = 0.05
    scored = [(k, v) for k, v in out.items() if v.get("n", 0) > 0]
    calibrated = [(k, v) for k, v in scored if v["calErr"] <= tol]
    if calibrated:
        best = min(calibrated, key=lambda kv: kv[1]["intervalScore"])[0]
        reason = "within +/-%.0f%% of nominal, lowest interval score" % (tol * 100)
    elif scored:
        best = min(scored, key=lambda kv: kv[1]["calErr"])[0]
        reason = "none within tolerance; smallest calibration error"
    else:
        best, reason = None, "no usable source"
    return {"level": level, "H": H, "n": (scored[0][1]["n"] if scored else 0),
            "sources": out, "recommend": best, "reason": reason,
            "note": "overlapping H-ahead windows -> hits serially correlated; coverage CIs advisory"}
