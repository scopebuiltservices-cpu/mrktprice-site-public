#!/usr/bin/env python3
"""Intraday trigger -> projection engine  (Frontier Econometrics 2026 synthesis).

Pure stdlib. Detects an abnormal intraday state via TIME-OF-DAY-ROBUST volume + realized-variance
z-gates, confirms the state persists over CONSECUTIVE 15-minute windows together with an econometric
drift signal and a volatility-regime gate, then integrates per-window drift in LOG-PRICE space and
wraps the projected path in a TRIGGER-MATCHED conformal band (parametric forecast-SE band as a
fallback). A bound-adjusted decision rule decides 'tradable' vs 'conditional scenario', and a
coverage audit measures realized hit-rate.

Discipline (the rule that ties the spec together): every threshold, normalizer, standard error,
quantile and interval width used at trigger time T is computable from information available STRICTLY
<= T. No look-ahead, ever.  Mirrored 1:1 by intraday_engine.js for live rendering.

Symbols (15-min window k):  p_k = log P_k ,  r_k = p_k - p_{k-1}
  RV_k  = sum of sub-bar squared returns (or r_k^2 if sub-bars unavailable)
  bucket(k) = intraday clock id, e.g. the 10:00-10:15 slot across days
"""
from __future__ import annotations
import math

# --------------------------------------------------------------------------- robust stats
def _median(xs):
    s = sorted(x for x in xs if x is not None and x == x)
    n = len(s)
    if n == 0:
        return float("nan")
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])

def _mad(xs, med=None):
    s = [x for x in xs if x is not None and x == x]
    if not s:
        return 0.0
    m = _median(s) if med is None else med
    return 1.4826 * _median([abs(x - m) for x in s])

def _z(x, m, sd):
    return (x - m) / sd if (sd and sd > 0) else 0.0


# --------------------------------------------------------------------------- time-of-day normalizers
def tod_normalizers(hist_bars):
    """From HISTORICAL bars only, per intraday clock bucket, robust center/scale of log-volume and
    log-RV. hist_bars: iterable of {'bucket','vol','rv'}. Returns {bucket:{mV,sV,mRV,sRV}}."""
    by = {}
    for b in hist_bars:
        by.setdefault(b["bucket"], {"lv": [], "lrv": []})
        if b.get("vol", 0) > 0:
            by[b["bucket"]]["lv"].append(math.log(b["vol"]))
        if b.get("rv", 0) > 0:
            by[b["bucket"]]["lrv"].append(math.log(b["rv"]))
    out = {}
    for bk, d in by.items():
        mV = _median(d["lv"]); mRV = _median(d["lrv"])
        out[bk] = {"mV": mV, "sV": _mad(d["lv"], mV), "mRV": mRV, "sRV": _mad(d["lrv"], mRV)}
    return out

def abnormality(bar, norms):
    """zV, zRV for one bar given per-bucket normalizers (0 if the bucket is unseen)."""
    nb = norms.get(bar["bucket"])
    if not nb:
        return 0.0, 0.0
    zV = _z(math.log(bar["vol"]), nb["mV"], nb["sV"]) if bar.get("vol", 0) > 0 else 0.0
    zRV = _z(math.log(bar["rv"]), nb["mRV"], nb["sRV"]) if bar.get("rv", 0) > 0 else 0.0
    return zV, zRV

def gate_A(zV, zRV, thV, thRV):
    """User's volume + volatility threshold trip."""
    return 1 if (zV >= thV and zRV >= thRV) else 0


# --------------------------------------------------------------------------- drift / SE / regime
def ewma_drift(rets, lam=0.85):
    """Exponentially weighted mean of recent 15-min log returns (the per-window drift estimate)."""
    if not rets:
        return 0.0
    num = den = 0.0
    w = 1.0
    for r in reversed(rets):
        num += w * r; den += w; w *= lam
    return num / den if den else 0.0

def rolling_se(rets, mu):
    """Standard error of the drift estimate from rolling residual dispersion."""
    n = len(rets)
    if n < 3:
        return float("inf")
    var = sum((r - mu) ** 2 for r in rets) / (n - 1)
    return math.sqrt(var / n)

