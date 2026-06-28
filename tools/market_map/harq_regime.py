#!/usr/bin/env python3
"""
HARQ + regime realized-volatility forecaster (Bollerslev-Patton-Quaedvlieg 2016), CORRECTED.

  Corsi (2009) HAR-RV : RV_t = b0 + b1 RV_{t-1} + b2 RV_{w,t-1} + b3 RV_{m,t-1}
  BPQ (2016) HARQ     : the DAILY coefficient is MEASUREMENT-ERROR adjusted ->
                        RV_t = b0 + (b1 + b1Q * sqrtRQ~_{t-1}) RV_{t-1} + b2 RV_w + b3 RV_m
                        where sqrtRQ~ = demeaned sqrt(realized quarticity). When the daily RV is measured
                        noisily (high RQ), b1Q (typically < 0) SHRINKS the daily loading — the whole point
                        of HARQ. The previous build entered log RQ ADDITIVELY (a plain regressor), which is
                        NOT HARQ; this corrects it to the interaction on the daily lag, in LEVELS.
  Regime augmentation : + b4 p^HV_{t-1}  (filtered high-volatility-regime probability).

Estimated by OLS in LEVELS. RV_t = r_t^2 (daily proxy); the HARQ interaction is precisely the correction
for that proxy's measurement noise. Adds: walk-forward OUT-OF-SAMPLE R^2 (vs in-sample) and a split-conformal
quantile on HARQ's OWN out-of-sample residuals (so the cone is calibrated to THIS model, not price returns).
Every input at t uses info strictly before t. Pure stdlib. Research only.
"""
import math
FLOOR = 1e-12
__all__ = ["harq_regime_forecast", "gen_fixture"]


def _ols(X, y):
    n = len(X); p = len(X[0])
    XtX = [[0.0] * p for _ in range(p)]; Xty = [0.0] * p
    for i in range(n):
        xi = X[i]; yi = y[i]
        for a in range(p):
            Xty[a] += xi[a] * yi; xa = xi[a]; row = XtX[a]
            for b in range(p):
                row[b] += xa * xi[b]
    A = [XtX[i][:] + [1.0 if i == j else 0.0 for j in range(p)] for i in range(p)]
    for c in range(p):
        pv = c
        for r in range(c + 1, p):
            if abs(A[r][c]) > abs(A[pv][c]):
                pv = r
        if abs(A[pv][c]) < 1e-300:
            return None
        A[c], A[pv] = A[pv], A[c]; d = A[c][c]
        for j in range(2 * p):
            A[c][j] /= d
        for r in range(p):
            if r == c:
                continue
            f = A[r][c]
            for j in range(2 * p):
                A[r][j] -= f * A[c][j]
    inv = [row[p:] for row in A]
    return [sum(inv[a][b] * Xty[b] for b in range(p)) for a in range(p)]


def _r2(X, y, beta):
    n = len(y); ybar = sum(y) / n; sst = sum((v - ybar) ** 2 for v in y) or 1e-300
    sse = sum((y[i] - sum(X[i][a] * beta[a] for a in range(len(beta)))) ** 2 for i in range(n))
    return 1.0 - sse / sst


def _logrets(closes):
    out = []
    for i in range(1, len(closes)):
        out.append(math.log(closes[i] / closes[i - 1]) if (closes[i - 1] > 0 and closes[i] > 0) else 0.0)
    return out


def _median(xs):
    s = sorted(xs); n = len(s)
    return 0.0 if not n else (s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2]))


def _mad(xs, m):
    return 1.4826 * _median([abs(x - m) for x in xs]) if xs else 0.0


def _quantile(xs, q):
    s = sorted(xs)
    if not s:
        return 0.0
    pos = q * (len(s) - 1); lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (pos - lo)


