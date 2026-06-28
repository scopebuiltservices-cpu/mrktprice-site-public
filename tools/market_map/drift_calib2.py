#!/usr/bin/env python3
"""
drift_calib2.py — MASTER drift calibration: a point-in-time, OOS-gated, two-factor predictive regression.

Replaces the single reversion shrink (drift_calib v1) with the correct econometric object:
    E[r_{t->t+H} | x_t] = alpha + beta_rev * gap_t + beta_mom * mom_t
where gap_t = log(SMA_win/price)  (reversion-to-fair-value signal, point-in-time)
      mom_t = log(price/price_{t-mwin})  (trailing momentum signal, point-in-time)
      r     = log(price_{t+H}/price_t)   (realized H-day forward return)

Rigor implemented (pure-stdlib, unit-tested on planted structure):
  * RIDGE shrinkage of the slope coefficients toward 0 (intercept unpenalized) — honest at low signal/noise.
  * NEWEY-WEST (HAC) standard errors with lag = H-1 — overlapping H-day returns are serially correlated.
  * PURGED, EMBARGOED WALK-FORWARD OOS R^2 (Campbell-Thompson) — drop H rows around the split so test
    returns do not overlap the training window; the production betas are GATED to 0 when OOS R^2 <= 0
    (no validated edge => flat central path is the honest output, not a UI default).
Returns alpha/beta_rev/beta_mom + HAC t-stats + oosR2 + hitRate + n + gated, ready to wire into the cone.
"""
import math
__all__ = ["robust_z", "ridge_fit", "predict", "newey_west_t", "build_rows", "walk_forward_oos", "calibrate"]


def _solve(A, b):
    """Solve A x = b for small symmetric A via Gaussian elimination (k<=4). Returns None if singular."""
    n = len(A); M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-15:
            return None
        M[c], M[p] = M[p], M[c]
        pv = M[c][c]
        for j in range(c, n + 1):
            M[c][j] /= pv
        for r in range(n):
            if r != c and abs(M[r][c]) > 0:
                f = M[r][c]
                for j in range(c, n + 1):
                    M[r][j] -= f * M[c][j]
    return [M[i][n] for i in range(n)]


