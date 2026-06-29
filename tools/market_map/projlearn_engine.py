"""projlearn_engine.py — learn from the daily projClose-vs-priceNow outcomes and RECALIBRATE the forecast.

Each forecast is a predicted log-return over horizon H:  predLR = ln(projClose_H / priceNow).
At maturity we observe the realized log-return:            realLR = ln(actualClose_H / priceNow).
Collected over many days, (predLR, realLR) pairs let us evaluate AND correct the model:

EQUATIONS
---------
1. Mincer-Zarnowitz regression (the standard forecast-optimality test & optimal linear recalibration):
       realLR = α + β·predLR + ε        (OLS)
   A perfect forecast has α=0, β=1. The fitted (α,β) give the optimal linear recalibration:
       predLR* = α + β·predLR
   β<1 ⇒ the raw forecast is too aggressive (shrink); α≠0 ⇒ systematic bias to remove.

2. Skill vs naive (naive = "no change", predLR=0):
       skill = 1 − MSE_model / MSE_naive,   MSE_naive = mean(realLR²)
   skill>0 ⇒ beats the random-walk baseline.

3. Theil's U2 = RMSE_model / RMSE_naive  (U2<1 ⇒ better than naive).

4. Shrinkage of the correction by sample size (trust raw forecast early, learn as evidence accrues):
       w = n/(n+τ);   β' = w·β + (1−w)·1;   α' = w·α       (τ default 12)
   so with little data the correction ≈ identity, and it strengthens as n grows.

Pure stdlib; verified against planted structure; 1:1 JS port. Research only, not advice."""
import math

__all__ = ["mincer_zarnowitz", "recalibrate", "skill_vs_naive", "theil_u2", "bias", "mae",
           "coverage", "learn"]


def _mean(x):
    return sum(x) / len(x) if x else 0.0


def mincer_zarnowitz(pred, realized):
    """OLS realized = a + b*pred. Returns {alpha, beta, r2, n}."""
    n = len(pred)
    if n < 3:
        return {"alpha": 0.0, "beta": 1.0, "r2": 0.0, "n": n}
    mp = _mean(pred); mr = _mean(realized)
    spp = sum((p - mp) ** 2 for p in pred)
    spr = sum((pred[i] - mp) * (realized[i] - mr) for i in range(n))
    beta = spr / spp if spp > 0 else 1.0
    alpha = mr - beta * mp
    sse = sum((realized[i] - (alpha + beta * pred[i])) ** 2 for i in range(n))
    sst = sum((r - mr) ** 2 for r in realized)
    r2 = (1.0 - sse / sst) if sst > 0 else 0.0
    return {"alpha": alpha, "beta": beta, "r2": r2, "n": n}


def recalibrate(pred, alpha, beta):
    return alpha + beta * pred


def skill_vs_naive(pred, realized):
    n = len(pred)
    if n == 0:
        return 0.0
    mse_m = sum((realized[i] - pred[i]) ** 2 for i in range(n)) / n
    mse_n = sum(r * r for r in realized) / n
    return 1.0 - mse_m / mse_n if mse_n > 0 else 0.0


def theil_u2(pred, realized):
    n = len(pred)
    if n == 0:
        return 1.0
    num = math.sqrt(sum((realized[i] - pred[i]) ** 2 for i in range(n)) / n)
    den = math.sqrt(sum(r * r for r in realized) / n)
    return num / den if den > 0 else 1.0


def bias(pred, realized):
    n = len(pred)
    return sum(realized[i] - pred[i] for i in range(n)) / n if n else 0.0


def mae(pred, realized):
    n = len(pred)
    return sum(abs(realized[i] - pred[i]) for i in range(n)) / n if n else 0.0


def coverage(realized, lo, hi):
    n = len(realized)
    if n == 0:
        return None
    return sum(1 for i in range(n) if lo[i] <= realized[i] <= hi[i]) / n


def learn(pred, realized, tau=12, n_min=8):
    """Full scorecard + the shrunk recalibration coefficients to APPLY to new forecasts."""
    mz = mincer_zarnowitz(pred, realized)
    n = mz["n"]
    w = n / (n + tau) if (n + tau) > 0 else 0.0
    a_app = w * mz["alpha"]
    b_app = w * mz["beta"] + (1.0 - w) * 1.0
    return {
        "alpha": round(mz["alpha"], 6), "beta": round(mz["beta"], 4), "r2": round(mz["r2"], 4),
        "skill": round(skill_vs_naive(pred, realized), 4), "theilU2": round(theil_u2(pred, realized), 4),
        "bias": round(bias(pred, realized), 6), "mae": round(mae(pred, realized), 6), "n": n,
        "applied": n >= n_min, "wAlpha": round(a_app, 6), "wBeta": round(b_app, 4), "shrink": round(w, 3),
    }
