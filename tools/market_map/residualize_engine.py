"""residualize_engine.py — strip hidden factor bets from a raw alpha (Fama-French residualization).

r_{i,t} = a_i + B_i . f_t + e_{i,t}   (time-series regression of name EXCESS return on FF factors)
mu_resid_i = alpha_raw_i - H * (B_i . lambda)    where lambda = per-period factor premia, H = horizon.

The residual alpha is the part of the forecast NOT explained by compensated factor exposure (market,
size, value, profitability, investment, momentum) — i.e. genuine selection edge. Pure stdlib; verified
against planted structure; 1:1 JS port for the browser. Research only, not advice."""
import math

FACTORS = ["MktRF", "SMB", "HML", "RMW", "CMA", "Mom"]
__all__ = ["multivar_ols", "factor_betas", "factor_premia", "residualize", "FACTORS"]


def _solve(A, b):
    """Solve A x = b (A is n x n, symmetric PD here) by Gaussian elimination w/ partial pivoting."""
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-15:
            return None
        M[c], M[p] = M[p], M[c]
        piv = M[c][c]
        for r in range(n):
            if r == c:
                continue
            f = M[r][c] / piv
            if f != 0.0:
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def multivar_ols(X, y, ridge=1e-8):
    """OLS with a tiny ridge for numerical stability. X: T rows each length K (NO intercept added here —
    pass it explicitly as a column of 1s if wanted). Returns {coef:[K], residSd, r2, n}."""
    T = len(y)
    if T == 0 or not X:
        return {"coef": [0.0] * (len(X[0]) if X else 0), "residSd": 0.0, "r2": 0.0, "n": 0}
    K = len(X[0])
    XtX = [[0.0] * K for _ in range(K)]
    Xty = [0.0] * K
    for t in range(T):
        xt = X[t]
        for i in range(K):
            Xty[i] += xt[i] * y[t]
            xi = xt[i]
            row = XtX[i]
            for j in range(K):
                row[j] += xi * xt[j]
    for i in range(K):
        XtX[i][i] += ridge
    coef = _solve(XtX, Xty)
    if coef is None:
        coef = [0.0] * K
    ybar = sum(y) / T
    sse = 0.0
    sst = 0.0
    for t in range(T):
        pred = sum(coef[i] * X[t][i] for i in range(K))
        sse += (y[t] - pred) ** 2
        sst += (y[t] - ybar) ** 2
    dof = max(1, T - K)
    resid_sd = math.sqrt(sse / dof)
    r2 = (1.0 - sse / sst) if sst > 0 else 0.0
    return {"coef": coef, "residSd": resid_sd, "r2": r2, "n": T}


def factor_betas(name_excess, factor_rows, factors=FACTORS, ridge=1e-8):
    """Time-series regression of name excess returns on the FF factors (with intercept).
    factor_rows: list of dicts (aligned with name_excess) carrying the factor keys.
    Returns {alpha, betas:{factor:beta}, residSd, r2, n}. Rows with any missing field are dropped."""
    X, y = [], []
    for r, ne in zip(factor_rows, name_excess):
        if ne is None:
            continue
        vals = [r.get(f) for f in factors]
        if any(v is None for v in vals):
            continue
        X.append([1.0] + vals)
        y.append(ne)
    if len(y) < len(factors) + 2:
        return {"alpha": 0.0, "betas": {f: 0.0 for f in factors}, "residSd": 0.0, "r2": 0.0, "n": len(y)}
    res = multivar_ols(X, y, ridge)
    c = res["coef"]
    return {"alpha": c[0], "betas": {factors[i]: c[i + 1] for i in range(len(factors))},
            "residSd": res["residSd"], "r2": res["r2"], "n": res["n"]}


def factor_premia(factor_rows, factors=FACTORS, halflife=None):
    """Per-period factor premia lambda_k. Simple mean, or EWMA (more weight on recent) if halflife set."""
    out = {}
    for f in factors:
        vals = [r.get(f) for r in factor_rows if r.get(f) is not None]
        if not vals:
            out[f] = 0.0
            continue
        if halflife and halflife > 0:
            lam = 0.5 ** (1.0 / halflife)
            num = den = 0.0
            w = 1.0
            for v in reversed(vals):          # most recent gets weight 1
                num += w * v
                den += w
                w *= lam
            out[f] = num / den if den > 0 else 0.0
        else:
            out[f] = sum(vals) / len(vals)
    return out


def residualize(alpha_raw, betas, premia, horizon=21, factors=FACTORS):
    """mu_resid = alpha_raw - H * sum_k beta_k * lambda_k. alpha_raw and the result are expected returns
    over the horizon (same units as the board's alpha). Returns the decomposition for transparency."""
    factor_expected = horizon * sum((betas.get(f, 0.0)) * (premia.get(f, 0.0)) for f in factors)
    return {"muResid": alpha_raw - factor_expected, "alphaRaw": alpha_raw,
            "factorExpected": factor_expected,
            "contrib": {f: horizon * betas.get(f, 0.0) * premia.get(f, 0.0) for f in factors}}
