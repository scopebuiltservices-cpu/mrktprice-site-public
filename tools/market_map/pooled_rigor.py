#!/usr/bin/env python3
"""
pooled_rigor.py — selection-bias + panel-dependence hardening for the pooled computations (pure stdlib).

Implements the rigor upgrades from the Reproducible Technical Report that were missing from the pooled
layer, each verified against planted structure:

  two_way_cluster_se   OLS slope with Cameron-Gelbach-Miller two-way (ticker x date) clustered SE
  two_way_fe           two-way fixed-effect (within) panel slope: y_it - y_i - y_t + y_bar
  psr                  Probabilistic Sharpe Ratio (Bailey & Lopez de Prado)
  min_trl              Minimum Track Record Length for PSR(SR*) >= prob
  pbo_cscv             Probability of Backtest Overfitting via CSCV (combinatorially-symmetric CV)
  reality_check        White's Reality Check bootstrap p-value (data-snooping over K strategies)
  spa                  Hansen's SPA (studentized, consistent recentering) p-value
  effective_breadth    eigenvalue participation ratio N_eff = (Σλ)²/Σλ²  (= N²/Σ_ij C_ij² for a corr matrix)
  random_effects_meta  DerSimonian-Laird pooled beta + tau² + I² heterogeneity
  mover_decomp         Δnet = Σ w_k Δcomponent_k  (audit a top-mover back to its components)

Research only.
"""
import math, random


# ---------- small helpers ----------
def _ncdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _nppf(p):
    if p <= 0: return -1e9
    if p >= 1: return 1e9
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    pl = 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p <= 1 - pl:
        q = p - 0.5; r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)


def _mean(x): return sum(x) / len(x) if x else 0.0


def _moments(x):
    n = len(x)
    if n < 3: return 0.0, 3.0
    m = _mean(x); m2 = sum((v - m) ** 2 for v in x) / n
    if m2 <= 0: return 0.0, 3.0
    m3 = sum((v - m) ** 3 for v in x) / n; m4 = sum((v - m) ** 4 for v in x) / n
    sd = math.sqrt(m2)
    return m3 / sd ** 3, m4 / m2 ** 2


# ---------- Sharpe inference: PSR + MinTRL ----------
def sharpe(returns):
    n = len(returns)
    if n < 2: return None
    m = _mean(returns); sd = math.sqrt(sum((r - m) ** 2 for r in returns) / (n - 1))
    return (m / sd) if sd > 0 else None


def psr(sr, n, skew=0.0, kurt=3.0, sr_benchmark=0.0):
    """Probabilistic Sharpe Ratio: P(true SR > sr_benchmark) given the estimate sr over n obs.
    sr and sr_benchmark are PER-OBSERVATION Sharpes. kurt is non-excess (normal=3)."""
    if n is None or n < 2: return None
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if denom <= 0: return None
    return _ncdf((sr - sr_benchmark) * math.sqrt(n - 1.0) / math.sqrt(denom))


def min_trl(sr, skew=0.0, kurt=3.0, sr_benchmark=0.0, prob=0.95):
    """Minimum Track Record Length: smallest n so PSR(sr_benchmark) >= prob. None if sr<=benchmark."""
    if sr <= sr_benchmark: return None
    z = _nppf(prob)
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if denom <= 0: return None
    return 1.0 + denom * (z / (sr - sr_benchmark)) ** 2


# ---------- panel inference: two-way clustered SE + two-way FE ----------
def _ols_xy(x, y):
    n = len(x); mx = _mean(x); my = _mean(y)
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx <= 0: return None
    b = sum((x[i] - mx) * (y[i] - my) for i in range(n)) / sxx
    a = my - b * mx
    resid = [y[i] - (a + b * x[i]) for i in range(n)]
    return a, b, resid, mx, sxx


def two_way_cluster_se(x, y, gid, did):
    """Slope of y~x with Cameron-Gelbach-Miller two-way clustered SE: V = Vg + Vd - Vw (White).
    gid/did are group (ticker) and date cluster labels aligned to x,y. Returns {beta,se,t,p,n}."""
    n = len(x)
    if n < 5: return None
    fit = _ols_xy(x, y)
    if not fit: return None
    a, b, e, mx, sxx = fit
    xc = [xi - mx for xi in x]
    bread = 1.0 / sxx                                   # (X'X)^-1 for the demeaned single regressor

    def meat(labels):
        sums = {}
        for i in range(n):
            sums[labels[i]] = sums.get(labels[i], 0.0) + xc[i] * e[i]
        return sum(s * s for s in sums.values())
    Vg = bread * meat(gid) * bread
    Vd = bread * meat(did) * bread
    Vw = bread * sum((xc[i] * e[i]) ** 2 for i in range(n)) * bread   # White HC0 (intersection clusters)
    V = Vg + Vd - Vw
    if V <= 0: V = max(Vg, Vd, Vw)                      # PSD floor (CGM can go slightly negative)
    se = math.sqrt(V); t = b / se if se > 0 else 0.0
    p = 2.0 * (1.0 - _ncdf(abs(t)))
    return {"beta": b, "se": se, "t": t, "p": max(0.0, min(1.0, p)), "n": n}


