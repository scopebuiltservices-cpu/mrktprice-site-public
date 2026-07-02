"""expectations_engine.py — expected-vs-actual reconciliation from the cone half-width, done right.

The projection cone's half-width (z*sigma_H, an ENDPOINT prediction interval) is used for what it
actually measures — containment of the realized close — and each surprise metric is compared against
the CORRECT estimand:

  price range  -> the realized close-range is compared to the model's EXPECTED PATH RANGE, i.e. the
                  Maximum-Favorable + Maximum-Adverse Excursion (path_probability), with a
                  Broadie-Glasserman discrete-monitoring correction so the ratio centres at 1 for a
                  well-calibrated series (a naive "range vs endpoint band" ratio is biased to ~0.85).
  volatility   -> realized variance (RV = sum r^2) vs forecast variance sigma_H^2, scored with the
                  proxy-robust QLIKE loss (vol_loss), not a bare ratio.
  volume       -> a robust z-score in LOG-volume space vs an EWMA log-volume baseline (RVOL is heavy-
                  right-tailed, so a raw ratio with fixed thresholds is not honest). Independent of
                  the half-width.

Per the "Econometric Chart Marks" guidance, the band carries its TYPE and LEVEL. Pure stdlib, keyless,
verified against planted structure (centred ratios, QLIKE=0 on a perfect forecast, log-z sign).
"""
import math

import metrics
import path_probability as PP
import vol_loss

# Broadie-Glasserman discrete-monitoring shift = -zeta(1/2)/sqrt(2*pi); daily closes undersample the
# continuous path max/min, so the expected DISCRETE range is the continuous range minus 2*BETA*sigma_step.
BETA = 0.5825971579


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
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p <= phigh:
        q = p - 0.5; r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)


def expected_band(price, sigma_H, level=0.90):
    """ENDPOINT prediction interval for the price over the horizon (labeled kind + level)."""
    if not (price and price > 0) or not (sigma_H and sigma_H > 0):
        return None
    z = _norm_ppf((1.0 + level) / 2.0)
    lo = price * math.exp(-z * sigma_H); hi = price * math.exp(z * sigma_H)
    return {"lo": round(lo, 4), "hi": round(hi, 4),
            "halfWidthPct": round(z * sigma_H * 100.0, 3), "rangePct": round((hi - lo) / price * 100.0, 3),
            "level": level, "z": round(z, 4), "sigmaH": round(sigma_H, 6), "kind": "prediction interval"}


def expected_log_range(sigma_H, H, drift_H=0.0):
    """Model's EXPECTED path range in log space = E[maxX] + E[|minX|] (MFE + MAE), corrected for
    discrete (daily-close) monitoring so it matches a realized close-to-close range. Centres the ratio."""
    if not (sigma_H and sigma_H > 0) or H < 1:
        return None
    mfe = PP.expected_max_favorable(sigma_H, drift_H)
    mae = PP.expected_max_adverse(sigma_H, drift_H)
    sd_step = sigma_H / math.sqrt(H)
    return max((mfe + mae) - 2.0 * BETA * sd_step, 1e-9)


def vol_baseline(vols):
    """EWMA-free robust baseline of LOG volume: {logMean, logSd} (mean/sd of log v). None if empty."""
    lv = [math.log(v) for v in vols if v and v > 0]
    if len(lv) < 3:
        return None
    m = sum(lv) / len(lv)
    sd = math.sqrt(sum((x - m) ** 2 for x in lv) / (len(lv) - 1))
    return {"logMean": m, "logSd": sd if sd > 1e-9 else 1e-9}


def _verdict(r, hi=1.25, lo=0.8):
    if r is None:
        return "n/a"
    return "expanded" if r > hi else ("quiet" if r < lo else "as expected")


