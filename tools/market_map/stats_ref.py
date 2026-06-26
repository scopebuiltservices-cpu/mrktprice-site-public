#!/usr/bin/env python3
"""Python reference for the terminal's stationarity tests — the missing reference behind the
"verified vs Python" claim (code-review H1). ADF (AIC lag selection + MacKinnon 5% critical value,
intercept-only) and KPSS (level, Newey-Westlong-run variance) are implemented here in pure stdlib
with the SAME formulas the dashboard uses in JS, so a golden-fixture test can assert cross-language
agreement instead of an unverifiable comment.

Mirrors terminal.html: _ols, _mackinnonCV, adfTest, _nwlrv, kpssTest. Pure stdlib. Research only.
"""
import math


def ols(X, y):
    """Normal equations + Gauss-Jordan inverse -> (beta, se). Mirrors terminal _ols(X,y)."""
    n = len(X); p = len(X[0])
    XtX = [[0.0] * p for _ in range(p)]; Xty = [0.0] * p
    for i in range(n):
        for a in range(p):
            Xty[a] += X[i][a] * y[i]
            for b in range(p):
                XtX[a][b] += X[i][a] * X[i][b]
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
    sse = 0.0
    for i in range(n):
        yh = sum(X[i][a] * beta[a] for a in range(p))
        sse += (y[i] - yh) ** 2
    s2 = sse / max(1, n - p)
    se = [math.sqrt(max(s2 * inv[a][a], 0.0)) for a in range(p)]
    return beta, se


def mackinnon_cv(T, lvl="5"):
    """MacKinnon (1996) response surface, intercept-only (no trend). Mirrors terminal _mackinnonCV."""
    P = {"1": [-3.43035, -6.5393, -16.786], "5": [-2.86154, -2.8903, -4.234], "10": [-2.56677, -1.5384, -2.809]}
    b = P[lvl]
    return b[0] + b[1] / T + b[2] / (T * T)


def adf(y):
    """Augmented Dickey-Fuller, intercept-only, AIC lag selection. Returns {tstat,lag,cv5,reject}.
    Mirrors terminal adfTest(y)."""
    n = len(y)
    if n < 25:
        return {"tstat": None, "reject": None, "lag": None, "cv5": None}
    dy = [y[i] - y[i - 1] for i in range(1, n)]
    pmax = max(0, min(int(12 * (n / 100.0) ** 0.25), (len(dy) - 2) // 2))
    best = None
    for lag in range(0, pmax + 1):
        X = []; t = []
        for k in range(pmax + 1, len(dy)):
            row = [1.0, y[k]]
            for i in range(1, lag + 1):
                row.append(dy[k - i])
            X.append(row); t.append(dy[k])
        if len(t) < 10:
            continue
        o = ols(X, t)
        if not o:
            continue
        beta = o[0]
        ssr = 0.0
        for i in range(len(t)):
            yh = sum(X[i][j] * beta[j] for j in range(len(X[i])))
            ssr += (t[i] - yh) ** 2
        m = len(t); kk = len(X[0])
        aic = m * math.log(ssr / m + 1e-300) + 2 * kk
        if best is None or aic < best["aic"]:
            best = {"aic": aic, "o": o, "lag": lag}
    if best is None:
        return {"tstat": None, "reject": None, "lag": None, "cv5": None}
    beta, se = best["o"]
    ts = beta[1] / se[1] if se[1] > 0 else 0.0
    T = max(len(dy) - (pmax + 1), 10)                       # regression rows (code-review H3 fix)
    cv5 = mackinnon_cv(T, "5")
    return {"tstat": ts, "lag": best["lag"], "cv5": cv5, "reject": ts < cv5}


def nw_lrv(u):
    """Newey-West long-run variance (Bartlett kernel). Mirrors terminal _nwlrv(u)."""
    n = len(u)
    L = int(4 * (n / 100.0) ** (2.0 / 9.0))
    g0 = sum(x * x for x in u) / n
    s = g0
    for j in range(1, L + 1):
        gj = sum(u[i] * u[i - j] for i in range(j, n)) / n
        s += 2.0 * (1.0 - j / (L + 1.0)) * gj
    return s


def kpss(y):
    """KPSS level-stationarity test. Returns {eta, reject} (5% cv 0.463). Mirrors terminal kpssTest(y)."""
    n = len(y)
    if n < 25:
        return {"eta": None, "reject": None}
    m = sum(y) / n
    e = [v - m for v in y]
    S = 0.0; ss = 0.0
    for v in e:
        S += v; ss += S * S
    lrv = max(1e-300, nw_lrv(e))
    eta = ss / (n * n * lrv)
    return {"eta": eta, "reject": eta > 0.463}


__all__ = ["ols", "mackinnon_cv", "adf", "nw_lrv", "kpss"]
