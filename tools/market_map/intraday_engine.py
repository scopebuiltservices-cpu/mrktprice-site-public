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

def conformal_band(logpath, resid_by_h, alpha=0.90):
    """Distribution-free, TRIGGER-MATCHED band. resid_by_h[h] = list of historical post-trigger
    log-price forecast errors e = p_realized - p_forecast at horizon h. Returns (lo,hi) log-prices."""
    lo = []; hi = []
    ql = (1 - alpha) / 2.0; qh = (1 + alpha) / 2.0
    for h, lp in enumerate(logpath):
        res = resid_by_h.get(h) or resid_by_h.get(h + 1) or []
        if len(res) >= 8:
            lo.append(lp + _quantile(res, ql)); hi.append(lp + _quantile(res, qh))
        else:
            lo.append(float("nan")); hi.append(float("nan"))
    return lo, hi


# --------------------------------------------------------------------------- decision + coverage
def decision(p_T, hi_logpath, lo_logpath, h_idx, cost=0.0, G=1.0):
    """Act on the BOUND-adjusted payoff, not the point forecast, AND apply the regime gate at the
    ACTION layer: a hot regime (G<1) downweights size; a hard gate (G=0) vetoes the trade. 'tradable'
    requires a bound-implied edge over cost AND an open gate. Long score = upper-bound log-move minus
    cost; short score = lower-bound minus cost."""
    if h_idx >= len(hi_logpath):
        return {"tradable": False, "side": None, "edge": 0.0, "size": 0.0, "regimeG": round(G, 2)}
    long_s = hi_logpath[h_idx] - p_T - cost
    short_s = p_T - lo_logpath[h_idx] - cost
    side = "long" if (long_s > 0 and long_s >= short_s) else ("short" if short_s > 0 else None)
    edge = long_s if side == "long" else (short_s if side == "short" else max(long_s, short_s))
    tradable = bool(side and edge > 0 and G > 0)
    return {"tradable": tradable, "side": side if tradable else None, "edge": round(edge, 5),
            "size": round(max(G, 0.0), 2) if tradable else 0.0, "regimeG": round(G, 2)}

def coverage(hits):
    h = [1 if x else 0 for x in hits]
    return (sum(h) / len(h)) if h else None


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
    sigmas = [sig1] * P["H"]; ses = [seT] * P["H"]
    plo, phi = parametric_band(logpath, sigmas, ses)
    clo, chi = conformal_band(logpath, (params or {}).get("resid_by_h", {}), P["alpha"])
    # prefer conformal where available, else parametric (more-conservative spirit)
    lo = [clo[h] if clo[h] == clo[h] else plo[h] for h in range(len(logpath))]
    hi = [chi[h] if chi[h] == chi[h] else phi[h] for h in range(len(logpath))]
    dec = decision(p_T, hi, lo, P["H"] - 1, P["cost"], gates[T]["G"])
    res.update({
        "T_bucket": bars[T]["bucket"], "muT": muT, "seT": seT,
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