def reconcile(price0, sigma_H, level, win_closes, win_rets, win_vols, vol_base, realized_close, drift_H=0.0):
    """Expected (correct estimand) vs actual over one completed horizon window."""
    band = expected_band(price0, sigma_H, level)
    if not band:
        return None
    c = [x for x in win_closes if x and x > 0]
    # RANGE: realized close log-range vs expected path range (MFE+MAE, discrete-corrected)
    act_lr = math.log(max(c) / min(c)) if len(c) >= 2 else None
    exp_lr = expected_log_range(sigma_H, len(win_rets) if win_rets else 1, drift_H)
    r_range = round(act_lr / exp_lr, 3) if (act_lr is not None and exp_lr) else None
    # VOLATILITY: realized variance vs forecast variance -> QLIKE (proxy-robust)
    rv = sum(x * x for x in (win_rets or []) if x == x)
    fvar = sigma_H * sigma_H
    ql = vol_loss.qlike([fvar], [rv]) if rv > 0 else None
    real_sig = math.sqrt(rv) if rv > 0 else None
    r_vol = round(real_sig / sigma_H, 3) if real_sig else None
    # VOLUME: robust z in log space vs baseline; RVOL for display
    zvol = None; rvol = None; vv = [v for v in (win_vols or []) if v and v > 0]
    if vv and vol_base:
        act_lv = sum(math.log(v) for v in vv) / len(vv)
        zvol = round((act_lv - vol_base["logMean"]) / vol_base["logSd"], 2)
        rvol = round(math.exp(act_lv) / math.exp(vol_base["logMean"]), 3)
    inside = (realized_close is not None and band["lo"] <= realized_close <= band["hi"])
    return {
        "band": band,
        "range": {"actualLogRange": round(act_lr, 5) if act_lr is not None else None,
                  "expectedLogRange": round(exp_lr, 5) if exp_lr else None, "ratio": r_range, "verdict": _verdict(r_range)},
        "vol": {"forecastVar": round(fvar, 8), "realizedVar": round(rv, 8), "qlike": round(ql, 5) if ql is not None else None,
                "sigmaRatio": r_vol, "verdict": _verdict(r_vol)},
        "volume": {"rvol": rvol, "z": zvol,
                   "verdict": ("n/a" if zvol is None else ("elevated" if zvol > 1.5 else ("light" if zvol < -1.5 else "normal")))},
        "containment": {"inside": bool(inside)},
    }


