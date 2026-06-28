#!/usr/bin/env python3
"""
rank_engine.py — the mastery ranking mathematics for the Bull/Bear board (pure-stdlib reference).

The old board ranks by the optimistic POINT estimate `tot` (expected 1-month total return). That over-ranks
noisy, low-conviction names. This engine ranks by a CONFIDENCE-ADJUSTED, MULTIPLICITY-DEFLATED, calibrated
score instead. Verified-engine pattern: this is authoritative; rank_engine.js is locked to tools/rank_golden.json.

Pieces (each defensible, each unit-tested):
  grinold_kahn(ic, sigma, z)      Grinold-Kahn forecast alpha = IC * sigma * z (turn a score into a
                                  CALIBRATED expected excess return using realized factor skill IC).
  alpha_forecast_se(...)          PER-NAME standard error of the predicted return from the alpha->return
                                  calibration (mean-response SE, leverage-aware). This is the genuine
                                  uncertainty term the lower-confidence bound should haircut: it is
                                  INDEPENDENT of the point estimate's sign and grows for extreme-alpha names.
  conviction_sigma(base, z)       FALLBACK effective forecast sigma when no per-name SE is available: grows as
                                  conviction shrinks (low |z| -> larger sigma -> larger uncertainty penalty).
  lcb_score(mu, sigma, k)         lower-confidence-bound rank score: move the edge toward 0 by k*sigma, in
                                  the direction of its own sign. Rank by what you can DEFEND, not the peak.
  deflated_conviction(z, n)       selection-bias-aware conviction: the max |z| over n names is inflated
                                  ~sqrt(2 ln n); report the conviction IN EXCESS of that multiplicity bar.
  stein_shrink(x, se, tau, c)     empirical-Bayes / James-Stein shrinkage of a noisy estimate toward a center
                                  c (the cross-sectional mean when borrowing strength; 0 by default).
  ewma_score(prev, now, lam)      run-over-run smoothing to damp board whipsaw (rank stability).
  composite_rank_score(...)       the headline score the board ranks by: LCB with the per-name SE, a soft
                                  multiplicity discount when n_tests is supplied, and optional EWMA.
"""
import json, math, os

__all__ = ["grinold_kahn", "alpha_forecast_se", "conviction_sigma", "lcb_score", "deflated_conviction",
           "stein_shrink", "eb_tau2", "eb_posterior", "ewma_score", "composite_rank_score",
           "effective_breadth", "enb_entropy", "trading_cost", "net_alpha", "cvar_es", "tail_adjust",
           "decay_alpha", "transition_gate", "ledoit_wolf", "deflated_sharpe"]


def grinold_kahn(ic, sigma, z):
    """Calibrated expected excess return = IC * sigma * z (Grinold-Kahn 'alpha = IC·σ·score')."""
    return ic * sigma * z


def alpha_forecast_se(resid_sd, alpha, alpha_mean, sxx, n):
    """Standard error of the predicted return from the alpha->return calibration, for ONE name:
        SE = resid_sd * sqrt(1/n + (alpha - alpha_mean)^2 / Sxx)
    This is the mean-response (estimation) uncertainty of the OLS prediction y_hat = a + b*alpha. It is
    heteroskedastic across names through leverage (extreme-alpha names sit far from the design center and
    carry wider bands) and, unlike a return-dispersion proxy, is independent of the point estimate's sign.
    Returns None when inputs are unusable so the caller can fall back to the conviction-scaled sigma."""
    if not (resid_sd and resid_sd > 0 and sxx and sxx > 0 and n and n >= 3):
        return None
    return resid_sd * math.sqrt(1.0 / n + (alpha - alpha_mean) * (alpha - alpha_mean) / sxx)


def conviction_sigma(base_sigma, z, floor=0.2, full=1.5):
    """Fallback effective forecast sigma that grows as conviction shrinks: sigma = base / clamp(|z|/full, floor, 1).
    At |z|>=full (HIGH) -> base; at |z|->0 -> base/floor (max uncertainty). Used only when no per-name SE exists."""
    rel = abs(z) / full if full > 0 else 0.0
    rel = max(floor, min(1.0, rel))
    return base_sigma / rel


def lcb_score(mu, sigma, k=0.5):
    """Lower-confidence-bound rank score: shift the edge toward 0 by k*sigma in the direction of its sign,
    so a high-uncertainty name (either side) is penalized toward neutral. Rank bulls desc, bears asc."""
    if sigma is None or sigma != sigma or sigma < 0:
        return mu
    pen = k * sigma
    if mu >= 0:
        return mu - pen
    return mu + pen


