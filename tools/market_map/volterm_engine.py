"""volterm_engine.py — retire sqrt-time volatility scaling (PDF 3). Direct horizon HV term structure +
Lo-MacKinlay variance ratio (with heteroskedasticity-robust CI) + EWMA vol + a blended variance scale.

Naive baseline being replaced:  sigma_H = sigma_1 * sqrt(H)  (random-walk assumption).
Replacement: measure the H-step volatility DIRECTLY (hv_term_structure) and report VR(H) = Var(R_H)/(H*Var(r1))
as the diagnostic of how wrong sqrt-scaling is (VR<1 mean reversion -> sqrt overstates; VR>1 persistence ->
sqrt understates). Pure stdlib; verified vs planted random-walk / AR(1) / persistent processes; JS port for
the browser cone. Research only, not advice."""
import math

__all__ = ["hv_term_structure", "sqrt_baseline", "variance_ratio", "ewma_vol", "studentize",
           "blended_scale"]


def _mean(x):
    return sum(x) / len(x) if x else 0.0


def _var(x, ddof=1):
    n = len(x)
    if n <= ddof:
        return 0.0
    m = _mean(x)
    return sum((v - m) ** 2 for v in x) / (n - ddof)


def hv_term_structure(returns, horizons, overlapping=True):
    """Direct H-step volatility for each horizon H: std of (overlapping) H-period summed log returns.
    No sqrt assumption — captures mean reversion/persistence empirically. Returns {H: sigma_H}."""
    out = {}
    T = len(returns)
    for H in horizons:
        if H <= 0 or T < H + 1:
            out[H] = None
            continue
        if H == 1:
            out[H] = math.sqrt(_var(returns))
            continue
        sums = []
        if overlapping:
            run = sum(returns[:H])
            sums.append(run)
            for t in range(H, T):
                run += returns[t] - returns[t - H]
                sums.append(run)
        else:
            for t in range(0, T - H + 1, H):
                sums.append(sum(returns[t:t + H]))
        out[H] = math.sqrt(_var(sums)) if len(sums) > 1 else None
    return out


def sqrt_baseline(returns, horizons):
    """The naive sigma_1 * sqrt(H) term structure, for side-by-side diagnostics."""
    s1 = math.sqrt(_var(returns))
    return {H: (s1 * math.sqrt(H) if H > 0 else None) for H in horizons}


def variance_ratio(returns, q):
    """Lo-MacKinlay overlapping variance ratio VR(q) with homoskedastic z and heteroskedasticity-robust
    z* + 95% CI. VR(q) = sigma_c^2(q) / sigma_a^2.  Returns dict {vr, z, zRobust, ciLo, ciHi, q, n}."""
    T = len(returns)
    if q < 2 or T < q + 1:
        return {"vr": None, "z": None, "zRobust": None, "ciLo": None, "ciHi": None, "q": q, "n": T}
    mu = _mean(returns)
    # 1-period variance (unbiased)
    sa2 = sum((r - mu) ** 2 for r in returns) / (T - 1)
    if sa2 <= 0:
        return {"vr": None, "z": None, "zRobust": None, "ciLo": None, "ciHi": None, "q": q, "n": T}
    # q-period overlapping variance, Lo-MacKinlay unbiased scaling m
    m = q * (T - q + 1) * (1.0 - q / float(T))
    sc2 = 0.0
    for t in range(q - 1, T):
        x = sum(returns[t - q + 1:t + 1]) - q * mu
        sc2 += x * x
    sc2 /= m
    vr = sc2 / sa2
    # homoskedastic asymptotic variance of VR
    v_homo = 2.0 * (2.0 * q - 1.0) * (q - 1.0) / (3.0 * q * T)
    z = (vr - 1.0) / math.sqrt(v_homo) if v_homo > 0 else None
    # heteroskedasticity-robust variance (Lo-MacKinlay M2): theta = sum_j [2(q-j)/q]^2 * delta_j
    dev2 = [(r - mu) ** 2 for r in returns]
    denom = sum(dev2) ** 2
    theta = 0.0
    if denom > 0:
        for j in range(1, q):
            num = sum(dev2[t] * dev2[t - j] for t in range(j, T))
            delta_j = num / denom                  # LM heteroskedastic-consistent delta_j (reduces to homoskedastic theta)
            theta += ((2.0 * (q - j) / q) ** 2) * delta_j
    z_rob = (vr - 1.0) / math.sqrt(theta) if theta > 0 else None
    se_rob = math.sqrt(theta) if theta > 0 else None
    ci_lo = vr - 1.96 * se_rob if se_rob else None
    ci_hi = vr + 1.96 * se_rob if se_rob else None
    return {"vr": vr, "z": z, "zRobust": z_rob, "ciLo": ci_lo, "ciHi": ci_hi, "q": q, "n": T}


def ewma_vol(returns, lam=0.94, seed=None):
    """RiskMetrics EWMA 1-step volatility: h_t = lam*h_{t-1} + (1-lam)*r_{t-1}^2. Returns sigma_t (final)."""
    if not returns:
        return 0.0
    h = seed if seed is not None else _var(returns)
    for r in returns:
        h = lam * h + (1.0 - lam) * r * r
    return math.sqrt(max(h, 0.0))


def studentize(y_real, yhat, sigma_h, gamma=1e-6):
    """Scaled nonconformity score s = (y - yhat)/(sigma_H + gamma) — feed to the conformal band layer."""
    return (y_real - yhat) / (sigma_h + gamma)


def blended_scale(components, weights, H):
    """Blend horizon-H variance components (e.g. {'hv':.., 'ewma':.., 'garch':.., 'rv':..}) into one
    sigma_H. weights nonnegative; renormalized to sum 1 over the components actually present."""
    keys = [k for k in components if components[k] is not None and weights.get(k, 0) > 0]
    if not keys:
        return None
    wsum = sum(weights[k] for k in keys)
    if wsum <= 0:
        return None
    var_h = sum((weights[k] / wsum) * (components[k] ** 2) for k in keys)
    return math.sqrt(max(var_h, 0.0))