def robust_z(xs):
    v = [x for x in xs if x is not None and x == x]
    if len(v) < 3:
        return [0.0 for _ in xs]
    s = sorted(v); n = len(s); med = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    ad = sorted(abs(x - med) for x in v); mad = ad[len(ad) // 2] if len(ad) % 2 else (ad[len(ad) // 2 - 1] + ad[len(ad) // 2]) / 2
    sc = 1.4826 * mad or 1.0
    return [((x - med) / sc if (x is not None and x == x) else 0.0) for x in xs]


def ridge_fit(X, y, lam=1.0):
    """Ridge with UNpenalized intercept. X rows = [1, gap, mom]. Returns [alpha, beta_rev, beta_mom]."""
    k = len(X[0]); A = [[0.0] * k for _ in range(k)]; b = [0.0] * k
    for xi, yi in zip(X, y):
        for a in range(k):
            b[a] += xi[a] * yi
            for c in range(k):
                A[a][c] += xi[a] * xi[c]
    for j in range(1, k):
        A[j][j] += lam            # shrink slopes toward 0, not the intercept
    sol = _solve(A, b)
    return sol if sol else [0.0] * k


def predict(beta, xi):
    return sum(b * x for b, x in zip(beta, xi))


def newey_west_t(X, y, beta, L):
    """HAC (Newey-West, Bartlett) t-stats for overlapping returns. Returns t per coefficient."""
    n = len(X); k = len(beta)
    e = [y[i] - predict(beta, X[i]) for i in range(n)]
    XtX = [[0.0] * k for _ in range(k)]
    for xi in X:
        for a in range(k):
            for c in range(k):
                XtX[a][c] += xi[a] * xi[c]
    # meat S = sum_l w_l (Gamma_l + Gamma_l')
    S = [[0.0] * k for _ in range(k)]
    def gamma(l):
        G = [[0.0] * k for _ in range(k)]
        for t in range(l, n):
            for a in range(k):
                for c in range(k):
                    G[a][c] += X[t][a] * e[t] * e[t - l] * X[t - l][c]
        return G
    G0 = gamma(0)
    for a in range(k):
        for c in range(k):
            S[a][c] += G0[a][c]
    for l in range(1, L + 1):
        w = 1.0 - l / (L + 1.0); Gl = gamma(l)
        for a in range(k):
            for c in range(k):
                S[a][c] += w * (Gl[a][c] + Gl[c][a])
    # Var(beta) = XtX^{-1} S XtX^{-1}
    inv = _inv(XtX)
    if inv is None:
        return [0.0] * k
    M = _matmul(_matmul(inv, S), inv)
    return [(beta[j] / math.sqrt(M[j][j]) if M[j][j] > 1e-18 else 0.0) for j in range(k)]


def _inv(A):
    n = len(A); M = [A[i][:] + [1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-15:
            return None
        M[c], M[p] = M[p], M[c]; pv = M[c][c]
        for j in range(2 * n):
            M[c][j] /= pv
        for r in range(n):
            if r != c:
                f = M[r][c]
                for j in range(2 * n):
                    M[r][j] -= f * M[c][j]
    return [row[n:] for row in M]


def _matmul(A, B):
    n = len(A); m = len(B[0]); p = len(B)
    return [[sum(A[i][k] * B[k][j] for k in range(p)) for j in range(m)] for i in range(n)]


def build_rows(closes, H=20, win=20, mwin=21):
    """Point-in-time [1, gap, mom] design rows + realized fwd return, for one name."""
    c = [x for x in closes if x is not None and x == x and x > 0]
    X = []; y = []
    lo = max(win - 1, mwin)
    if len(c) < lo + H + 1:
        return X, y
    for t in range(lo, len(c) - H):
        sma = sum(c[t - win + 1:t + 1]) / win
        if sma <= 0 or c[t - mwin] <= 0:
            continue
        gap = math.log(sma / c[t]); mom = math.log(c[t] / c[t - mwin])
        X.append([1.0, gap, mom]); y.append(math.log(c[t + H] / c[t]))
    return X, y


def walk_forward_oos(X, y, H, lam=1.0, split=0.7):
    """Purged/embargoed walk-forward OOS R^2 (Campbell-Thompson). Train on first `split`, purge H, test rest."""
    n = len(y)
    if n < 40:
        return {"oosR2": float("nan"), "hit": float("nan"), "nTest": 0}
    cut = int(n * split); tr_end = cut - H
    if tr_end < 20 or cut + 1 >= n:
        return {"oosR2": float("nan"), "hit": float("nan"), "nTest": 0}
    Xtr, ytr = X[:tr_end], y[:tr_end]; Xte, yte = X[cut:], y[cut:]
    beta = ridge_fit(Xtr, ytr, lam)
    ybar = sum(ytr) / len(ytr)
    sse_m = 0.0; sse_0 = 0.0; hit = 0; nt = 0
    for xi, yi in zip(Xte, yte):
        p = predict(beta, xi)
        sse_m += (yi - p) ** 2; sse_0 += (yi - ybar) ** 2
        if (p - ybar) * (yi - ybar) > 0:
            hit += 1
        nt += 1
    return {"oosR2": (1 - sse_m / sse_0) if sse_0 > 0 else float("nan"),
            "hit": hit / nt if nt else float("nan"), "nTest": nt}


def calibrate(closes_by_name, H=20, win=20, mwin=21, lam=4.0):
    """Pool point-in-time rows across the universe, fit ridge, HAC t-stats, OOS-gate.
    GATED betas (returned to production) are zeroed when OOS R^2 <= 0 (no validated edge => flat path)."""
    X = []; y = []; perName = []
    for closes in (closes_by_name or []):
        Xi, yi = build_rows(closes, H, win, mwin)
        if Xi:
            perName.append((Xi, yi)); X.extend(Xi); y.extend(yi)
    if len(y) < 60:
        return {"alpha": 0.0, "betaRev": 0.0, "betaMom": 0.0, "tRev": float("nan"),
                "tMom": float("nan"), "oosR2": float("nan"), "hit": float("nan"), "n": len(y), "gated": True}
    beta = ridge_fit(X, y, lam)
    tt = newey_west_t(X, y, beta, max(1, H - 1))
    # pooled OOS across names (each name purged independently), aggregate R^2
    sse_m = 0.0; sse_0 = 0.0; hit = 0; nt = 0
    for Xi, yi in perName:
        wf = walk_forward_oos(Xi, yi, H, lam)
        # recompute contributions from this name's test block
        n = len(yi)
        if n < 40:
            continue
        cut = int(n * 0.7); tr_end = cut - H
        if tr_end < 20 or cut + 1 >= n:
            continue
        b = ridge_fit(Xi[:tr_end], yi[:tr_end], lam); ybar = sum(yi[:tr_end]) / tr_end
        for xi, yv in zip(Xi[cut:], yi[cut:]):
            p = predict(b, xi); sse_m += (yv - p) ** 2; sse_0 += (yv - ybar) ** 2
            if (p - ybar) * (yv - ybar) > 0:
                hit += 1
            nt += 1
    oosR2 = (1 - sse_m / sse_0) if sse_0 > 0 else float("nan")
    sig = (tt[1] == tt[1] and abs(tt[1]) > 1.96) or (tt[2] == tt[2] and abs(tt[2]) > 1.96)
    gated = not (oosR2 == oosR2 and oosR2 > 0 and sig)   # need BOTH positive OOS R^2 AND HAC significance
    return {"alpha": round(beta[0], 6),
            "betaRev": 0.0 if gated else round(beta[1], 6),
            "betaMom": 0.0 if gated else round(beta[2], 6),
            "tRev": round(tt[1], 3), "tMom": round(tt[2], 3),
            "oosR2": (round(oosR2, 5) if oosR2 == oosR2 else None),
            "hit": (round(hit / nt, 4) if nt else None), "n": len(y), "sig": bool(sig), "gated": gated}