def realized_quarticity(subrets):
    """RQ_k = (M/3) * sum r^4 (Barndorff-Nielsen-Shephard). The asymptotic variance of RV is
    proportional to RQ, so a high RQ/RV^2 ratio means RV (and any vol-scaled band) is itself
    noisily measured -> the band should widen. Returns 0 when sub-window returns are unavailable."""
    m = len(subrets)
    if m < 1:
        return 0.0
    return (m / 3.0) * sum(r ** 4 for r in subrets)

def rq_band_inflation(rv, rq, cap=2.5):
    """Measurement-noise multiplier (>=1) for the per-window band, from the Barndorff-Nielsen-Shephard
    result that Var(RV) ~ (2/M)*IQ, i.e. the RELATIVE standard error of RV scales with sqrt(RQ)/RV.
    When RV is itself noisily measured (high RQ/RV^2, the HARQ insight), the vol-scaled band should
    widen. Returns 1.0 when RQ/RV are unavailable so the band degrades gracefully to the plain estimate.
    Calibrated so a clean Gaussian bar (RQ/RV^2 ~ 1) gives ~1.0 and noisy bars inflate up to `cap`."""
    if not (rv and rv > 0) or not (rq and rq > 0):
        return 1.0
    rel_se = (rq ** 0.5) / rv          # relative standard error of the variance estimate
    infl = 1.0 + max(0.0, rel_se - 1.0)
    return max(1.0, min(cap, infl))

def block_bootstrap_se(rets, block=4, B=200, seed=12345):
    """Moving-block bootstrap SE of the drift (mean) estimate. Unlike the iid rolling SE, it
    resamples contiguous blocks, so SERIAL DEPENDENCE in the 15-min returns inflates the SE
    instead of being ignored. Deterministic (seeded) so it is unit-testable."""
    import random
    n = len(rets)
    if n < 4:
        return float("inf")
    block = max(1, min(block, n))
    rng = random.Random(seed)
    means = []
    for _ in range(B):
        s = []
        while len(s) < n:
            start = rng.randrange(0, n)
            for j in range(block):
                s.append(rets[(start + j) % n])
        s = s[:n]
        means.append(sum(s) / n)
    mbar = sum(means) / B
    return math.sqrt(sum((mm - mbar) ** 2 for mm in means) / (B - 1))

def conservative_se(rets, mu, block=4, B=200, seed=12345):
    """Liao et al. robustness: a forecast SE should not be the naive in-sample/iid residual SE,
    which is too narrow for serially dependent or flexible estimators. Use the MORE CONSERVATIVE
    of the iid rolling SE and a moving-block bootstrap SE."""
    a = rolling_se(rets, mu)
    b = block_bootstrap_se(rets, block, B, seed)
    fin = [x for x in (a, b) if math.isfinite(x)]
    return max(fin) if fin else float("inf")

def signal_q(mu, se):
    return abs(mu) / se if (se and se > 0 and math.isfinite(se)) else 0.0

def high_vol_prob(rv_recent, rv_hist):
    """Filtered-probability proxy of the high-volatility regime: logistic of the robust RV z-score
    of the most recent window vs history. (A 2-state Markov-switching filter can replace this.)"""
    if not rv_hist or not rv_recent:
        return 0.0
    lrv = [math.log(x) for x in rv_hist if x > 0]
    m = _median(lrv); sd = _mad(lrv, m)
    z = _z(math.log(rv_recent), m, sd)
    return 1.0 / (1.0 + math.exp(-z))

def regime_gate(p_hv, rho=0.5, kappa=0.0):
    """Low-vol gating (Fang-Slepaczuk): full weight in calm regime, downweight (kappa) when hot."""
    return 1.0 if p_hv <= rho else kappa


# --------------------------------------------------------------------------- confirmation + trigger
def confirm_M(A, q, tau, sign_now, sign_prev):
    """M_k = A_k * B_k. Confirmation is about STATE PERSISTENCE + signal strength: B requires the drift
    signal to clear the threshold (q >= tau) with a stable sign. The volatility-regime gate is applied
    at the ACTION layer (decision), not here — vetoing confirmation on the very volatility that defines
    the breakout would be self-defeating."""
    B = 1 if (q >= tau and sign_now == sign_prev and sign_now != 0) else 0
    return A * B

def consecutive_trigger(M_seq, K):
    """First window where the consecutive-confirmation counter C reaches K. Returns (T_index, C_path)."""
    C = 0; path = []
    T = None
    for k, M in enumerate(M_seq):
        C = C + 1 if M == 1 else 0
        path.append(C)
        if T is None and C >= K:
            T = k
    return T, path