def deflated_conviction(z, n_tests):
    """Conviction in EXCESS of the cross-sectional multiplicity bar. With n names the largest |z| is
    inflated ~E[max] = sqrt(2 ln n); return sign(z) * max(0, |z| - sqrt(2 ln n))."""
    if n_tests is None or n_tests < 2:
        return z
    bar = math.sqrt(2.0 * math.log(n_tests))
    excess = max(0.0, abs(z) - bar)
    return math.copysign(excess, z) if z != 0 else 0.0


def stein_shrink(x, se, tau, center=0.0):
    """Empirical-Bayes / James-Stein shrinkage of a noisy estimate toward `center`: w = tau^2/(tau^2+se^2);
    shrunk = center + w*(x-center). Noisier estimates (large se) shrink harder toward the center. Use the
    cross-sectional mean as the center to BORROW STRENGTH across names; center=0 reproduces shrink-to-zero."""
    if se is None or se <= 0 or tau is None or tau <= 0:
        return x
    w = (tau * tau) / (tau * tau + se * se)
    return center + w * (x - center)


def eb_tau2(values, ses):
    """Empirical-Bayes between-name (signal) variance, by method of moments:
        tau^2 = max(0, Var(values) - mean(se^2))
    i.e. the cross-sectional dispersion of the estimates MINUS the average measurement variance, so it
    measures only the dispersion that is real signal. Drives the shrink strength: if the cross-section is
    mostly noise (Var ~ mean se^2) -> tau^2 -> 0 -> shrink everything to the center; if there is strong
    signal -> tau^2 large -> barely shrink. Self-tuning (Efron-Morris), no hand-set knob."""
    a = [x for x in values if x == x]
    s = [x for x in ses if (x is not None and x == x and x > 0)]
    if len(a) < 3:
        return 0.0
    m = sum(a) / len(a)
    var = sum((x - m) ** 2 for x in a) / (len(a) - 1)
    mse = (sum(x * x for x in s) / len(s)) if s else 0.0
    return max(0.0, var - mse)


def eb_posterior(value, se, center, tau2):
    """Normal-Normal (empirical-Bayes) posterior for one estimate given prior N(center, tau2) and
    likelihood N(value, se^2):
        w = tau2 / (tau2 + se^2)                 shrink weight (toward the data; 1-w toward the prior)
        mu = center + w*(value - center)          posterior mean (shrunk estimate)
        sd = sqrt(w)*se                           posterior SD  (= sqrt(w*se^2) < se: shrinkage buys certainty)
    Returns {"mu","sd","w"}. Ranking by mu - k*sd unifies shrinkage and the uncertainty haircut in ONE
    posterior, so a noisy name is not penalized twice. se/ tau2 unusable -> identity (no shrink)."""
    if se is None or se <= 0 or tau2 is None or tau2 <= 0:
        return {"mu": value, "sd": (se if (se is not None and se > 0) else 0.0), "w": 1.0}
    w = tau2 / (tau2 + se * se)
    return {"mu": center + w * (value - center), "sd": math.sqrt(w) * se, "w": w}


def ewma_score(prev, now, lam=0.5):
    """Run-over-run smoothing for rank stability (damps daily whipsaw). lam in (0,1]; prev None -> now."""
    if prev is None or prev != prev:
        return now
    return lam * now + (1.0 - lam) * prev


def composite_rank_score(tot, z, base_sigma, k=0.5, n_tests=None, prev=None, lam=1.0, se=None):
    """Headline ranking score the board sorts by:
      1. sigma = per-name regression SE `se` when supplied (the genuine estimation uncertainty); otherwise
         the conviction-scaled proxy conviction_sigma(base_sigma, z).
      2. LCB: shift `tot` toward 0 by k*sigma in the direction of its sign (lcb_score).
      3. Multiplicity: when n_tests is supplied, apply a SOFT selection discount min(1, |z|/sqrt(2 ln n)) so a
         name that has not cleared the cross-sectional bar cannot present full strength. This is separate from
         the estimation-noise LCB (different source of doubt: selection vs. measurement).
      4. EWMA-smooth against the prior run's score when `prev` is supplied."""
    sigma = se if (se is not None and se == se and se > 0) else conviction_sigma(base_sigma, z)
    s = lcb_score(tot, sigma, k)
    if n_tests is not None and n_tests >= 2:
        bar = math.sqrt(2.0 * math.log(n_tests))
        if bar > 0:
            s = s * min(1.0, abs(z) / bar)
    return ewma_score(prev, s, lam) if (prev is not None) else s


# ============================================================================
# Extensions from the "Omitted Strategies" review — each a verified, self-contained primitive.
# ============================================================================

