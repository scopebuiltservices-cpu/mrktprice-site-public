"""dm_test.py — Diebold-Mariano equal-predictive-accuracy test with HLN small-sample correction (stdlib).

band_bakeoff ranks methods by mean interval score, but a lower mean is not a significant difference. The
Diebold-Mariano test (1995) asks whether two forecasts have equal expected loss, using the loss DIFFERENTIAL
d_t = L_a,t - L_b,t and a HAC (Newey-West) long-run variance to handle the serial correlation that h-step
overlapping forecasts induce. Harvey-Leybourne-Newbold (1997) add the small-sample correction and a
Student-t reference distribution, which matters at the modest sample sizes of horizon-H walk-forwards.

    DM   = mean(d) / sqrt( LRV(d) / n ),          LRV = gamma_0 + 2*sum_{k=1}^{h-1} gamma_k   (Newey-West trunc)
    DM*  = DM * sqrt( (n + 1 - 2h + h(h-1)/n) / n ),   compared to t_{n-1}

Sign convention: DM* < 0 (p small) => forecast A has significantly LOWER loss (A is better). Verified in
test_dm_test.py: planted A-better -> significant negative; equal-accuracy -> not significant.
"""
from __future__ import annotations

import math


def _mean(x):
    return sum(x) / len(x) if x else float("nan")


def _autocov(d, k, mu):
    n = len(d)
    return sum((d[t] - mu) * (d[t - k] - mu) for t in range(k, n)) / n


def _t_two_sided_p(t, df):
    """Two-sided p-value of Student-t via the regularized incomplete beta I_x(df/2, 1/2)."""
    if df <= 0 or t != t:
        return float("nan")
    x = df / (df + t * t)
    return _betai(df / 2.0, 0.5, x)


def _betai(a, b, x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(math.log(x) * a + math.log(1.0 - x) * b - lbeta) / a
    return front * _betacf(a, b, x) if x < (a + 1.0) / (a + b + 2.0) else 1.0 - _betai(b, a, 1.0 - x)


def _betacf(a, b, x, itmax=200, eps=3e-12):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    dd = 1.0 - qab * x / qap
    if abs(dd) < 1e-30:
        dd = 1e-30
    dd = 1.0 / dd
    h = dd
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        dd = 1.0 + aa * dd
        if abs(dd) < 1e-30:
            dd = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        dd = 1.0 / dd
        h *= dd * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        dd = 1.0 + aa * dd
        if abs(dd) < 1e-30:
            dd = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        dd = 1.0 / dd
        de = dd * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h


def diebold_mariano(loss_a, loss_b, h: int = 1):
    """DM test on two loss series (same length, aligned). h = forecast horizon (# of overlapping steps).
    Returns dict with the loss-differential mean, DM, HLN-corrected DM*, df, two-sided p, and a verdict.
    Convention: meanDiff/DM negative => A has lower loss (A better)."""
    d = [float(a) - float(b) for a, b in zip(loss_a, loss_b) if a == a and b == b]
    n = len(d)
    if n < 8:
        return {"n": n, "ok": False, "reason": "need >= 8 aligned observations"}
    mu = _mean(d)
    g0 = _autocov(d, 0, mu)
    lrv = g0 + 2.0 * sum(_autocov(d, k, mu) for k in range(1, h))   # Newey-West truncation at h-1
    if lrv <= 0:
        lrv = g0 if g0 > 0 else 1e-12
    dm = mu / math.sqrt(lrv / n)
    corr = math.sqrt(max(1e-9, (n + 1 - 2 * h + h * (h - 1) / n) / n))
    dm_star = dm * corr
    p = _t_two_sided_p(dm_star, n - 1)
    better = "A" if mu < 0 else ("B" if mu > 0 else "tie")
    return {"n": n, "ok": True, "meanDiff": round(mu, 8), "DM": round(dm, 4), "DMstar": round(dm_star, 4),
            "df": n - 1, "pValue": round(p, 6), "significant": bool(p < 0.05),
            "better": (better if p < 0.05 else "none"), "horizon": h}


def compare_methods(loss_by_method: dict, baseline: str, h: int = 1) -> dict:
    """DM-test every method's loss series against a baseline. loss_by_method: {name: [per-step losses]}.
    Returns {name: dm_result} for all names != baseline."""
    base = loss_by_method.get(baseline)
    if base is None:
        return {"error": f"baseline '{baseline}' not in losses"}
    out = {}
    for name, la in loss_by_method.items():
        if name == baseline:
            continue
        out[name] = diebold_mariano(la, base, h=h)   # A=method, B=baseline: DM<0 => method better
    return out