def two_way_fe(x, y, gid, did):
    """Two-way fixed-effect (within) slope: demean x,y by group and date means, then OLS through origin.
    y_it~ = y_it - ybar_i - ybar_t + ybar.  Returns {beta, n}."""
    n = len(x)
    if n < 5: return None
    def demean(v):
        gbar = {}; gcnt = {}; dbar = {}; dcnt = {}
        for i in range(n):
            gbar[gid[i]] = gbar.get(gid[i], 0.0) + v[i]; gcnt[gid[i]] = gcnt.get(gid[i], 0) + 1
            dbar[did[i]] = dbar.get(did[i], 0.0) + v[i]; dcnt[did[i]] = dcnt.get(did[i], 0) + 1
        gm = {k: gbar[k] / gcnt[k] for k in gbar}; dm = {k: dbar[k] / dcnt[k] for k in dbar}
        gg = _mean(v)
        return [v[i] - gm[gid[i]] - dm[did[i]] + gg for i in range(n)]
    xt = demean(x); yt = demean(y)
    sxx = sum(v * v for v in xt)
    if sxx <= 0: return None
    b = sum(xt[i] * yt[i] for i in range(n)) / sxx
    return {"beta": b, "n": n}


# ---------- data snooping: CSCV/PBO, Reality Check, SPA ----------
def _comb_halves(S):
    import itertools
    idx = list(range(S))
    half = S // 2
    seen = set(); out = []
    for c in itertools.combinations(idx, half):
        key = frozenset(c)
        if key in seen: continue
        comp = frozenset(idx) - key
        if comp in seen: continue
        seen.add(key); out.append((list(c), sorted(comp)))
    return out


def pbo_cscv(M, S=10):
    """Probability of Backtest Overfitting (Bailey et al. CSCV). M is T_obs x N_configs of per-period
    returns. Split rows into S blocks; over all balanced IS/OOS splits, take the IS-best config and read
    its OOS performance rank; PBO = P(OOS rank in lower half). Returns {pbo, n_splits, n_configs}."""
    T = len(M)
    if T < S or not M or len(M[0]) < 2: return {"pbo": None, "reason": "insufficient"}
    N = len(M[0]); bs = T // S
    blocks = [list(range(k * bs, (k + 1) * bs)) for k in range(S)]
    def perf(rows, cfg):
        xs = [M[r][cfg] for r in rows]
        return sharpe(xs) or 0.0
    lam = []
    for IS_b, OOS_b in _comb_halves(S):
        IS = [r for b in IS_b for r in blocks[b]]; OOS = [r for b in OOS_b for r in blocks[b]]
        is_perf = [perf(IS, c) for c in range(N)]
        best = max(range(N), key=lambda c: is_perf[c])
        oos = [perf(OOS, c) for c in range(N)]
        rank = 1 + sum(1 for v in oos if v < oos[best])            # 1..N, higher=better
        w = rank / (N + 1.0)
        lam.append(1.0 if w <= 0.5 else 0.0)
    pbo = _mean(lam) if lam else None
    return {"pbo": pbo, "n_splits": len(lam), "n_configs": N}


def reality_check(D, B=1000, block=5, seed=12345):
    """White's Reality Check. D is T x K differential returns (strategy_k - benchmark). Stationary block
    bootstrap; statistic V=max_k sqrt(T)*mean(D_k); p = P(V* >= V) under recentered resamples."""
    T = len(D)
    if T < 10 or not D[0]: return {"p": None, "reason": "insufficient"}
    K = len(D[0]); cols = [[D[t][k] for t in range(T)] for k in range(K)]
    means = [_mean(c) for c in cols]
    V = max(math.sqrt(T) * means[k] for k in range(K))
    rng = _mulberry32(seed); ge = 0
    for _ in range(B):
        idx = _block_idx(T, block, rng)
        vb = -1e18
        for k in range(K):
            mb = _mean([cols[k][i] for i in idx])
            vb = max(vb, math.sqrt(T) * (mb - means[k]))
        if vb >= V: ge += 1
    return {"p": (ge + 1.0) / (B + 1.0), "V": V, "K": K}


