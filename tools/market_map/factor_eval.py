"""Factor evaluation engine (pure stdlib) — turns the board from fixed weights into a self-auditing
econometric voting system, per the Deep-Research blueprint.

Pipeline per rebalance:
  1. IC_{f,t} = Spearman rank corr of factor exposure vs FORWARD return over horizon h  (spearman_ic)
  2. mean IC over expanding history + HAC/Newey-West SE (overlap maxlags = h-1)           (hac_mean_t)
  3. p-values -> Benjamini-Hochberg FDR at q -> only survivors vote                        (bh_fdr)
  4. sign-aware shrinkage weight  w_f ∝ pass_f · sign(mean) · max(0,|t|-1), normalized      (factor_weights)
  5. deflated Sharpe gate on the COMPOSITE with an HONEST trial count (Bailey-Lopez de Prado) (deflated_sharpe)

If too few factors survive, the caller should degrade to a low-confidence regime rather than pretend.
Every estimator is unit-tested against planted structure in test_factor_eval.py. Research only.
"""
import math

_EULER = 0.5772156649015329


def _ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _nppf(p):
    """Inverse standard-normal CDF (Acklam's rational approximation; |err|<1.15e-9)."""
    if p <= 0.0: return -math.inf
    if p >= 1.0: return math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    pl = 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p <= 1 - pl:
        q = p - 0.5; r = q * q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def _rank(a):
    """Average ranks (ties shared) — proper Spearman handling."""
    idx = sorted(range(len(a)), key=lambda i: a[i])
    r = [0.0] * len(a); i = 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and a[idx[j + 1]] == a[idx[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[idx[k]] = avg
        i = j + 1
    return r


def _pearson(a, b):
    n = len(a)
    if n < 2: return 0.0
    ma = sum(a) / n; mb = sum(b) / n; sa = sb = sab = 0.0
    for i in range(n):
        da = a[i] - ma; db = b[i] - mb; sa += da * da; sb += db * db; sab += da * db
    d = math.sqrt(sa * sb)
    return sab / d if d > 1e-300 else 0.0


def spearman_ic(exposure, fwd_ret):
    """Cross-sectional Spearman rank IC of a factor vs forward returns."""
    n = min(len(exposure), len(fwd_ret))
    if n < 3: return 0.0
    return _pearson(_rank(exposure[:n]), _rank(fwd_ret[:n]))


def hac_mean_t(series, maxlags=None):
    """Mean of an IC time series and its HAC (Newey-West) t-stat. For an h-period overlapping
    forward-return horizon use maxlags=h-1. Returns {mean, se, t, p, n}."""
    n = len(series)
    if n < 3: return {"mean": 0.0, "se": None, "t": 0.0, "p": 1.0, "n": n}
    mu = sum(series) / n
    u = [x - mu for x in series]
    L = maxlags if maxlags is not None else int(math.floor(4 * (n / 100.0) ** (2.0 / 9.0)))
    L = max(0, min(L, n - 1))
    g0 = sum(x * x for x in u) / n
    lrv = g0
    for j in range(1, L + 1):
        gj = sum(u[t] * u[t - j] for t in range(j, n)) / n
        lrv += 2.0 * (1.0 - j / (L + 1.0)) * gj
    lrv = max(lrv, 1e-300)
    se = math.sqrt(lrv / n)
    t = mu / se if se > 0 else 0.0
    p = 2.0 * (1.0 - _ncdf(abs(t)))
    return {"mean": mu, "se": se, "t": t, "p": max(0.0, min(1.0, p)), "n": n}


def bh_fdr(pvals, q=0.10):
    """Benjamini-Hochberg: returns (reject[list bool], p_cutoff). Controls FDR at q."""
    m = len(pvals)
    if m == 0: return [], 0.0
    order = sorted(range(m), key=lambda i: pvals[i])
    kmax = 0
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= q * rank / m:
            kmax = rank
    cut = pvals[order[kmax - 1]] if kmax else -1.0
    return [pvals[i] <= cut for i in range(m)], cut


def factor_weights(ic_history, maxlags=None, q=0.10):
    """ic_history: {factor: [IC_t,...]}. Returns {factor: {mean,t,p,pass,weight}} with sign-aware
    shrinkage weights w ∝ pass·sign(mean)·max(0,|t|-1), normalized so |weights| sum to 1.
    Also returns _breadth (fraction of factors surviving BH-FDR)."""
    names = list(ic_history.keys())
    stats = {f: hac_mean_t(ic_history[f], maxlags) for f in names}
    rej, cut = bh_fdr([stats[f]["p"] for f in names], q)
    raw = {}
    for i, f in enumerate(names):
        st = stats[f]; passed = bool(rej[i])
        w = (1.0 if passed else 0.0) * (1.0 if st["mean"] >= 0 else -1.0) * max(0.0, abs(st["t"]) - 1.0)
        raw[f] = w; st["pass"] = passed
    tot = sum(abs(v) for v in raw.values()) or 1.0
    out = {}
    for f in names:
        st = stats[f]
        out[f] = {"mean": round(st["mean"], 5), "t": round(st["t"], 3), "p": round(st["p"], 4),
                  "pass": st["pass"], "weight": round(raw[f] / tot, 4)}
    out["_breadth"] = round(sum(1 for f in names if stats[f]["pass"]) / max(1, len(names)), 3)
    return out


def estimate_sr_trials_std(trial_series):
    """Cross-trial Sharpe DISPERSION for the deflated-Sharpe null (Bailey & Lopez de Prado). `trial_series`
    is an iterable of per-trial return/IC series (one per tried configuration). Returns the sample stdev of
    the per-trial (per-observation) Sharpe ratios, or None if fewer than 2 usable trials. DSR's expected-max
    Sharpe under the null scales with THIS dispersion, not with the trial count alone — hard-coding it to 1.0
    makes the gate arbitrarily strict or loose. Pass the result as sr_trials_std to deflated_sharpe()."""
    srs = []
    for s in trial_series or []:
        s = [float(x) for x in s if x is not None]
        if len(s) < 2:
            continue
        mu = sum(s) / len(s)
        var = sum((x - mu) ** 2 for x in s) / (len(s) - 1)
        if var > 0:
            srs.append(mu / math.sqrt(var))
    if len(srs) < 2:
        return None
    m = sum(srs) / len(srs)
    v = sum((x - m) ** 2 for x in srs) / (len(srs) - 1)
    return math.sqrt(v) if v > 0 else None


def deflated_sharpe(sr, n_obs, skew=0.0, kurt=3.0, n_trials=1, sr_trials_std=1.0):
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado). `sr` is the observed (per-period) Sharpe of the
    composite; n_trials is the HONEST number of configurations tried; sr_trials_std is the dispersion of
    Sharpes across those trials. Returns {sr0, dsr} where dsr=P(true SR>0 after deflation). kurt is the
    non-excess kurtosis (3 = normal)."""
    if n_obs < 2: return {"sr0": None, "dsr": None}
    N = max(int(n_trials), 1)
    if N > 1:
        z1 = _nppf(1.0 - 1.0 / N); z2 = _nppf(1.0 - 1.0 / (N * math.e))
        sr0 = sr_trials_std * ((1.0 - _EULER) * z1 + _EULER * z2)
    else:
        sr0 = 0.0
    denom = math.sqrt(max(1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr, 1e-9))
    dsr = _ncdf(((sr - sr0) * math.sqrt(n_obs - 1.0)) / denom)
    return {"sr0": round(sr0, 4), "dsr": round(dsr, 4)}