# --------------------------------------------------------------------------- projection + bands
def project_logpath(p_T, drifts):
    """Discrete anti-derivative of per-window drift: p_{T+h} = p_T + sum_{j<=h} mu. Returns log-prices."""
    out = []; p = p_T
    for mu in drifts:
        p += mu; out.append(p)
    return out

def parametric_band(logpath, sigmas, ses, z=1.6448536):
    """Accumulated forecast-SE band (diagonal approx): FSE_h = sqrt(sum sigma^2 + sum se^2).
    Returns (lo_logprice, hi_logprice) per horizon. z default ~ 90% two-sided."""
    lo = []; hi = []
    sv = 0.0; se2 = 0.0
    for h, lp in enumerate(logpath):
        sv += sigmas[h] ** 2 if h < len(sigmas) else 0.0
        se2 += ses[h] ** 2 if h < len(ses) else 0.0
        fse = math.sqrt(sv + se2)
        lo.append(lp - z * fse); hi.append(lp + z * fse)
    return lo, hi

def _quantile(xs, q):
    s = sorted(xs)
    if not s:
        return 0.0
    pos = q * (len(s) - 1)
    lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)

def _conformal_q(xs, p, upper):
    """Finite-sample split-conformal order-statistic quantile (the recipe that earns the 'distribution-free'
    label): upper tail uses index ceil(p*(n+1)), lower tail floor(p*(n+1)), clamped to [1,n]. This is the
    same order-statistic correction lineage.py uses — not a linearly-interpolated empirical quantile."""
    s = sorted(xs); n = len(s)
    if n == 0:
        return 0.0
    if upper:
        idx = min(n, max(1, int(math.ceil(p * (n + 1)))))
    else:
        idx = min(n, max(1, int(math.floor(p * (n + 1)))))
    return s[idx - 1]

def conformal_band(logpath, resid_by_h, alpha=0.90):
    """Distribution-free, TRIGGER-MATCHED band using FINITE-SAMPLE split-conformal order-statistic quantiles
    (not linearly-interpolated empirical quantiles). resid_by_h[h] = list of historical post-trigger log-price
    forecast errors e = p_realized - p_forecast at horizon h. Returns (lo,hi) log-prices."""
    lo = []; hi = []
    ql = (1 - alpha) / 2.0; qh = (1 + alpha) / 2.0
    for h, lp in enumerate(logpath):
        res = resid_by_h.get(h) or resid_by_h.get(h + 1) or []
        if len(res) >= 8:
            lo.append(lp + _conformal_q(res, ql, upper=False)); hi.append(lp + _conformal_q(res, qh, upper=True))
        else:
            lo.append(float("nan")); hi.append(float("nan"))
    return lo, hi


# --------------------------------------------------------------------------- decision + coverage
def decision(p_T, hi_logpath, lo_logpath, h_idx, cost=0.0, G=1.0):
    """LOWER-CONFIDENCE decision rule (conservative interval edge) + regime gate at the ACTION layer.

    The earlier rule used the OPTIMISTIC interval endpoint as reward (long = hi - p_T, short = p_T - lo).
    For any interval that straddles the current log-price that is positive whenever half-width > cost, so
    a zero point-forecast still reads 'tradable' — it converts predictive UNCERTAINTY into presumed profit
    and manufactures false positives. The correct conservative edge requires the trade to clear cost even
    at the UNFAVORABLE bound:
        long  edge = lo - p_T - cost   (go long only if even the lower bound beats current + cost)
        short edge = p_T - hi - cost   (go short only if even the upper bound is below current - cost)
    Both can be negative simultaneously (no directional edge), which is the correct answer for a symmetric
    band around the current price. The optimistic scores are still returned as diagnostics (optLong/optShort).
    A hot regime (G<1) downweights size; a hard gate (G=0) vetoes the trade."""
    if h_idx >= len(hi_logpath):
        return {"tradable": False, "side": None, "edge": 0.0, "size": 0.0, "regimeG": round(G, 2)}
    hi = hi_logpath[h_idx]; lo = lo_logpath[h_idx]
    long_s = lo - p_T - cost                 # conservative long edge (lower bound clears cost)
    short_s = p_T - hi - cost                # conservative short edge (upper bound clears cost)
    side = "long" if (long_s > 0 and long_s >= short_s) else ("short" if short_s > 0 else None)
    edge = long_s if side == "long" else (short_s if side == "short" else max(long_s, short_s))
    tradable = bool(side and edge > 0 and G > 0)
    return {"tradable": tradable, "side": side if tradable else None, "edge": round(edge, 5),
            "size": round(max(G, 0.0), 2) if tradable else 0.0, "regimeG": round(G, 2),
            "optLong": round(hi - p_T - cost, 5), "optShort": round(p_T - lo - cost, 5)}