def harq_regime_forecast(closes, ann=252):
    r = _logrets(closes)
    if len(r) < 60:
        return None
    rv = [max(rr * rr, FLOOR) for rr in r]
    n = len(rv)

    def rq(t):                                  # rolling realized-quarticity proxy (BPQ (N/3) sum r^4)
        w = r[max(0, t - 4):t + 1]; m = len(w)
        return max((m / 3.0) * sum(x ** 4 for x in w), FLOOR) if m else FLOOR

    srq = [math.sqrt(rq(t)) for t in range(n)]
    srq_bar = sum(srq[22:n]) / max(1, (n - 22))         # demean over the estimation window
    def p_hv(t):
        hist = [math.log(rv[i]) for i in range(max(0, t - 120), t)]
        if len(hist) < 20:
            return 0.5
        m = _median(hist); sd = _mad(hist, m) or 1e-9
        return 1.0 / (1.0 + math.exp(-(math.log(rv[t]) - m) / sd))

    def row(t):
        rvd = rv[t - 1]; rvw = sum(rv[t - 5:t]) / 5.0; rvm = sum(rv[t - 22:t]) / 22.0
        sq = srq[t - 1] - srq_bar
        return [1.0, rvd, sq * rvd, rvw, rvm, p_hv(t - 1)]    # (b1 + b1Q*sqrtRQ~)*RVd via [RVd, sqrtRQ~*RVd]

    X = [row(t) for t in range(22, n)]; Y = [rv[t] for t in range(22, n)]
    if len(X) < 30:
        return None
    beta = _ols(X, Y)
    if not beta:
        return None
    r2 = _r2(X, Y, beta)

    # walk-forward OOS R^2 (Campbell-Thompson) + split-conformal on OOS residuals of THIS model
    cut = int(len(X) * 0.7)
    oosR2 = float("nan"); confQ = None
    if cut >= 30 and len(X) - cut >= 10:
        b_tr = _ols(X[:cut], Y[:cut])
        if b_tr:
            ybar = sum(Y[:cut]) / cut; sse_m = 0.0; sse_0 = 0.0; resid = []
            for i in range(cut, len(X)):
                pred = max(sum(X[i][a] * b_tr[a] for a in range(len(b_tr))), FLOOR)
                sse_m += (Y[i] - pred) ** 2; sse_0 += (Y[i] - ybar) ** 2
                sd = math.sqrt(pred) or 1e-9
                resid.append(abs(math.sqrt(Y[i]) - math.sqrt(pred)) / sd)   # standardized vol error
            oosR2 = (1 - sse_m / sse_0) if sse_0 > 0 else float("nan")
            if resid:
                confQ = _quantile(resid, 0.90)                              # 90% conformal multiplier

    xf = [1.0, rv[n - 1], (srq[n - 1] - srq_bar) * rv[n - 1], sum(rv[n - 5:n]) / 5.0, sum(rv[n - 22:n]) / 22.0, p_hv(n - 1)]
    rv_f = max(sum(xf[a] * beta[a] for a in range(len(beta))), FLOOR)
    vol_daily = math.sqrt(rv_f)
    return {
        "rvForecast": rv_f, "volDaily": vol_daily,
        "volForecastAnn": vol_daily * math.sqrt(ann) * 100.0,
        "curVolAnn": math.sqrt(rv[n - 1]) * math.sqrt(ann) * 100.0,
        "cur20VolAnn": math.sqrt(sum(rv[n - 20:n]) / 20.0) * math.sqrt(ann) * 100.0,
        "r2": r2, "oosR2": (None if oosR2 != oosR2 else oosR2), "confQ": confQ,
        "n": len(X), "beta": beta, "b1Q": beta[2], "phvNow": xf[5],
        "comp": {"rvD": rv[n - 1], "rvW": xf[3], "rvM": xf[4], "sqrtRQz": srq[n - 1] - srq_bar},
        "labels": ["const", "RVd", "sqrtRQ~*RVd (HARQ)", "RVw", "RVm", "p(high-vol)"],
    }


def _mul32(seed):
    a = [seed & 0xFFFFFFFF]
    def rnd():
        a[0] = (a[0] + 0x6D2B79F5) & 0xFFFFFFFF
        t = ((a[0] ^ (a[0] >> 15)) * (1 | a[0])) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) ^ t) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0
    return rnd


def gen_fixture():
    r = _mul32(20260628); c = [50.0]; vol = 0.02
    for _ in range(200):
        vol = 0.0001 + 0.94 * vol + 0.05 * (0.02 * (r() - 0.5)) ** 2 * 50   # mild GARCH-ish
        c.append(round(c[-1] * math.exp(math.sqrt(max(vol, 1e-6)) * (r() - 0.5)), 6))
    f = harq_regime_forecast(c)
    return {"fixture_version": 1, "case": "harq-bpq-core", "closes": c, "expected": f}