def spa(D, B=1000, block=5, seed=777):
    """Hansen's SPA (studentized, consistent recentering). D is T x K differential returns. Returns p."""
    T = len(D)
    if T < 10 or not D[0]: return {"p": None, "reason": "insufficient"}
    K = len(D[0]); cols = [[D[t][k] for t in range(T)] for k in range(K)]
    means = [_mean(c) for c in cols]
    sds = []
    for k in range(K):
        v = sum((cols[k][t] - means[k]) ** 2 for t in range(T)) / max(T - 1, 1)
        sds.append(math.sqrt(v / T) if v > 0 else 1e-9)             # std error of the mean
    Tstat = max(means[k] / sds[k] for k in range(K))
    # Hansen (2005) CONSISTENT recentering: model k keeps its sample mean only if that mean is not
    # significantly negative at the studentized rate sqrt(2 ln ln T); otherwise it is recentered to 0
    # (treated as a non-beating model under the null). sds[k] is already the std error of the mean
    # (= sqrt(var_k / T)), so sds[k]*sqrt(2 ln ln T) is exactly Hansen's threshold sqrt((omega_k^2/T)*2 ln ln T).
    llt = math.sqrt(2.0 * math.log(math.log(T))) if T >= 3 else 0.0
    thr = [means[k] if means[k] >= -sds[k] * llt else 0.0 for k in range(K)]
    rng = _mulberry32(seed); ge = 0
    for _ in range(B):
        idx = _block_idx(T, block, rng)
        tb = -1e18
        for k in range(K):
            mb = _mean([cols[k][i] for i in idx])
            tb = max(tb, (mb - thr[k]) / sds[k])
        if tb >= Tstat: ge += 1
    return {"p": (ge + 1.0) / (B + 1.0), "T": Tstat, "K": K}


def _mulberry32(seed):
    """Deterministic 32-bit PRNG, BIT-FOR-BIT identical to the JS mulberry32 in pooled_rigor.js, so the
    bootstrap p-values (Reality Check, SPA) match across Python and JS exactly. All arithmetic is unsigned
    mod 2^32, which reproduces JS's int32/Math.imul low-32-bit semantics."""
    a = seed & 0xFFFFFFFF
    M = 0xFFFFFFFF
    def nxt():
        nonlocal a
        a = (a + 0x6D2B79F5) & M
        t = (a ^ (a >> 15)) & M
        t = (t * ((1 | a) & M)) & M
        t2 = (((t ^ (t >> 7)) & M) * ((61 | t) & M)) & M
        t = (((t + t2) & M) ^ t) & M
        return ((t ^ (t >> 14)) & M) / 4294967296.0
    return nxt


def _block_idx(T, block, rnd):
    """Stationary block-bootstrap indices using a mulberry32 callable (matches JS blockIdx exactly)."""
    idx = []
    while len(idx) < T:
        s = int(rnd() * T)
        for j in range(block):
            idx.append((s + j) % T)
            if len(idx) >= T: break
    return idx[:T]


# ---------- diversification + meta-analysis + decomposition ----------
def effective_breadth(corr):
    """Eigenvalue participation ratio N_eff=(Σλ)²/Σλ². For a correlation matrix Σλ=trace=N and
    Σλ²=trace(C²)=Σ_ij C_ij², so N_eff = N² / Σ_ij C_ij²  (exact, no eigendecomposition)."""
    N = len(corr)
    if N == 0: return None
    fro2 = sum(corr[i][j] ** 2 for i in range(N) for j in range(N))
    if fro2 <= 0: return None
    return (N * N) / fro2


def random_effects_meta(betas, ses):
    """DerSimonian-Laird random-effects meta-analysis. Returns {beta_fe, beta_re, se_re, tau2, Q, I2, k}."""
    pairs = [(b, s) for b, s in zip(betas, ses) if s and s > 0 and b is not None]
    k = len(pairs)
    if k < 2: return {"beta_fe": None, "beta_re": None, "se_re": None, "tau2": None, "Q": None, "I2": None, "k": k}
    w = [1.0 / (s * s) for _, s in pairs]; b = [bb for bb, _ in pairs]
    sw = sum(w); bfe = sum(w[i] * b[i] for i in range(k)) / sw
    Q = sum(w[i] * (b[i] - bfe) ** 2 for i in range(k))
    df = k - 1
    C = sw - sum(wi * wi for wi in w) / sw
    tau2 = max(0.0, (Q - df) / C) if C > 0 else 0.0
    ws = [1.0 / (1.0 / wi + tau2) if (1.0 / wi + tau2) > 0 else 0.0 for wi in w]
    sws = sum(ws)
    bre = sum(ws[i] * b[i] for i in range(k)) / sws if sws > 0 else None
    sere = math.sqrt(1.0 / sws) if sws > 0 else None
    I2 = max(0.0, (Q - df) / Q) * 100.0 if Q > 0 else 0.0
    return {"beta_fe": bfe, "beta_re": bre, "se_re": sere, "tau2": tau2, "Q": Q, "I2": I2, "k": k}


def mover_decomp(now, prev, weights=None):
    """Δnet decomposition: Δnet = Σ w_k (now_k - prev_k). now/prev are dicts of component scores.
    Default weights = the composite (sMR .35, sMom .30, sSig .25, sVol .10)."""
    weights = weights or {"sMR": 0.35, "sMom": 0.30, "sSig": 0.25, "sVol": 0.10}
    contrib = {}; total = 0.0
    for k, w in weights.items():
        d = (now.get(k, 0.0) or 0.0) - (prev.get(k, 0.0) or 0.0)
        c = w * d; contrib[k] = c; total += c
    return {"dnet": total, "contrib": contrib}