def effective_breadth(n, avg_corr):
    """#11 dependence-aware multiplicity: effective number of INDEPENDENT bets under equicorrelation
    rho: N_eff = n / (1 + (n-1)*rho). Correlated names overstate n, so the multiplicity bar should use
    sqrt(2 ln N_eff), not sqrt(2 ln n). rho clamped [0,1); rho=0 -> n, rho->1 -> 1."""
    if n is None or n < 1:
        return 1.0
    rho = 0.0 if (avg_corr is None or avg_corr != avg_corr) else max(0.0, min(0.999, avg_corr))
    return max(1.0, n / (1.0 + (n - 1) * rho))


def enb_entropy(spectrum):
    """Meucci Effective Number of Bets via entropy of a normalized non-negative spectrum (PCA
    eigenvalues / weights): ENB = exp(-sum p ln p), p = s/sum(s). Range [1, len]."""
    s = [max(0.0, x) for x in spectrum if x == x]
    tot = sum(s)
    if tot <= 0 or not s:
        return 1.0
    p = [x / tot for x in s if x > 0]
    h = -sum(pi * math.log(pi) for pi in p)
    return math.exp(h)


def trading_cost(vol_pct=None, fee_bps=2.0, half_spread_bps=None, participation=0.05, impact_coef=0.1):
    """#4 round-trip trading cost in PERCENT: 2*(fee + half-spread) + sqrt-impact. half-spread proxies
    from daily vol when not supplied (~5% of daily vol); impact = impact_coef*vol*sqrt(participation)
    (square-root market-impact law). Accepts real bps spread / vol when available."""
    fee = fee_bps / 100.0
    hs = (half_spread_bps / 100.0) if half_spread_bps is not None else 0.05 * (vol_pct if (vol_pct and vol_pct == vol_pct) else 2.0)
    v = vol_pct if (vol_pct and vol_pct == vol_pct) else 2.0
    impact = impact_coef * v * math.sqrt(max(participation, 0.0))
    return 2.0 * (fee + hs) + impact


def net_alpha(mu, cost):
    """#4 net-of-cost edge: move the edge toward 0 by the (positive) cost, on either side."""
    if cost is None or cost < 0:
        cost = 0.0
    return (mu - cost) if mu >= 0 else (mu + cost)


def cvar_es(returns, alpha=0.05):
    """#14 historical Expected Shortfall (CVaR): mean of the worst alpha-tail of returns, returned as a
    POSITIVE loss magnitude. None when too few points (<20)."""
    r = sorted(x for x in returns if x == x)
    if len(r) < 20:
        return None
    k = max(1, int(math.floor(alpha * len(r))))
    tail = r[:k]
    return abs(sum(tail) / len(tail))


def tail_adjust(mu, es, lam=0.1):
    """#14 haircut the edge for tail risk: move toward 0 by lam*ES (ES positive)."""
    if es is None or es < 0:
        return mu
    return (mu - lam * es) if mu >= 0 else (mu + lam * es)


def decay_alpha(mu, horizon, half_life):
    """#16 exponential alpha decay over a holding horizon: mu * 0.5^(horizon/half_life)."""
    if not half_life or half_life <= 0 or horizon is None or horizon < 0:
        return mu
    return mu * (0.5 ** (horizon / half_life))


def transition_gate(prev, now, band):
    """#5 turnover hysteresis: keep the prior ranking value unless the new one moves more than `band`
    (cuts churn/turnover/tax friction). prev None -> now."""
    if prev is None or prev != prev:
        return now
    if band is None or band < 0:
        band = 0.0
    return now if abs(now - prev) > band else prev


def _lw_cov(Xc):
    T = len(Xc); p = len(Xc[0]); S = [[0.0] * p for _ in range(p)]
    for t in range(T):
        x = Xc[t]
        for i in range(p):
            xi = x[i]; row = S[i]
            for j in range(p):
                row[j] += xi * x[j]
    for i in range(p):
        for j in range(p):
            S[i][j] /= T
    return S


def ledoit_wolf(X):
    """#6 Ledoit-Wolf (2004) linear shrinkage of the sample covariance to a scaled-identity target
    F = m*I (m = average variance): Sigma* = delta*F + (1-delta)*S, delta = b^2/d^2 with d^2 the
    dispersion of S from F and b^2 the estimation error (capped at d^2). Returns (delta, Sigma*).
    X: T rows of p returns (demeaned internally). Stdlib-only, O(T*p^2)."""
    T = len(X); p = len(X[0])
    mean = [sum(X[t][j] for t in range(T)) / T for j in range(p)]
    Xc = [[X[t][j] - mean[j] for j in range(p)] for t in range(T)]
    S = _lw_cov(Xc)
    m = sum(S[i][i] for i in range(p)) / p
    d2 = sum((S[i][j] - (m if i == j else 0.0)) ** 2 for i in range(p) for j in range(p)) / p
    bb = 0.0
    for t in range(T):
        x = Xc[t]
        bb += sum((x[i] * x[j] - S[i][j]) ** 2 for i in range(p) for j in range(p))
    bb = bb / (T * T) / p
    b2 = min(bb, d2)
    delta = max(0.0, min(1.0, (b2 / d2) if d2 > 0 else 0.0))
    Sig = [[delta * (m if i == j else 0.0) + (1 - delta) * S[i][j] for j in range(p)] for i in range(p)]
    return delta, Sig


