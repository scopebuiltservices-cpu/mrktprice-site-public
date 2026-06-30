#!/usr/bin/env python3
"""
drift_calib3.py — drift v2 FRONTIER: regime-conditional coefficients + Driscoll-Kraay panel SE + CRPS/PIT.

Extends drift_calib2's predictive regression E[r_{t->t+H}|x] = a + bRev*gap + bMom*mom with the three
upgrades that make it a correct PANEL forecast:

  1. REGIME-CONDITIONAL beta (interaction): add gap*R and mom*R where R = 1 in a TRENDING regime
     (Kaufman efficiency ratio > thr), 0 in a RANGE-BOUND regime. Effective loadings:
        range : revR = bRev,           momR = bMom
        trend : revT = bRev + gRev,    momT = bMom + gMom
     -> reversion can dominate range-bound regimes and momentum the trends, learned from data.
  2. DRISCOLL-KRAAY standard errors: HAC over time AFTER aggregating the score x_it*e_it across the
     cross-section at each date -> robust to BOTH serial correlation (overlapping H-day returns) AND
     cross-sectional dependence (names cluster in calendar time). t-stats use these, not naive OLS.
  3. CRPS + PIT scoring: proper scoring of the Gaussian predictive forecast on OUT-OF-SAMPLE outcomes
     (closed-form CRPS) and a PIT-uniformity KS statistic (calibration). The drift turns on only when the
     OOS R^2 > 0 AND a factor is DK-significant; CRPS/PIT track whether it stays calibrated.

Pure stdlib; unit-tested on planted structure (coefficient recovery, DK inflation under cross-sectional
dependence, CRPS/PIT correctness, regime separation, honest gating of a random walk).
"""
import math
__all__ = ["efficiency_ratio", "ridge_fit", "predict", "driscoll_kraay_t", "crps_gaussian",
           "pit_gaussian", "ks_uniform", "build_rows3", "calibrate3"]


def _phi(x): return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)
def _Phi(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _inv(A):
    n = len(A); M = [A[i][:] + [1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-300:
            return None
        M[c], M[p] = M[p], M[c]; d = M[c][c]
        for j in range(2 * n):
            M[c][j] /= d
        for r in range(n):
            if r != c:
                f = M[r][c]
                for j in range(2 * n):
                    M[r][j] -= f * M[c][j]
    return [row[n:] for row in M]


def _matmul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(len(B))) for j in range(len(B[0]))] for i in range(len(A))]


def ridge_fit(X, y, lam=1.0):
    k = len(X[0]); A = [[0.0] * k for _ in range(k)]; b = [0.0] * k
    for xi, yi in zip(X, y):
        for a in range(k):
            b[a] += xi[a] * yi
            for c in range(k):
                A[a][c] += xi[a] * xi[c]
    for j in range(1, k):
        A[j][j] += lam
    inv = _inv(A)
    if inv is None:
        return [0.0] * k
    return [sum(inv[a][c] * b[c] for c in range(k)) for a in range(k)]


def predict(beta, xi): return sum(b * x for b, x in zip(beta, xi))


def efficiency_ratio(closes, t, n):
    """Kaufman efficiency ratio in [0,1] at t over n bars: |net move| / sum|bar moves|. High => trending."""
    if t - n < 0:
        return 0.0
    net = abs(closes[t] - closes[t - n])
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(t - n + 1, t + 1)) or 1e-12
    return net / path


