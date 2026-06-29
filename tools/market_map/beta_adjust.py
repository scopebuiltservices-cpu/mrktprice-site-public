#!/usr/bin/env python3
"""beta_adjust.py — econometrically correct market beta: Dimson (non-synchronous) + Vasicek (shrinkage).

Raw OLS beta is (a) attenuated by errors-in-variables and (b) downward-biased for less-liquid names that
react to the market with a lag (non-synchronous trading). Two standard corrections, verified:

  Dimson (1979):   regress rᵢ on [r_m(t-1), r_m(t), r_m(t+1)] and SUM the coefficients -> β_dimson.
                   Recovers the true loading when a stock's reaction is spread across adjacent days.
  Vasicek (1973):  shrink each name's beta toward the cross-sectional mean, weighted by precision:
                   wᵢ = σ²_cross / (σ²_cross + se²ᵢ);  β_adj = wᵢ·βᵢ + (1-wᵢ)·β̄.
                   Noisy (high-SE) betas shrink more — a proper empirical-Bayes estimator.
  Bloomberg 2/3:   β_adj = (2/3)·β_raw + (1/3)·1   — the fixed-weight fallback when SEs are unavailable.

Pure stdlib; planted-tested. Research only, not advice."""
import math


def ols_beta_se(y, x):
    """Simple OLS slope of y on x with the classical slope standard error. Returns (beta, se)."""
    n = len(y)
    if n < 3 or n != len(x):
        return (float("nan"), float("nan"))
    mx = sum(x) / n; my = sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx <= 0:
        return (float("nan"), float("nan"))
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    b = sxy / sxx
    a = my - b * mx
    sse = sum((y[i] - (a + b * x[i])) ** 2 for i in range(n))
    s2 = sse / (n - 2) if n > 2 else float("nan")
    se = math.sqrt(s2 / sxx) if (s2 == s2 and s2 >= 0) else float("nan")
    return (b, se)


def dimson_beta(y, mkt, lags=1, leads=1):
    """Dimson summed beta: regress y on contemporaneous + `lags` lagged + `leads` led market returns,
    multivariate OLS, and sum the market coefficients. Falls back to OLS beta if the system is degenerate."""
    n = len(y)
    if n != len(mkt) or n < (lags + leads + 5):
        return ols_beta_se(y, mkt)[0]
    # align: for index t we need mkt[t-lags .. t+leads]; valid t in [lags, n-1-leads]
    rows = []; ys = []
    for t in range(lags, n - leads):
        feat = [mkt[t - k] for k in range(lags, 0, -1)] + [mkt[t]] + [mkt[t + k] for k in range(1, leads + 1)]
        rows.append([1.0] + feat); ys.append(y[t])
    coef = _ols_multi(rows, ys)
    if coef is None:
        return ols_beta_se(y, mkt)[0]
    return sum(coef[1:])                                  # drop intercept, sum the market loadings


def _ols_multi(X, y):
    """Normal-equations multivariate OLS (X already includes the intercept column). Returns coef list or None."""
    k = len(X[0]); n = len(X)
    XtX = [[0.0] * k for _ in range(k)]; Xty = [0.0] * k
    for i in range(n):
        xi = X[i]
        for a in range(k):
            Xty[a] += xi[a] * y[i]
            for b in range(k):
                XtX[a][b] += xi[a] * xi[b]
    # Gauss-Jordan solve
    M = [row[:] + [Xty[r]] for r, row in enumerate(XtX)]
    for c in range(k):
        piv = max(range(c, k), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-12:
            return None
        M[c], M[piv] = M[piv], M[c]
        pv = M[c][c]
        M[c] = [v / pv for v in M[c]]
        for r in range(k):
            if r != c and abs(M[r][c]) > 0:
                f = M[r][c]
                M[r] = [M[r][j] - f * M[c][j] for j in range(k + 1)]
    return [M[r][k] for r in range(k)]


def bloomberg_adjust(beta_raw, w=2.0 / 3.0, prior=1.0):
    return w * beta_raw + (1.0 - w) * prior


def vasicek(betas, ses, prior=None):
    """Cross-sectional Vasicek shrinkage. betas/ses are aligned lists. prior=None -> cross-sectional mean.
    Returns the list of shrunk betas. Names with NaN se fall back to the Bloomberg 2/3 rule."""
    good = [b for b, s in zip(betas, ses) if b == b]
    if not good:
        return list(betas)
    bbar = (sum(good) / len(good)) if prior is None else prior
    m = sum(good) / len(good)
    var_cross = (sum((b - m) ** 2 for b in good) / (len(good) - 1)) if len(good) > 1 else 0.0
    out = []
    for b, s in zip(betas, ses):
        if b != b:
            out.append(b); continue
        if s == s and s > 0 and var_cross > 0:
            w = var_cross / (var_cross + s * s)
            out.append(w * b + (1.0 - w) * bbar)
        else:
            out.append(bloomberg_adjust(b, prior=bbar))
    return out


def adjusted_betas(returns_by_name, mkt, prior=1.0, lags=1, leads=1):
    """End-to-end: Dimson per name -> SE per name -> Vasicek shrinkage toward `prior`.
    returns_by_name: {name: [returns]} aligned to mkt. Returns {name: adjusted_beta}."""
    names = list(returns_by_name.keys())
    dimson = {}; ses = {}
    for nm in names:
        y = returns_by_name[nm]
        dimson[nm] = dimson_beta(y, mkt, lags, leads)
        ses[nm] = ols_beta_se(y, mkt)[1]                  # SE from the simple regression (precision proxy)
    bl = [dimson[nm] for nm in names]; sl = [ses[nm] for nm in names]
    shr = vasicek(bl, sl, prior=prior)
    return {names[i]: shr[i] for i in range(len(names))}
