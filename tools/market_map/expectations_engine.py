"""expectations_engine.py — expected-vs-actual reconciliation from the cone half-width.

Turns the projection cone's HALF-WIDTH (z*sigma_H in log-return space) into concrete, LABELED
expectations for price range, volatility and volume, then scores them against what actually happened
so "projection accuracy" is a measured number, not a claim.

Per the "Econometric Chart Marks" guidance, every interval carries its TYPE and LEVEL: the cone is a
PREDICTION interval (outcome uncertainty) at a stated coverage — never an unlabeled band. Nested
levels (50/80/95) are supported. Actual range uses the committed close series (hist has close+volume,
not intraday H/L) so it is reported honestly as a CLOSE range. Pure stdlib, keyless, verified.
"""
import math


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
    """PREDICTION interval for the price over the horizon. sigma_H is the horizon vol (log space)."""
    if not (price and price > 0) or not (sigma_H and sigma_H > 0):
        return None
    z = _norm_ppf((1.0 + level) / 2.0)
    lo = price * math.exp(-z * sigma_H); hi = price * math.exp(z * sigma_H)
    return {"lo": round(lo, 4), "hi": round(hi, 4),
            "halfWidthPct": round(z * sigma_H * 100.0, 3),      # +/- move as % of price
            "rangePct": round((hi - lo) / price * 100.0, 3),    # full band width as % of price
            "level": level, "z": round(z, 4), "sigmaH": round(sigma_H, 6),
            "kind": "prediction interval"}


def nested_bands(price, sigma_H, levels=(0.5, 0.8, 0.95)):
    return {("%g" % l): expected_band(price, sigma_H, l) for l in levels}


def realized_range_pct(win_closes):
    """Actual CLOSE-to-close range over the window as % of the window's first close."""
    c = [x for x in win_closes if x and x > 0]
    if len(c) < 2:
        return None
    return (max(c) - min(c)) / c[0] * 100.0


def realized_sigma_H(win_rets, H):
    r = [x for x in win_rets if x == x]
    if len(r) < 2:
        return None
    m = sum(r) / len(r)
    v = sum((x - m) ** 2 for x in r) / (len(r) - 1)
    return math.sqrt(v) * math.sqrt(H)


def _ratio(actual, expected):
    if actual is None or expected is None or expected <= 0:
        return None
    return round(actual / expected, 3)


def _verdict(r):
    if r is None:
        return "n/a"
    return "expanded" if r > 1.25 else ("quiet" if r < 0.8 else "as expected")


def reconcile(price0, sigma_H, level, win_closes, win_rets, win_vols, exp_vol, realized_close):
    """Expected (from half-width) vs actual, for one completed horizon window."""
    band = expected_band(price0, sigma_H, level)
    if not band:
        return None
    act_range = realized_range_pct(win_closes)
    real_sig = realized_sigma_H(win_rets, len(win_rets)) if win_rets else None
    act_vol = (sum(win_vols) / len(win_vols)) if win_vols else None
    r_range = _ratio(act_range, band["rangePct"])
    r_vol = _ratio(real_sig, sigma_H)
    r_voln = _ratio(act_vol, exp_vol)
    inside = (realized_close is not None and band["lo"] <= realized_close <= band["hi"])
    return {
        "band": band,
        "range": {"expectedPct": band["rangePct"], "actualPct": round(act_range, 3) if act_range is not None else None,
                  "ratio": r_range, "verdict": _verdict(r_range)},
        "vol": {"expectedSigmaH": round(sigma_H, 6), "realizedSigmaH": round(real_sig, 6) if real_sig else None,
                "ratio": r_vol, "verdict": _verdict(r_vol)},
        "volume": {"expected": round(exp_vol) if exp_vol else None, "actual": round(act_vol) if act_vol else None,
                   "ratio": r_voln, "verdict": _verdict(r_voln)},
        "containment": {"inside": bool(inside)},
    }


def _champion_sigma(closes, H):
    """Default sigma source: VR-corrected horizon vol sigma_d*sqrt(H*VR) (the current champion)."""
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
    """Walk-forward projection accuracy: project the band from closes[:t+1], then compare to the
    realized window t..t+H. Aggregates containment (should ~ level), and how expected vs actual range,
    volatility, and volume compared on average (ratio ~ 1 = well-calibrated)."""
    c = [float(x) for x in closes if x is not None and float(x) > 0]
    vols = vols or []
    sigma_fn = sigma_fn or _champion_sigma
    hit = 0; n = 0; rr = 0.0; nrr = 0; vrt = 0.0; nvr = 0; vlr = 0.0; nvl = 0
    for t in range(min_train, len(c) - H, max(1, int(stride))):
        hist = c[:t + 1]
        sH = sigma_fn(hist, H)
        if not sH or sH <= 0:
            continue
        p0 = c[t]
        win = c[t:t + H + 1]
        rets = [math.log(win[i] / win[i - 1]) for i in range(1, len(win)) if win[i] > 0 and win[i - 1] > 0]
        exp_vol = (sum(vols[max(0, t - 20):t]) / max(1, len(vols[max(0, t - 20):t]))) if len(vols) > t else None
        win_vol = vols[t:t + H + 1] if len(vols) > t else []
        rec = reconcile(p0, sH, level, win, rets, win_vol, exp_vol, c[t + H])
        if not rec:
            continue
        n += 1; hit += 1 if rec["containment"]["inside"] else 0
        if rec["range"]["ratio"] is not None: rr += rec["range"]["ratio"]; nrr += 1
        if rec["vol"]["ratio"] is not None: vrt += rec["vol"]["ratio"]; nvr += 1
        if rec["volume"]["ratio"] is not None: vlr += rec["volume"]["ratio"]; nvl += 1
    if not n:
        return None
    return {"H": H, "level": level, "n": n, "containment": round(hit / n, 4),
            "meanRangeRatio": round(rr / nrr, 3) if nrr else None,
            "meanVolRatio": round(vrt / nvr, 3) if nvr else None,
            "meanVolumeRatio": round(vlr / nvl, 3) if nvl else None}