def _champion_sigma(closes, H):
    """VR-corrected horizon vol sigma_d*sqrt(H*VR) (the current cone champion)."""
    c = [x for x in closes if x and x > 0]
    if len(c) < 30:
        return None
    r = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
    m = sum(r) / len(r)
    v = sum((x - m) ** 2 for x in r) / (len(r) - 1)
    sd = math.sqrt(v)
    if sd <= 0:
        return None
    q = min(H, max(2, len(c) // 4))
    if len(r) < q * 4:
        return sd * math.sqrt(H)
    v1 = sum((x - m) ** 2 for x in r) / len(r)
    if v1 <= 0:
        return sd * math.sqrt(H)
    s = 0.0
    for k in range(q - 1, len(r)):
        su = sum(r[k - i] for i in range(q))
        s += (su - q * m) ** 2
    s /= (len(r) - q + 1)
    vr = s / (q * v1)
    return sd * math.sqrt(H * (vr if vr > 0 else 1.0))


def accuracy(closes, vols, H=21, level=0.90, sigma_fn=None, min_train=60, stride=3):
    """Walk-forward projection accuracy with the corrected estimands: containment (~ level),
    mean centred range ratio (~1 when well-calibrated), aggregate QLIKE variance loss, and the
    share of windows with elevated volume."""
    c = [float(x) for x in closes if x is not None and float(x) > 0]
    vols = vols or []
    sigma_fn = sigma_fn or _champion_sigma
    hit = 0; n = 0; rr = 0.0; nrr = 0; fvars = []; rvars = []; volz_hi = 0; nvz = 0
    for t in range(min_train, len(c) - H, max(1, int(stride))):
        hist = c[:t + 1]
        sH = sigma_fn(hist, H)
        if not sH or sH <= 0:
            continue
        win = c[t:t + H + 1]
        rets = [math.log(win[i] / win[i - 1]) for i in range(1, len(win)) if win[i] > 0 and win[i - 1] > 0]
        base = vol_baseline(vols[max(0, t - 60):t]) if len(vols) > t else None
        rec = reconcile(c[t], sH, level, win, rets, (vols[t:t + H + 1] if len(vols) > t else []), base, c[t + H])
        if not rec:
            continue
        n += 1; hit += 1 if rec["containment"]["inside"] else 0
        if rec["range"]["ratio"] is not None: rr += rec["range"]["ratio"]; nrr += 1
        if rec["vol"]["realizedVar"] and rec["vol"]["realizedVar"] > 0:
            fvars.append(rec["vol"]["forecastVar"]); rvars.append(rec["vol"]["realizedVar"])
        if rec["volume"]["z"] is not None:
            nvz += 1; volz_hi += 1 if rec["volume"]["z"] > 1.5 else 0
    if not n:
        return None
    return {"H": H, "level": level, "n": n, "containment": round(hit / n, 4),
            "meanRangeRatio": round(rr / nrr, 3) if nrr else None,
            "qlike": round(vol_loss.qlike(fvars, rvars), 5) if fvars else None,
            "elevVolShare": round(volz_hi / nvz, 3) if nvz else None}


def _ols_slope(xs, ys):
    n = len(xs)
    if n < 5:
        return None
    mx = sum(xs) / n; my = sum(ys) / n
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    sxx = sum((xs[i] - mx) ** 2 for i in range(n))
    return (sxy / sxx) if sxx > 0 else None


def path_projection(closes, vols=None, H=21, r=5):
    """Fuse the band's DISPERSION (sigma_H) and PERSISTENCE (Lo-MacKinlay VR) into a decision-ready read:

      pathPct     : % probability the horizon move finishes in the EXPECTED direction = Phi(|drift|/sigma_H).
                    Drift is CONDITIONAL on the recent push and bounded by measured persistence
                    (|drift| <= 0.5*sigma_H, scaled by |VR-1|), so pathPct stays in a realistic ~50-69% band
                    and never over-claims. Persist -> continue the push; fade -> revert; RW -> ~50%.
      peak        : expected TOP price = Maximum-Favorable-Excursion of the path in the expected direction
                    (path_probability.expected_max_favorable with drift), and days-to-peak CAPPED at the OU
                    half-life so the peak is timed BEFORE mean reversion (theta) erodes it.
      topVolume   : expected volume AT that peak = median volume x historical volume-elasticity to move size
                    (OLS of log-volume on standardized |return|), shown only 'where smart' (elasticity>0).

    'smart' is True only when VR is statistically significant (|z|>=1.6449); otherwise the directional peak
    claim is suppressed (the path is ~a coin-flip). Keyless, pure stdlib, verified against planted structure.
    """
    c = [float(x) for x in (closes or []) if x is not None and float(x) > 0]
    if len(c) < 60:
        return None
    lr = [math.log(c[i] / c[i - 1]) for i in range(1, len(c)) if c[i] > 0 and c[i - 1] > 0]
    if len(lr) < 40:
        return None
    mu = sum(lr) / len(lr)
    sd_d = math.sqrt(sum((x - mu) ** 2 for x in lr) / (len(lr) - 1))
    if sd_d <= 0:
        return None
    sH = _champion_sigma(c, H)
    if not sH or sH <= 0:
        return None
    q = min(H, max(2, len(c) // 4))
    vs = metrics.variance_ratio_stat(c, q)
    vr = vs["vr"] if vs else 1.0
    z = vs["z"] if vs else None
    sig = bool(z is not None and abs(z) >= 1.6449)
    hl = metrics.half_life(c)
    tail = sum(lr[-r:])
    push = 1.0 if tail > 0 else (-1.0 if tail < 0 else 1.0)
    if sig and vr > 1:
        dir_exp = push; kappa = min(0.5, vr - 1.0)          # persist -> continue the push
    elif sig and vr < 1:
        dir_exp = -push; kappa = min(0.5, 1.0 - vr)         # fade -> revert against the push
    else:
        dir_exp = push; kappa = 0.0                          # random walk -> ~50/50
    drift_H = dir_exp * kappa * sH
    p_dir = PP._ncdf(abs(drift_H) / sH)                      # Phi(|drift|/sigma_H) toward dir_exp
    exc = PP.expected_max_favorable(sH, abs(drift_H))        # expected TOP excursion (with drift)
    P0 = c[-1]
    peak_log = dir_exp * exc
    peak_price = P0 * math.exp(peak_log)
    ttp = max(1.0, min(float(H), hl)) if (hl is not None and vr < 1) else float(H)
    top_vol = vol_mult = None; vol_ok = False
    if vols:
        v = [float(x) for x in vols if x is not None and float(x) > 0]
        if len(v) >= 40 and len(v) >= len(lr):
            av = [abs(x) / sd_d for x in lr]                 # standardized |return|
            lv = [math.log(x) for x in v[-len(lr):]]         # aligned log-volume
            beta = _ols_slope(av, lv)
            medv = sorted(v)[len(v) // 2]
            if beta is not None and beta > 0:
                peak_daily = (abs(peak_log) / ttp) / sd_d    # standardized per-day move at peak pace
                vol_mult = max(1.0, min(math.exp(beta * peak_daily), 8.0))
                top_vol = medv * vol_mult; vol_ok = True
    return {
        "sigmaH": round(sH, 6), "driftH": round(drift_H, 6), "dir": int(dir_exp),
        "pathPct": round(100.0 * p_dir, 1), "pathDir": ("up" if dir_exp > 0 else "down"),
        "vr": round(vr, 3), "z": (round(z, 2) if z is not None else None), "halfLife": (round(hl, 1) if hl else None),
        "peakPrice": round(peak_price, 4), "peakPct": round((math.exp(peak_log) - 1.0) * 100.0, 2),
        "peakLogExc": round(exc, 6), "timeToPeakD": round(ttp, 1),
        "topVolume": (round(top_vol) if top_vol else None), "topVolMult": (round(vol_mult, 2) if vol_mult else None),
        "volElastOK": vol_ok, "smart": sig,
        "note": ("Peak/top shown because persistence is significant (VR z=%.1f)." % z) if sig
                else "VR not significant -> directional peak suppressed; path is ~a coin-flip."}