def coverage(hits):
    h = [1 if x else 0 for x in hits]
    return (sum(h) / len(h)) if h else None

def audit_coverage(events, alpha=0.90):
    """Realized-coverage audit (the 'is the band honest?' loop). events: resolved triggers, each
    {lo,hi,center,realized,pT,gatePass,rwLo,rwHi} in consistent (log-)price units. Coverage near the
    target with NARROW bands is good; coverage only because the band is huge is not, so band width
    and a random-walk baseline are reported alongside. Mirrors auditCoverage() in intraday_engine.js."""
    if not events:
        return None
    def cov(evs):
        if not evs:
            return None
        return sum(1 for e in evs if e["lo"] <= e["realized"] <= e["hi"]) / len(evs)
    n = len(events)
    gated = [e for e in events if e.get("gatePass")]
    # Frontier p.10: predictive content is REGIME-DEPENDENT, so audit coverage conditionally, not only
    # in aggregate. Split the realized hit-rate by the calm (p_HV<=rho) vs hot (p_HV>rho) regime.
    calm = [e for e in events if e.get("hot") is False]
    hot = [e for e in events if e.get("hot") is True]
    rw = [e for e in events if e.get("rwLo") is not None]
    vb = [e for e in events if e.get("volLo") is not None]   # volatility-only band baseline
    bias = sum(e["realized"] - e["center"] for e in events) / n
    # avgBandWidth is mean(hi-lo) in LOG-price units == the spec's band-sharpness mean log(U/L).
    width = sum(e["hi"] - e["lo"] for e in events) / n
    da = sum(1 for e in events if (e["center"] >= e["pT"]) == (e["realized"] >= e["pT"])) / n
    rwcov = (sum(1 for e in rw if e["rwLo"] <= e["realized"] <= e["rwHi"]) / len(rw)) if rw else None
    vbcov = (sum(1 for e in vb if e["volLo"] <= e["realized"] <= e["volHi"]) / len(vb)) if vb else None
    return {"n": n, "target": alpha, "coverage": round(cov(events), 3),
            "condCoverageGated": round(cov(gated), 3) if gated else None,
            "condCoverageCalm": round(cov(calm), 3) if calm else None,
            "condCoverageHot": round(cov(hot), 3) if hot else None,
            "bias": round(bias, 6), "avgBandWidth": round(width, 6), "sharpness": round(width, 6),
            "directionalAccuracy": round(da, 3),
            "rwBaselineCoverage": round(rwcov, 3) if rwcov is not None else None,
            "volBaselineCoverage": round(vbcov, 3) if vbcov is not None else None}


