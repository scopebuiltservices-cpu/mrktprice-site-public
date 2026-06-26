#!/usr/bin/env python3
"""log-HARQ + regime realized-volatility forecaster — the FREE, no-GPU benchmark the frontier
papers measure their neural nets against.

  Corsi (2009) HAR-RV   : log RV_t = b0 + b1 log RV_{t-1} + b2 log RV_{t-5:t-1} + b3 log RV_{t-22:t-1}
  Bollerslev-Patton-Quaedvlieg (2016) HARQ : + b4 log RQ_{t-1}   (realized-quarticity measurement-error term)
  Fang-Slepaczuk (2026) regime augmentation: + b5 p^HV_{t-1}     (filtered high-volatility-regime probability)

Estimated by OLS. DAILY-RV approximation: RV_t = r_t^2 from daily closes (no intraday feed needed);
RQ is a short rolling-window r^4 proxy; p^HV is a robust-z logistic on trailing log-RV. Every input
at time t uses information strictly before t (no look-ahead). Pure stdlib. Research only — not advice.
"""
import math

FLOOR = 1e-12


def _ols(X, y):
    """Normal equations + Gauss-Jordan inverse. Returns (beta, r2) or None if singular."""
    n = len(X); p = len(X[0])
    XtX = [[0.0] * p for _ in range(p)]; Xty = [0.0] * p
    for i in range(n):
        xi = X[i]; yi = y[i]
        for a in range(p):
            Xty[a] += xi[a] * yi
            xa = xi[a]
            row = XtX[a]
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
        A[c], A[pv] = A[pv], A[c]
        d = A[c][c]
        for j in range(2 * p):
            A[c][j] /= d
        for r in range(p):
            if r == c:
                continue
            f = A[r][c]
            for j in range(2 * p):
                A[r][j] -= f * A[c][j]
    inv = [row[p:] for row in A]
    beta = [sum(inv[a][b] * Xty[b] for b in range(p)) for a in range(p)]
    ybar = sum(y) / n
    sst = sum((v - ybar) ** 2 for v in y) or 1e-300
    sse = 0.0
    for i in range(n):
        yh = sum(X[i][a] * beta[a] for a in range(p))
        sse += (y[i] - yh) ** 2
    return beta, 1.0 - sse / sst


def _logrets(closes):
    out = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0 and closes[i] > 0:
            out.append(math.log(closes[i] / closes[i - 1]))
        else:
            out.append(0.0)
    return out


def _median(xs):
    s = sorted(xs); n = len(s)
    return 0.0 if not n else (s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2]))


def _mad(xs, m):
    return 1.4826 * _median([abs(x - m) for x in xs]) if xs else 0.0


def harq_regime_forecast(closes, ann=252):
    """Fit log-HARQ+regime on the daily RV series and forecast next-period RV/vol. Returns a dict
    of {volForecastAnn, rvForecast, curVolAnn, cur20VolAnn, r2, n, beta, labels, comp, phvNow} or None."""
    r = _logrets(closes)
    if len(r) < 60:
        return None
    rv = [max(rr * rr, FLOOR) for rr in r]                      # daily realized variance proxy
    n = len(rv)
    lrv = [math.log(v) for v in rv]

    def rq_proxy(t):                                            # rolling realized quarticity (daily proxy)
        w = r[max(0, t - 4):t + 1]; m = len(w)
        return max((m / 3.0) * sum(x ** 4 for x in w), FLOOR) if m else FLOOR

    def p_hv(t):                                               # filtered high-vol-regime probability (info < t)
        hist = lrv[max(0, t - 120):t]
        if len(hist) < 20:
            return 0.5
        m = _median(hist); sd = _mad(hist, m) or 1e-9
        return 1.0 / (1.0 + math.exp(-(lrv[t] - m) / sd))

    X = []; Y = []
    for t in range(22, n):                                     # predict RV_t from lags ending t-1
        rvd = rv[t - 1]
        rvw = sum(rv[t - 5:t]) / 5.0
        rvm = sum(rv[t - 22:t]) / 22.0
        X.append([1.0, math.log(rvd), math.log(max(rvw, FLOOR)), math.log(max(rvm, FLOOR)),
                  math.log(rq_proxy(t - 1)), p_hv(t - 1)])
        Y.append(lrv[t])
    if len(X) < 30:
        return None
    fit = _ols(X, Y)
    if not fit:
        return None
    beta, r2 = fit

    rvd = rv[n - 1]; rvw = sum(rv[n - 5:n]) / 5.0; rvm = sum(rv[n - 22:n]) / 22.0
    xf = [1.0, math.log(rvd), math.log(max(rvw, FLOOR)), math.log(max(rvm, FLOOR)),
          math.log(rq_proxy(n - 1)), p_hv(n - 1)]
    rv_f = math.exp(sum(xf[a] * beta[a] for a in range(len(beta))))
    vol_daily = math.sqrt(rv_f)
    return {
        "rvForecast": rv_f,
        "volForecastAnn": vol_daily * math.sqrt(ann) * 100.0,
        "volDaily": vol_daily,
        "curVolAnn": math.sqrt(rv[n - 1]) * math.sqrt(ann) * 100.0,
        "cur20VolAnn": math.sqrt(sum(rv[n - 20:n]) / 20.0) * math.sqrt(ann) * 100.0,
        "r2": r2, "n": len(X), "beta": beta, "phvNow": xf[5],
        "comp": {"rvD": rvd, "rvW": rvw, "rvM": rvm, "rqNow": math.exp(xf[4])},
        "labels": ["const", "log RVd", "log RVw", "log RVm", "log RQ", "p(high-vol)"],
    }


__all__ = ["harq_regime_forecast"]