def driscoll_kraay_t(X, y, beta, tidx, L):
    """Driscoll-Kraay t-stats. tidx[i] = integer time index of obs i (shared across names). Aggregates the
    score x_i*e_i across the cross-section at each date, then Bartlett-HAC over the distinct dates."""
    n = len(X); k = len(beta)
    e = [y[i] - predict(beta, X[i]) for i in range(n)]
    XtX = [[0.0] * k for _ in range(k)]
    for xi in X:
        for a in range(k):
            for c in range(k):
                XtX[a][c] += xi[a] * xi[c]
    # h_t = sum over units at time t of x_it * e_it
    H = {}
    for i in range(n):
        t = tidx[i]; v = H.get(t)
        if v is None:
            v = [0.0] * k; H[t] = v
        for a in range(k):
            v[a] += X[i][a] * e[i]
    times = sorted(H)
    hs = [H[t] for t in times]; T = len(hs)
    def gamma(l):
        G = [[0.0] * k for _ in range(k)]
        for s in range(l, T):
            for a in range(k):
                for c in range(k):
                    G[a][c] += hs[s][a] * hs[s - l][c]
        return G
    S = [[0.0] * k for _ in range(k)]; G0 = gamma(0)
    for a in range(k):
        for c in range(k):
            S[a][c] += G0[a][c]
    for l in range(1, min(L, T - 1) + 1):
        w = 1.0 - l / (L + 1.0); Gl = gamma(l)
        for a in range(k):
            for c in range(k):
                S[a][c] += w * (Gl[a][c] + Gl[c][a])
    inv = _inv(XtX)
    if inv is None:
        return [0.0] * k
    V = _matmul(_matmul(inv, S), inv)
    return [(beta[j] / math.sqrt(V[j][j]) if V[j][j] > 1e-18 else 0.0) for j in range(k)]


def crps_gaussian(mu, sigma, y):
    """Closed-form CRPS of a Gaussian predictive N(mu,sigma) vs outcome y (lower is better)."""
    if sigma <= 0:
        return abs(y - mu)
    z = (y - mu) / sigma
    return sigma * (z * (2 * _Phi(z) - 1) + 2 * _phi(z) - 1 / math.sqrt(math.pi))


def pit_gaussian(mu, sigma, y):
    return _Phi((y - mu) / sigma) if sigma > 0 else (1.0 if y >= mu else 0.0)


def ks_uniform(us):
    """KS statistic of a sample vs Uniform(0,1) — PIT calibration (0 = perfectly calibrated)."""
    s = sorted(u for u in us if u == u)
    n = len(s)
    if n == 0:
        return float("nan")
    d = 0.0
    for i, u in enumerate(s):
        d = max(d, abs((i + 1) / n - u), abs(u - i / n))
    return d


def build_rows3(closes, H=20, win=20, mwin=21, ern=20, er_thr=0.5, dates=None):
    """Point-in-time rows [1, gap, mom, gap*R, mom*R] + realized + time index + regime R.

    The time index feeds Driscoll-Kraay cross-sectional aggregation, which is only valid when the index is a
    SHARED CALENDAR date across names. If `dates` (an ordinal/integer trading-date code aligned to `closes`,
    comparable across names) is supplied, we emit the real date code so DK clusters genuine common dates.
    Otherwise we fall back to bars-from-end (N-1-t), which only coincides with calendar time when every name
    has identical length and no gaps — a fragile assumption flagged by the caller as a pseudo-panel HAC."""
    cz = [(x, (dates[i] if dates is not None and i < len(dates) else None))
          for i, x in enumerate(closes) if x is not None and x == x and x > 0]
    c = [x for x, _ in cz]; dc = [d for _, d in cz]
    X = []; y = []; tt = []; reg = []
    lo = max(win - 1, mwin, ern)
    if len(c) < lo + H + 1:
        return X, y, tt, reg
    N = len(c)
    have_dates = dates is not None and all(d is not None for d in dc)
    for t in range(lo, N - H):
        sma = sum(c[t - win + 1:t + 1]) / win
        if sma <= 0 or c[t - mwin] <= 0:
            continue
        gap = math.log(sma / c[t]); mom = math.log(c[t] / c[t - mwin])
        R = 1.0 if efficiency_ratio(c, t, ern) > er_thr else 0.0
        X.append([1.0, gap, mom, gap * R, mom * R]); y.append(math.log(c[t + H] / c[t]))
        tt.append(dc[t] if have_dates else (N - 1) - t); reg.append(R)
    return X, y, tt, reg