# --------------------------------------------------------------------------- orchestration
def evaluate(bars, hist_bars, params=None):
    """Walk today's `bars` left-to-right with NO look-ahead, using `hist_bars` only for the robust
    normalizers and the trigger-matched conformal residuals. Returns the full decision object.

    bars / hist_bars items: {'bucket','vol','rv','ret','p'}  (p = log price)
    params: thV,thRV,tau,rho,kappa,K,H (horizon windows), alpha, cost, lam.
    """
    P = {"thV": 1.5, "thRV": 1.5, "tau": 1.5, "rho": 0.5, "kappa": 0.34,
         "K": 3, "H": 8, "alpha": 0.90, "cost": 0.0, "lam": 0.85, "warm": 6}
    if params:
        P.update(params)
    norms = tod_normalizers(hist_bars)
    rv_hist = [b["rv"] for b in hist_bars if b.get("rv", 0) > 0]

    M_seq = []; gates = []
    sign_prev = 0
    for k, b in enumerate(bars):
        zV, zRV = abnormality(b, norms)
        A = gate_A(zV, zRV, P["thV"], P["thRV"])
        past_rets = [bars[j]["ret"] for j in range(max(0, k - 20), k + 1)]   # info <= k only
        mu = ewma_drift(past_rets, P["lam"]); se = rolling_se(past_rets, mu)
        q = signal_q(mu, se)
        _rvwin = [bars[j].get("rv") for j in range(max(0, k - 3), k + 1) if bars[j].get("rv", 0) > 0]
        p_hv = high_vol_prob(_median(_rvwin) if _rvwin else b.get("rv"), rv_hist)   # smoothed persistent state
        G = regime_gate(p_hv, P["rho"], P["kappa"])
        sign_now = 1 if mu > 0 else (-1 if mu < 0 else 0)
        warm = k >= P["warm"]
        M = confirm_M(A, q, P["tau"], sign_now, sign_prev) if warm else 0
        M_seq.append(M)
        gates.append({"k": k, "zV": round(zV, 2), "zRV": round(zRV, 2), "A": A, "q": round(q, 2),
                      "pHV": round(p_hv, 2), "G": G, "mu": mu, "se": se, "M": M})
        sign_prev = sign_now

    T, C_path = consecutive_trigger(M_seq, P["K"])
    res = {"triggered": T is not None, "T": T, "C": C_path, "gates": gates, "params": P}
    if T is None:
        return res

    # project: damped persistence of the trigger-time drift over H windows
    muT = gates[T]["mu"]; seT = gates[T]["se"]
    sigT = math.sqrt(rolling_se([b["ret"] for b in bars[max(0, T - 20):T + 1]], muT) ** 2) if T >= 0 else 0.0
    drifts = [muT * (0.92 ** j) for j in range(P["H"])]
    p_T = bars[T]["p"]
    logpath = project_logpath(p_T, drifts)
    # per-window dispersion for the parametric band (recent realized 15-min vol)
    rr = [b["ret"] for b in bars[max(0, T - 20):T + 1]]
    sig1 = (sum((r - muT) ** 2 for r in rr) / max(len(rr) - 1, 1)) ** 0.5 if len(rr) > 2 else abs(muT) + 1e-6
    # Liao conservative SE for the band: the more conservative of iid-rolling and block-bootstrap SE,
    # so the parametric fallback band is honestly wide under serial dependence (never falsely narrow).
    seCons = conservative_se(rr, muT)
    if not math.isfinite(seCons):
        seCons = seT
    # RQ-aware widening (Frontier/HARQ): if the trigger-window variance is itself noisily measured
    # (high RQ/RV^2), inflate the per-window dispersion so the parametric band is not falsely tight.
    rqT = bars[T].get("rq"); rvT = bars[T].get("rv")
    rqInfl = rq_band_inflation(rvT, rqT)
    sigmas = [sig1 * rqInfl] * P["H"]; ses = [seCons] * P["H"]
    plo, phi = parametric_band(logpath, sigmas, ses)
    clo, chi = conformal_band(logpath, (params or {}).get("resid_by_h", {}), P["alpha"])
    # prefer conformal where available, else parametric (more-conservative spirit)
    lo = [clo[h] if clo[h] == clo[h] else plo[h] for h in range(len(logpath))]
    hi = [chi[h] if chi[h] == chi[h] else phi[h] for h in range(len(logpath))]
    dec = decision(p_T, hi, lo, P["H"] - 1, P["cost"], gates[T]["G"])
    res.update({
        "T_bucket": bars[T]["bucket"], "muT": muT, "seT": seT, "seConsT": seCons, "rqInfl": round(rqInfl, 3),
        "centerLog": logpath, "center": [math.exp(x) for x in logpath],
        "loLog": lo, "hiLog": hi, "lo": [math.exp(x) for x in lo], "hi": [math.exp(x) for x in hi],
        "bandSource": ["conformal" if clo[h] == clo[h] else "parametric" for h in range(len(logpath))],
        "decision": dec,
    })
    return res


if __name__ == "__main__":
    import random
    rng = random.Random(7)
    def mkbar(bucket, mu, sig, base_vol):
        r = rng.gauss(mu, sig); return {"bucket": bucket, "ret": r, "rv": r * r + 1e-8,
                                        "vol": base_vol * math.exp(rng.gauss(0, 0.3)), "p": 0.0}
    hist = [mkbar(b % 26, 0.0, 0.004, 1e6) for b in range(26 * 20)]
    today = [mkbar(k, 0.0, 0.004, 1e6) for k in range(26)]
    p = 4.6
    for b in today:
        p += b["ret"]; b["p"] = p
    out = evaluate(today, hist)
    print("triggered:", out["triggered"], "at T =", out["T"])