def _ncdf(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _nppf(pp):
    """Acklam inverse-normal approximation (for the deflated-Sharpe selection threshold)."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    pl = 0.02425
    if pp < pl:
        q = math.sqrt(-2 * math.log(pp)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if pp <= 1 - pl:
        q = pp - 0.5; r = q * q; return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - pp)); return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)


def deflated_sharpe(sr, T, skew=0.0, kurt=3.0, n_trials=1):
    """#2 Deflated Sharpe Ratio (Bailey & Lopez de Prado): probability the TRUE SR>0 after deflating
    for selection over n_trials AND non-normal returns. var_sr=(1 - skew*sr + (kurt-1)/4*sr^2)/(T-1);
    SR* = E[max] of n_trials null Sharpes. Use as a promotion gate (e.g. require DSR>=0.95)."""
    if T < 3:
        return None
    var_sr = (1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr) / (T - 1)
    sr_star = 0.0
    if n_trials and n_trials >= 2:
        g = 0.5772156649015329
        sr_star = math.sqrt(max(var_sr, 0.0)) * ((1 - g) * _nppf(1 - 1.0 / n_trials) + g * _nppf(1 - 1.0 / (n_trials * math.e)))
    return _ncdf((sr - sr_star) / math.sqrt(max(var_sr, 1e-12)))


# ---- committed golden fixture (both languages lock to it) ----
def gen_fixture():
    cases = [
        {"tot": 6.5, "z": 2.1, "base_sigma": 9.0, "se": 1.2},   # high edge, high conviction, clean estimate
        {"tot": 6.0, "z": 0.5, "base_sigma": 9.0, "se": 4.5},   # high edge, LOW conviction + noisy -> ranks lower
        {"tot": -5.0, "z": -1.8, "base_sigma": 9.0, "se": 1.5}, # bear, high conviction
        {"tot": -4.8, "z": -0.4, "base_sigma": 9.0, "se": 3.8}, # bear, low conviction + noisy
        {"tot": 1.2, "z": 3.0, "base_sigma": 6.0, "se": 0.6},   # small edge, very high conviction, very clean
    ]
    n = len(cases)
    tots = [c["tot"] for c in cases]
    ses = [c["se"] for c in cases]
    eb_center = sum(tots) / n              # global prior center (mean expected return)
    eb_t2 = eb_tau2(tots, ses)             # self-tuned shrink strength
    out = []
    for c in cases:
        eb = eb_posterior(c["tot"], c["se"], eb_center, eb_t2)
        out.append({
            "tot": c["tot"], "z": c["z"], "base_sigma": c["base_sigma"], "se": c["se"],
            "convSigma": conviction_sigma(c["base_sigma"], c["z"]),
            "lcb": lcb_score(c["tot"], c["se"], 0.5),
            "score": composite_rank_score(c["tot"], c["z"], c["base_sigma"], 0.5, n, se=c["se"]),
            "zAdj": deflated_conviction(c["z"], 150),
            "gk": grinold_kahn(0.08, c["base_sigma"], c["z"]),
            "aFse": alpha_forecast_se(2.0, c["z"], 0.0, 10.0, n),     # leverage SE with z as a stand-in alpha
            "steinC": stein_shrink(c["tot"], c["se"], 3.0, center=1.0),
            "ebMu": eb["mu"], "ebSd": eb["sd"], "ebW": eb["w"],
            "netAlpha": net_alpha(c["tot"], 1.0), "decayMu": decay_alpha(c["tot"], 5, 21),
            "tailAdj": tail_adjust(c["tot"], 0.8, 0.1),
        })
    return {"fixture_version": 4, "case": "rank-engine-core", "k": 0.5, "n_tests": n,
            "ebCenter": eb_center, "ebTau2": eb_t2,
            "effBreadth": effective_breadth(n, 0.3), "enb": enb_entropy([4.0, 2.0, 1.0, 1.0, 0.5]),
            "tradingCost": trading_cost(3.0), "dsr": deflated_sharpe(0.5, 250, 0.0, 3.0, n),
            "rows": out}


def main():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rank_golden.json")
    json.dump(gen_fixture(), open(p, "w"), separators=(",", ":"))
    print("wrote", os.path.normpath(p))


if __name__ == "__main__":
    main()