def calibrate3(closes_by_name, H=20, win=20, mwin=21, lam=6.0, dates_by_name=None):
    """Pool regime-interacted rows across the universe; ridge fit; Driscoll-Kraay t-stats; purged
    walk-forward OOS R^2 + CRPS + PIT-KS; gate the regime-conditional betas on OOS edge AND DK significance.

    Pass `dates_by_name` (a list of per-name ordinal trading-date codes aligned to each closes series, shared
    across names) to get genuine calendar-aligned Driscoll-Kraay. Without it the time index is bars-from-end
    and the covariance is honestly a PSEUDO-PANEL HAC approximation (flagged via tidxKind/dkLabel)."""
    X = []; y = []; tt = []; per = []
    have_dates = bool(dates_by_name) and len(dates_by_name) == len(closes_by_name or [])
    for k, closes in enumerate(closes_by_name or []):
        di = dates_by_name[k] if have_dates else None
        Xi, yi, ti, ri = build_rows3(closes, H, win, mwin, dates=di)
        if Xi:
            per.append((Xi, yi)); X.extend(Xi); y.extend(yi); tt.extend(ti)
    if len(y) < 80:
        return {"gated": True, "n": len(y), "alpha": 0.0, "betaRev": 0.0, "betaMom": 0.0,
                "gRev": 0.0, "gMom": 0.0, "oosR2": None, "crps": None, "pitKS": None}
    beta = ridge_fit(X, y, lam)
    dk = driscoll_kraay_t(X, y, beta, tt, max(1, H - 1))
    # purged walk-forward OOS across names; accumulate R^2, CRPS, PIT
    sse_m = sse_0 = 0.0; crps_sum = 0.0; nt = 0; pits = []
    for Xi, yi in per:
        n = len(yi)
        if n < 50:
            continue
        cut = int(n * 0.7); tr_end = cut - H
        if tr_end < 25 or cut + 1 >= n:
            continue
        b = ridge_fit(Xi[:tr_end], yi[:tr_end], lam)
        res = [yi[i] - predict(b, Xi[i]) for i in range(tr_end)]
        m = sum(res) / len(res); sd = (sum((r - m) ** 2 for r in res) / max(1, len(res) - 1)) ** 0.5 or 1e-6
        ybar = sum(yi[:tr_end]) / tr_end
        for i in range(cut, n):
            p = predict(b, Xi[i])
            sse_m += (yi[i] - p) ** 2; sse_0 += (yi[i] - ybar) ** 2
            crps_sum += crps_gaussian(p, sd, yi[i]); pits.append(pit_gaussian(p, sd, yi[i])); nt += 1
    oosR2 = (1 - sse_m / sse_0) if sse_0 > 0 else float("nan")
    crps = (crps_sum / nt) if nt else float("nan")
    pitKS = ks_uniform(pits) if pits else float("nan")
    sig = (dk[1] == dk[1] and abs(dk[1]) > 1.96) or (dk[2] == dk[2] and abs(dk[2]) > 1.96) or \
          (dk[3] == dk[3] and abs(dk[3]) > 1.96) or (dk[4] == dk[4] and abs(dk[4]) > 1.96)
    gated = not (oosR2 == oosR2 and oosR2 > 0 and sig)
    z = lambda v: 0.0 if gated else round(v, 6)
    return {"alpha": round(beta[0], 6), "betaRev": z(beta[1]), "betaMom": z(beta[2]),
            "gRev": z(beta[3]), "gMom": z(beta[4]),
            "revRange": z(beta[1]), "revTrend": z(beta[1] + beta[3]),
            "momRange": z(beta[2]), "momTrend": z(beta[2] + beta[4]),
            "dkT": {"rev": round(dk[1], 3), "mom": round(dk[2], 3), "gRev": round(dk[3], 3), "gMom": round(dk[4], 3)},
            "oosR2": (None if oosR2 != oosR2 else round(oosR2, 5)),
            "crps": (None if crps != crps else round(crps, 6)),
            "pitKS": (None if pitKS != pitKS else round(pitKS, 4)),
            "tidxKind": ("calendar_date" if have_dates else "bars_from_end"),
            "dkLabel": ("Driscoll-Kraay (calendar-aligned)" if have_dates
                        else "pseudo-panel HAC (bars-from-end proxy; NOT date-aligned)"),
            "n": len(y), "nTest": nt, "gated": gated}
