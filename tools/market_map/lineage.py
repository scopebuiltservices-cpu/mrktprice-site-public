"""
lineage.py — Institutional cone "probability-lineage" core (server-side, pure stdlib).

Implements the mathematical objects from the Institutional Upgrade Blueprint, adapted to
MrktPrice's INTRADAY-WEIGHTED horizon set. Heavy fitting belongs server-side (SR 11-7
benchmarkability/validation); the browser renders a normalized payload.

Every function here is deterministic and unit-tested in test_lineage.py against planted
structure. No third-party deps.

Objects:
  - viterbi()                  MAP regime lineage (top branch) + log-prob
  - top_branches()             MAP + next-(k-1) branches with branch probability
  - branch_decomposition()     law of total variance -> diffusive vs branching confidence
  - bridge_touch_upper/lower() Brownian-bridge touch-before-finish probability
  - sigma_volume_matrix()      E[cumulative volume | k-sigma move, horizon]  (volume-ahead)
  - conformal_pad()            split-conformal quantile padding (finite-sample coverage)
  - hawkes_expected_count()    exp-kernel Hawkes integrated intensity (short-horizon volume)
  - straddle_labels()          honest "implied absolute move" vs "sigma-equivalent move"
  - event_variance()           term-structure event-variance extraction (Q measure)
  - house_blend()              omega_Q * sig_Q^2 + (1-omega_Q) * sig_P^2 + v_evt
  - node_payload()             assembles the exact lineage-node field set
"""
from __future__ import annotations
import math, random
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Sequence, Tuple

NEG_INF = float("-inf")

# ---- INTRADAY-WEIGHTED horizon set (user choice) -----------------------------
# primary = intraday + short; context = the longer tenors (computed but de-emphasized)
HORIZONS: List[Tuple[str, float, bool]] = [
    # (label, trading-days equivalent, is_primary)
    ("intraday", 0.25, True),
    ("1d",       1.0,  True),
    ("5d",       5.0,  True),
    ("10d",      10.0, False),
    ("20d",      20.0, False),
    ("63d",      63.0, False),
]
PRIMARY_HORIZONS = [h for h in HORIZONS if h[2]]


# ---- Viterbi MAP lineage -----------------------------------------------------
def viterbi(log_init: Sequence[float],
            log_trans: Sequence[Sequence[float]],
            log_lik: Sequence[Sequence[float]]) -> Dict:
    """Most-probable regime path (MAP lineage). All inputs in LOG space.
    log_lik[t][k] = log p(obs_t | regime k). Returns {path, logProb}."""
    T = len(log_lik)
    K = len(log_init)
    if T == 0:
        return {"path": [], "logProb": 0.0}
    dp = [[NEG_INF] * K for _ in range(T)]
    back = [[-1] * K for _ in range(T)]
    for k in range(K):
        dp[0][k] = log_init[k] + log_lik[0][k]
    for t in range(1, T):
        for k in range(K):
            best, arg = NEG_INF, -1
            for j in range(K):
                cand = dp[t - 1][j] + log_trans[j][k]
                if cand > best:
                    best, arg = cand, j
            dp[t][k] = best + log_lik[t][k]
            back[t][k] = arg
    last = max(range(K), key=lambda k: dp[T - 1][k])
    path = [0] * T
    path[T - 1] = last
    for t in range(T - 2, -1, -1):
        path[t] = back[t + 1][path[t + 1]]
    return {"path": path, "logProb": dp[T - 1][last]}


def top_branches(post_regime: Sequence[float],
                 trans: Sequence[Sequence[float]],
                 traj_density: Optional[Sequence[float]] = None,
                 k: int = 3) -> List[Dict]:
    """Top-k branches. branch probability = posterior regime mass * local transition
    self-mass * conditional trajectory density, normalized. Returns ranked list."""
    K = len(post_regime)
    if traj_density is None:
        traj_density = [1.0] * K
    raw = []
    for j in range(K):
        trans_mass = trans[j][j] if (j < len(trans) and j < len(trans[j])) else 1.0
        raw.append(max(0.0, post_regime[j]) * max(1e-12, trans_mass) * max(1e-12, traj_density[j]))
    s = sum(raw) or 1.0
    branches = [{"regime": j, "p": raw[j] / s} for j in range(K)]
    branches.sort(key=lambda b: -b["p"])
    return branches[:k]


# ---- Law of total variance: diffusive vs branching ---------------------------
def branch_decomposition(regime_weights: Sequence[float],
                         cond_means: Sequence[float],
                         cond_vars: Sequence[float]) -> Dict:
    """Var(R) = E[Var(R|z)] + Var(E[R|z]).
       within   = E[Var(R|z)]    -> diffusive confidence
       between  = Var(E[R|z])     -> branching confidence
    Returns shares in [0,1] plus the raw variances."""
    w = list(regime_weights)
    s = sum(w) or 1.0
    w = [x / s for x in w]
    within = sum(w[i] * cond_vars[i] for i in range(len(w)))
    mean = sum(w[i] * cond_means[i] for i in range(len(w)))
    between = sum(w[i] * (cond_means[i] - mean) ** 2 for i in range(len(w)))
    total = within + between
    if total <= 0:
        return {"within": 0.0, "between": 0.0, "total": 0.0,
                "diffusive_share": 0.0, "branching_share": 0.0, "mean": mean}
    return {"within": within, "between": between, "total": total,
            "diffusive_share": within / total, "branching_share": between / total,
            "mean": mean}


# ---- Brownian-bridge touch correction ----------------------------------------
def bridge_touch_upper(log_s0: float, log_s1: float, log_barrier: float, var_dt: float) -> float:
    """P(path crosses upper barrier b between two log-price nodes | endpoints)."""
    if log_barrier <= max(log_s0, log_s1):
        return 1.0
    if var_dt <= 0:
        return 0.0
    expo = -2.0 * (log_barrier - log_s0) * (log_barrier - log_s1) / var_dt
    return max(0.0, min(1.0, math.exp(expo)))


def bridge_touch_lower(log_s0: float, log_s1: float, log_barrier: float, var_dt: float) -> float:
    """P(path crosses lower barrier b between two log-price nodes | endpoints)."""
    if log_barrier >= min(log_s0, log_s1):
        return 1.0
    if var_dt <= 0:
        return 0.0
    expo = -2.0 * (log_s0 - log_barrier) * (log_s1 - log_barrier) / var_dt
    return max(0.0, min(1.0, math.exp(expo)))


# ---- Sigma-volume matrix (the "expected volume ahead" object) ----------------
def sigma_volume_matrix(paths: Sequence[Dict],
                        horizons: Sequence[str],
                        sigma_bins: Sequence[float]) -> Dict:
    """paths: list of {horizon, retZ, cumVol}. retZ = terminal return in sigma units.
    Returns out[horizon][\"lo..hi\"] = {n, meanCumVol}.  This is E[volume | k-sigma move]."""
    out: Dict[str, Dict] = {}
    for h in horizons:
        out[h] = {}
        for i in range(len(sigma_bins) - 1):
            lo, hi = sigma_bins[i], sigma_bins[i + 1]
            xs = [p["cumVol"] for p in paths
                  if p.get("horizon") == h and lo <= p.get("retZ", float("nan")) < hi]
            mean = (sum(xs) / len(xs)) if xs else None
            out[h]["%g..%g" % (lo, hi)] = {"n": len(xs), "meanCumVol": mean}
    return out


# ---- Split-conformal padding -------------------------------------------------
def conformal_pad(scores: Sequence[float], alpha: float = 0.10) -> float:
    """(1-alpha) finite-sample conformal quantile of nonconformity scores."""
    s = sorted(scores)
    if not s:
        return 0.0
    idx = min(len(s) - 1, math.ceil((1 - alpha) * (len(s) + 1)) - 1)
    return s[max(0, idx)]


def apply_symmetric_conformal(q_lo: float, q_hi: float, cal_y: Sequence[float],
                              cal_qlo: Sequence[float], cal_qhi: Sequence[float],
                              alpha: float = 0.10) -> Dict:
    scores = [max(cal_qlo[i] - cal_y[i], cal_y[i] - cal_qhi[i], 0.0) for i in range(len(cal_y))]
    pad = conformal_pad(scores, alpha)
    return {"qLo": q_lo - pad, "qHi": q_hi + pad, "pad": pad}


# ---- Exponential-kernel Hawkes short-horizon volume forecast -----------------
def hawkes_expected_count(now_min: float, event_times_min: Sequence[float],
                          mu_per_min: float, alpha: float, beta_per_min: float,
                          horizon_min: float) -> Dict:
    """Integrated exp-kernel Hawkes intensity over [now, now+horizon] -> expected count.
    lambda(t) = mu + sum alpha * exp(-beta (t - t_i))."""
    lam_now = mu_per_min
    for tm in event_times_min:
        age = now_min - tm
        if age >= 0:
            lam_now += alpha * math.exp(-beta_per_min * age)
    expected = mu_per_min * horizon_min
    for tm in event_times_min:
        age = now_min - tm
        if age >= 0:
            expected += (alpha / beta_per_min) * math.exp(-beta_per_min * age) * \
                        (1 - math.exp(-beta_per_min * horizon_min))
    return {"lambdaNow": lam_now, "expectedCount": expected}


# ---- Honest options labels: implied absolute move vs sigma-equivalent ---------
def straddle_labels(s0: float, sigma_annual: float, t_years: float,
                    straddle_price: Optional[float] = None) -> Dict:
    """ATM straddle ~ S0 * sigma * sqrt(T) * sqrt(2/pi)  (risk-neutral E|move|).
       sigma-equivalent (1-sigma) move = straddle * sqrt(pi/2).
    Returns both, clearly separated so the UI never mislabels a straddle as '1-sigma'."""
    sig_move = s0 * sigma_annual * math.sqrt(max(t_years, 0.0))   # 1-sigma price move
    if straddle_price is None:
        straddle_price = sig_move * math.sqrt(2.0 / math.pi)       # expected |move|
    implied_abs_move = straddle_price
    sigma_equiv_move = straddle_price * math.sqrt(math.pi / 2.0)
    return {"impliedAbsMove": implied_abs_move,       # E|move| (straddle)
            "sigmaEquivMove": sigma_equiv_move,       # 1-sigma move
            "sigma1Move": sig_move}                   # model 1-sigma (cross-check)


# ---- Event-variance extraction (Q measure, term-structure differencing) -------
def event_variance(w_q_plus: float, w_q_minus: float, base_var_per_t: float,
                   dt_span: float) -> float:
    """v_evt ~ max(0, w_Q(T+) - w_Q(T-) - base_var * (T+ - T-)).
    w_Q(T) = T * implied_total_variance(T). Isolates the discrete-event variance bump."""
    return max(0.0, w_q_plus - w_q_minus - base_var_per_t * dt_span)


def house_blend(sig_q2: float, sig_p2: float, v_evt: float, omega_q: float) -> float:
    """sigma_house^2 = omega_Q sig_Q^2 + (1-omega_Q) sig_P^2 + v_evt.
    omega_Q in [0,1], shrunk toward 0 when option liquidity is poor (FRTB modellability analog)."""
    w = max(0.0, min(1.0, omega_q))
    return w * sig_q2 + (1 - w) * sig_p2 + max(0.0, v_evt)


# ---- Lineage node payload (the exact field set) ------------------------------
@dataclass
class LineageNode:
    node_id: str
    parent_id: Optional[str]
    forecast_ts: str
    horizon_end_ts: str
    horizon: str
    q10: float
    q25: float
    q50: float
    q75: float
    q90: float
    q95: float
    p_node: float
    p_touch_up: Optional[float] = None
    p_touch_down: Optional[float] = None
    expected_cum_volume: Optional[float] = None
    sigma_equivalent: Optional[float] = None
    event_var_share: Optional[float] = None
    regime_probs: List[float] = field(default_factory=list)
    confidence_decomp: Dict = field(default_factory=dict)   # branch/diffusion/calibration
    drivers_ranked: List[Dict] = field(default_factory=list)  # {name, contrib, sign, label}
    provenance: Dict = field(default_factory=dict)            # sources + timestamps
    validation_snapshot: Dict = field(default_factory=dict)   # coverage/CRPS/PIT for h x regime
    reasoning_text: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


# Driver label discipline: associated (predictive only) / event-linked / causal
DRIVER_LABELS = ("associated", "event-linked", "causal")


def driver_contributions(regime_post: Sequence[float],
                         betas: Sequence[float],
                         dfactors: Sequence[float],
                         names: Sequence[str],
                         labels: Optional[Sequence[str]] = None) -> List[Dict]:
    """c_j = pi(z) |beta_j| |df_j| / sum_l pi(z) |beta_l| |df_l|.  Ranked, label-disciplined."""
    pi = sum(regime_post) / len(regime_post) if regime_post else 1.0
    raw = [pi * abs(betas[j]) * abs(dfactors[j]) for j in range(len(names))]
    s = sum(raw) or 1.0
    out = []
    for j in range(len(names)):
        lab = (labels[j] if labels and j < len(labels) else "associated")
        if lab not in DRIVER_LABELS:
            lab = "associated"
        out.append({"name": names[j], "contrib": raw[j] / s,
                    "sign": (1 if betas[j] * dfactors[j] >= 0 else -1), "label": lab})
    out.sort(key=lambda d: -d["contrib"])
    return out


def reasoning_from_fields(node: LineageNode) -> str:
    """Generate human-readable summary FROM FIELDS ONLY (no free-form guessing)."""
    parts = [f"{node.horizon}: median {node.q50:.2f} (10-90 {node.q10:.2f}-{node.q90:.2f}),",
             f"branch prob {node.p_node:.0%}."]
    if node.p_touch_up is not None:
        parts.append(f"Touch-up {node.p_touch_up:.0%} / touch-down {(node.p_touch_down or 0):.0%}.")
    if node.expected_cum_volume is not None:
        parts.append(f"Expected volume to node {node.expected_cum_volume:,.0f}.")
    cd = node.confidence_decomp or {}
    if cd:
        parts.append(f"Confidence: {cd.get('branching_share',0):.0%} branch / "
                     f"{cd.get('diffusive_share',0):.0%} diffusion.")
    if node.drivers_ranked:
        d = node.drivers_ranked[0]
        parts.append(f"Top driver {d['name']} ({d['label']}, {d['contrib']:.0%}).")
    return " ".join(parts)


# ============================================================================
# Phase 2 — Forecast core: Gaussian HMM regime inference + lineage object
# ============================================================================
def _logsumexp(xs: Sequence[float]) -> float:
    m = max(xs)
    if m == NEG_INF:
        return NEG_INF
    return m + math.log(sum(math.exp(x - m) for x in xs))


def _norm_logpdf(x: float, mu: float, var: float) -> float:
    var = max(var, 1e-12)
    return -0.5 * (math.log(2 * math.pi * var) + (x - mu) ** 2 / var)


def gaussian_hmm_fit(returns: Sequence[float], K: int = 2, iters: int = 60,
                     seed: int = 0) -> Dict:
    """Baum-Welch EM for a K-state Gaussian HMM (scalar emissions). Returns regimes
    ordered by ascending mean (state 0 = most bearish). Stable log-space FB."""
    x = [r for r in returns if r == r]            # drop NaN
    T = len(x)
    if T < 3 * K:
        return {"K": K, "ok": False}
    lo, hi = min(x), max(x)
    gvar = (sum((v - sum(x) / T) ** 2 for v in x) / T) or 1e-6
    means = [lo + (hi - lo) * (k + 0.5) / K for k in range(K)]
    vars = [gvar] * K
    pi = [1.0 / K] * K
    trans = [[(0.90 if i == j else 0.10 / (K - 1)) for j in range(K)] for i in range(K)]

    gamma = [[1.0 / K] * K for _ in range(T)]
    for _ in range(iters):
        ll = [[_norm_logpdf(x[t], means[k], vars[k]) for k in range(K)] for t in range(T)]
        # forward
        la = [[NEG_INF] * K for _ in range(T)]
        for k in range(K):
            la[0][k] = math.log(max(pi[k], 1e-300)) + ll[0][k]
        ltr = [[math.log(max(trans[i][j], 1e-300)) for j in range(K)] for i in range(K)]
        for t in range(1, T):
            for k in range(K):
                la[t][k] = _logsumexp([la[t - 1][j] + ltr[j][k] for j in range(K)]) + ll[t][k]
        # backward
        lb = [[NEG_INF] * K for _ in range(T)]
        for k in range(K):
            lb[T - 1][k] = 0.0
        for t in range(T - 2, -1, -1):
            for k in range(K):
                lb[t][k] = _logsumexp([ltr[k][j] + ll[t + 1][j] + lb[t + 1][j] for j in range(K)])
        # gamma + xi
        for t in range(T):
            denom = _logsumexp([la[t][k] + lb[t][k] for k in range(K)])
            for k in range(K):
                gamma[t][k] = math.exp(la[t][k] + lb[t][k] - denom)
        xi_sum = [[0.0] * K for _ in range(K)]
        for t in range(T - 1):
            denom = _logsumexp([la[t][i] + ltr[i][j] + ll[t + 1][j] + lb[t + 1][j]
                                for i in range(K) for j in range(K)])
            for i in range(K):
                for j in range(K):
                    xi_sum[i][j] += math.exp(la[t][i] + ltr[i][j] + ll[t + 1][j] + lb[t + 1][j] - denom)
        # M-step
        pi = [max(gamma[0][k], 1e-8) for k in range(K)]
        s = sum(pi); pi = [p / s for p in pi]
        for i in range(K):
            row = xi_sum[i]; rs = sum(row) or 1e-12
            trans[i] = [v / rs for v in row]
        for k in range(K):
            wsum = sum(gamma[t][k] for t in range(T)) or 1e-12
            means[k] = sum(gamma[t][k] * x[t] for t in range(T)) / wsum
            vars[k] = max(1e-10, sum(gamma[t][k] * (x[t] - means[k]) ** 2 for t in range(T)) / wsum)
    # order by ascending mean for stable labels
    order = sorted(range(K), key=lambda k: means[k])
    inv = {old: new for new, old in enumerate(order)}
    means = [means[o] for o in order]
    vars = [vars[o] for o in order]
    pi = [pi[o] for o in order]
    trans = [[trans[order[i]][order[j]] for j in range(K)] for i in range(K)]
    post_last = [gamma[T - 1][o] for o in order]
    return {"K": K, "ok": True, "means": means, "vars": vars, "trans": trans,
            "pi": pi, "post_last": post_last}


def lineage_object(returns: Sequence[float], horizons=HORIZONS,
                   step_days_per_unit: float = 5.0, K: int = 2) -> Optional[Dict]:
    """Fit HMM to (weekly) returns and emit the per-ticker lineage payload:
    regime posterior, transition matrix, top branches, and per-horizon diffusive-vs-
    branching confidence split + MAP-branch drift/vol. step_days_per_unit: trading days
    per return step (weekly = 5)."""
    fit = gaussian_hmm_fit(returns, K=K)
    if not fit.get("ok"):
        return None
    post = fit["post_last"]
    trans = fit["trans"]
    means = fit["means"]
    vars = fit["vars"]
    branches = top_branches(post, trans, k=min(3, K))
    regime_now = max(range(K), key=lambda k: post[k])
    hz = {}
    for label, days, _primary in horizons:
        steps = days / step_days_per_unit                   # return-steps in this horizon
        hmeans = [means[k] * steps for k in range(K)]        # drift scales linearly
        hvars = [vars[k] * steps for k in range(K)]          # diffusion variance additive
        dec = branch_decomposition(post, hmeans, hvars)
        mapk = branches[0]["regime"]
        hz[label] = {
            "diffusive": round(dec["diffusive_share"], 4),
            "branching": round(dec["branching_share"], 4),
            "mapDrift": round(hmeans[mapk], 6),
            "mapVol": round(math.sqrt(max(hvars[mapk], 0)), 6),
            "totVol": round(math.sqrt(max(dec["total"], 0)), 6),
            # per-regime drift/vol so the UI can draw the next-best branches as ribbons too
            "rd": [round(m, 6) for m in hmeans],
            "rv": [round(math.sqrt(max(v, 0)), 6) for v in hvars],
        }
    return {
        "K": K, "regimeNow": regime_now,
        "post": [round(p, 4) for p in post],
        "trans": [[round(v, 4) for v in row] for row in trans],
        "means": [round(m, 6) for m in means],
        "vols": [round(math.sqrt(max(v, 0)), 6) for v in vars],
        "branches": [{"regime": b["regime"], "p": round(b["p"], 4)} for b in branches],
        "horizons": hz,
        "valid": validation_snapshot(returns, fit, HORIZONS, step_days_per_unit),
        "stepDays": step_days_per_unit,
    }


# ============================================================================
# Phase 3 — Calibration: proper scoring + split-conformal by regime x horizon
# ============================================================================
SQRT2 = math.sqrt(2.0)
SQRT2PI = math.sqrt(2.0 * math.pi)
INV_SQRT_PI = 1.0 / math.sqrt(math.pi)


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / SQRT2))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT2PI


def crps_gaussian(y: float, mu: float, sigma: float) -> float:
    """Closed-form CRPS for a Gaussian predictive (Gneiting & Raftery)."""
    sigma = max(sigma, 1e-12)
    w = (y - mu) / sigma
    return sigma * (w * (2.0 * norm_cdf(w) - 1.0) + 2.0 * norm_pdf(w) - INV_SQRT_PI)


def interval_score(y: float, lo: float, hi: float, alpha: float) -> float:
    """Winkler/Gneiting interval score for a (1-alpha) central interval. Lower is better."""
    s = (hi - lo)
    if y < lo:
        s += (2.0 / alpha) * (lo - y)
    elif y > hi:
        s += (2.0 / alpha) * (y - hi)
    return s


def wilson_interval(k: int, n: int, z: float = 1.959964) -> Tuple[float, float]:
    """Wilson score CI for a binomial hit-rate (not the lazy Wald interval)."""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def pit_ks(pits: Sequence[float]) -> Dict:
    """KS distance of PIT values from Uniform(0,1) + asymptotic p. Uniform == calibrated."""
    n = len(pits)
    if n == 0:
        return {"D": None, "p": None, "n": 0}
    s = sorted(pits)
    D = 0.0
    for i, u in enumerate(s):
        D = max(D, abs((i + 1) / n - u), abs(u - i / n))
    lam = (math.sqrt(n) + 0.12 + 0.11 / math.sqrt(n)) * D
    # asymptotic Kolmogorov tail
    p = 2.0 * sum((-1) ** (j - 1) * math.exp(-2.0 * j * j * lam * lam) for j in range(1, 50))
    return {"D": D, "p": max(0.0, min(1.0, p)), "n": n}


def dkw_band(n: int, alpha: float = 0.05) -> Optional[float]:
    """Dvoretzky-Kiefer-Wolfowitz uniform band half-width for the empirical CDF."""
    if n <= 0:
        return None
    return math.sqrt(math.log(2.0 / alpha) / (2.0 * n))


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _var(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def _quantile(xs: Sequence[float], q: float) -> float:
    """Linear-interpolation empirical quantile (numpy default)."""
    s = sorted(xs); n = len(s)
    if n == 0:
        return 0.0
    if n == 1:
        return s[0]
    pos = q * (n - 1); lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def garch11_fit(returns: Sequence[float]) -> Optional[Dict]:
    """GARCH(1,1) variance-targeting QMLE: uncond var fixed to the sample var, (alpha,beta)
    found by 2-D grid + local refine on the Gaussian quasi-log-likelihood (alpha+beta<1).
    Pure-stdlib, no optimizer dependency."""
    r = [v for v in returns if v == v]
    n = len(r)
    if n < 40:
        return None
    uv = _var(r)
    if uv <= 0:
        return None

    def nll(a, b):
        if a < 0 or b < 0 or a + b >= 0.999:
            return 1e18
        om = (1 - a - b) * uv; h = uv; s = 0.0
        for t in range(1, n):
            h = om + a * r[t - 1] * r[t - 1] + b * h; h = max(h, 1e-14)
            s += math.log(h) + r[t] * r[t] / h
        return 0.5 * s
    best = None
    for a in (0.02, 0.05, 0.08, 0.12, 0.16, 0.20, 0.25, 0.30):
        for b in (0.50, 0.60, 0.70, 0.78, 0.85, 0.90, 0.94, 0.97):
            v = nll(a, b)
            if best is None or v < best[0]:
                best = (v, a, b)
    _, a, b = best; step = 0.04
    for _ in range(6):
        improved = False
        for da in (-step, 0, step):
            for db in (-step, 0, step):
                na, nb = a + da, b + db
                if na <= 0 or nb <= 0 or na + nb >= 0.999:
                    continue
                v = nll(na, nb)
                if v < best[0]:
                    best = (v, na, nb); a, b = na, nb; improved = True
        if not improved:
            step *= 0.5
    _, a, b = best
    return {"omega": (1 - a - b) * uv, "alpha": a, "beta": b, "uncondVar": uv}


def garch11_nstep_var(fit: Dict, returns: Sequence[float], n: int) -> float:
    """Aggregate GARCH(1,1) variance over an n-step horizon: sum_{k=1..n} E[h_{t+k}],
    E[h_{t+k}] = uncond + (alpha+beta)^{k-1}(h_{t+1} - uncond)."""
    r = [v for v in returns if v == v]
    a = fit["alpha"]; b = fit["beta"]; om = fit["omega"]; uv = fit["uncondVar"]
    h = uv
    for t in range(1, len(r)):
        h = om + a * r[t - 1] * r[t - 1] + b * h
    h1 = om + a * r[-1] * r[-1] + b * h
    ph = a + b; tot = 0.0
    for kk in range(0, n):
        tot += uv + (ph ** kk) * (h1 - uv)
    return max(tot, 1e-14)


def calibrate_horizon(returns: Sequence[float], n_steps: int,
                      regimes: Optional[Sequence[int]] = None,
                      window: int = 26, alpha: float = 0.10) -> Optional[Dict]:
    """Studentized, ASYMMETRIC split-conformal calibration of an n-step predictive with an
    H-EMBARGO between the calibration and test folds (acceptance criteria #1-#10).

    Walk-forward samples (no lookahead): each i fits mu/sigma on the trailing `window` STRICTLY
    before i, with outcome y=sum(r[i:i+n]) (label matures only after n steps, criterion #2).
    Samples are split 60/40 into calibration/test with n observations PURGED at the boundary so
    their n-step outcomes can't overlap (criterion #3). Studentized residuals e=(y-mu_n)/sig_n on
    the calibration fold give SEPARATE lower/upper empirical quantiles qLo/qHi (criteria #5,#6).
    Coverage / Wilson CI / interval score / mean width / CRPS / PIT-KS are reported on the TEST
    fold only, pooled and by regime (criteria #7,#8,#10). `coverageGaussian` keeps the naive
    symmetric +/-z number so the optimism the embargo+asymmetry remove is visible."""
    r = [v for v in returns if v == v]
    T = len(r)
    n = max(1, int(n_steps))
    z = 1.6448536269514722  # one-sided 95% -> 90% central
    if T < window + 3 * n + 20:
        return None
    samples = []  # (i, mu_n, sig_n, y, regime)
    for i in range(window, T - n + 1):
        win = r[i - window:i]
        mu = _mean(win); var = _var(win)
        mu_n = n * mu; sig_n = math.sqrt(max(n * var, 1e-12))
        y = sum(r[i:i + n])
        rg = regimes[i] if (regimes is not None and i < len(regimes)) else None
        samples.append((i, mu_n, sig_n, y, rg))
    M = len(samples)
    if M < 30:
        return None
    cut = int(M * 0.6)
    cal = samples[:max(1, cut - n)]   # purge: drop last n of calibration fold
    test = samples[cut + n:]          # embargo: drop first n of test fold
    if len(cal) < 15 or len(test) < 15:
        return None
    embargo_gap = test[0][0] - cal[-1][0]
    # finite-sample split-conformal quantiles of the studentized calibration residuals: the
    # ceil((1-a/2)(ne+1))-th order statistic (upper) and floor((a/2)(ne+1))-th (lower) guarantee
    # marginal coverage >= 1-alpha (Vovk; Lei et al.) — widens slightly vs the plain quantile at small ne.
    e_sorted = sorted((s[3] - s[1]) / s[2] for s in cal)
    ne = len(e_sorted)
    qHi = e_sorted[min(ne, max(1, math.ceil((1.0 - alpha / 2.0) * (ne + 1)))) - 1]
    qLo = e_sorted[min(ne, max(1, math.floor((alpha / 2.0) * (ne + 1)))) - 1]
    ea_sorted = sorted(abs(x) for x in e_sorted)
    qSym = ea_sorted[min(ne, max(1, math.ceil((1.0 - alpha) * (ne + 1)))) - 1]
    # REGIME-CONDITIONED conformal: SEPARATE lower/upper finite-sample quantiles per regime, computed from
    # that regime's OWN calibration residuals (not just the pooled set), so coverage can be conditioned by
    # regime rather than only sliced afterward. Falls back to the pooled qLo/qHi where a regime is too thin.
    MIN_REG_CAL = 20
    reg_e: Dict[int, List[float]] = {}
    for s in cal:
        if s[4] is not None:
            reg_e.setdefault(s[4], []).append((s[3] - s[1]) / s[2])
    reg_q: Dict[int, tuple] = {}
    for rg, es in reg_e.items():
        if len(es) >= MIN_REG_CAL:
            es2 = sorted(es); m = len(es2)
            qh = es2[min(m, max(1, math.ceil((1.0 - alpha / 2.0) * (m + 1)))) - 1]
            ql = es2[min(m, max(1, math.floor((alpha / 2.0) * (m + 1)))) - 1]
            reg_q[rg] = (ql, qh)
    covA = covS = covG = covRC = 0
    widths, crps_l, isc_l, pits = [], [], [], []
    reg_cov: Dict[int, List[int]] = {}
    reg_rc: Dict[int, List[int]] = {}
    for (i, mu_n, sig_n, y, rg) in test:
        loA = mu_n + qLo * sig_n; hiA = mu_n + qHi * sig_n
        cA = 1 if loA <= y <= hiA else 0; covA += cA
        # regime-conditioned padded interval: use the regime's own quantiles when available, else pooled
        qlo_rc, qhi_rc = reg_q.get(rg, (qLo, qHi))
        loRC = mu_n + qlo_rc * sig_n; hiRC = mu_n + qhi_rc * sig_n
        cRC = 1 if loRC <= y <= hiRC else 0; covRC += cRC
        loS = mu_n - qSym * sig_n; hiS = mu_n + qSym * sig_n
        covS += 1 if loS <= y <= hiS else 0
        loG = mu_n - z * sig_n; hiG = mu_n + z * sig_n
        covG += 1 if loG <= y <= hiG else 0
        widths.append(hiA - loA)
        crps_l.append(crps_gaussian(y, mu_n, sig_n))
        isc_l.append(interval_score(y, loA, hiA, alpha))
        pits.append(norm_cdf((y - mu_n) / sig_n))
        if rg is not None:
            reg_cov.setdefault(rg, []).append(cA)
            reg_rc.setdefault(rg, []).append(cRC)
    mt = len(test); k = covA
    wlo, whi = wilson_interval(k, mt)
    by_reg = {}
    for rg, cs in reg_cov.items():
        if len(cs) >= 15:
            by_reg[str(rg)] = {"n": len(cs), "coverage": round(sum(cs) / len(cs), 3)}
    by_reg_conf = {}
    for rg, (ql, qh) in reg_q.items():
        rc = reg_rc.get(rg, [])
        by_reg_conf[str(rg)] = {"nCal": len(reg_e[rg]), "qLo": round(ql, 4), "qHi": round(qh, 4),
                                "coverage": (round(sum(rc) / len(rc), 3) if rc else None)}
    ks = pit_ks(pits)
    return {
        "n": mt, "nSteps": n, "nCal": len(cal), "embargo": n, "embargoGap": embargo_gap,
        "coverage": round(k / mt, 3), "wilsonLo": round(wlo, 3), "wilsonHi": round(whi, 3),
        "coverageGaussian": round(covG / mt, 3), "coverageSym": round(covS / mt, 3),
        "qLo": round(qLo, 4), "qHi": round(qHi, 4), "target": round(1 - alpha, 3),
        # SCORING OBJECTS ARE DISTINCT (audit fix): crps + pit score the BASE Gaussian predictive
        # N(mu_n, sig_n); intervalScore + coverage score the PUBLISHED conformal band. The *Gaussian keys
        # make that explicit; the unsuffixed crps/pitKS/pitUniformP are back-compat aliases of the Gaussian
        # metrics, and scoredObject states which object each metric evaluates.
        "crps": round(_mean(crps_l), 6), "crpsGaussian": round(_mean(crps_l), 6),
        "intervalScore": round(_mean(isc_l), 6),
        "widthMean": round(_mean(widths), 6),
        "pitKS": (round(ks["D"], 3) if ks["D"] is not None else None),
        "pitUniformP": (round(ks["p"], 3) if ks["p"] is not None else None),
        "pitGaussianKS": (round(ks["D"], 3) if ks["D"] is not None else None),
        "pitGaussianUniformP": (round(ks["p"], 3) if ks["p"] is not None else None),
        "scoredObject": {"crps": "gaussianCenterline", "pit": "gaussianCenterline", "interval": "conformalBand"},
        "dkw": (round(dkw_band(mt), 4)),
        "byRegime": by_reg,
        # schema-promised fields, now genuinely emitted: conformalPad = extra σ the (1-alpha) conformal band
        # adds over the naive Gaussian z-band; coveragePadded = coverage of the REGIME-CONDITIONED conformal
        # band (regime-specific quantiles where available, pooled fallback); byRegimeConformal exposes the
        # per-regime quantiles + their conditioned coverage.
        "conformalPad": round(qSym - z, 4),
        "coveragePadded": round(covRC / mt, 3),
        "regimeConditioned": bool(reg_q),
        "byRegimeConformal": by_reg_conf,
        "calibrated": bool(wlo <= (1 - alpha) <= whi),
    }


def _decode_path(returns: Sequence[float], fit: Dict) -> List[int]:
    """Viterbi MAP regime path under fitted params (for regime-conditioned calibration)."""
    r = [v for v in returns if v == v]
    K = fit["K"]; means = fit["means"]; vars = fit["vars"]
    li = [math.log(max(p, 1e-300)) for p in fit["pi"]]
    lt = [[math.log(max(fit["trans"][i][j], 1e-300)) for j in range(K)] for i in range(K)]
    ll = [[_norm_logpdf(x, means[k], vars[k]) for k in range(K)] for x in r]
    return viterbi(li, lt, ll)["path"]


def validation_snapshot(returns: Sequence[float], fit: Dict, horizons=HORIZONS,
                        step_days_per_unit: float = 5.0) -> Dict:
    """Per-horizon (and per-regime) calibration ledger from walk-forward scoring."""
    path = _decode_path(returns, fit) if fit.get("ok") else None
    out = {}
    for label, days, _primary in horizons:
        n = max(1, round(days / step_days_per_unit))
        c = calibrate_horizon(returns, n, regimes=path)
        if c:
            out[label] = c
    return out


# ============================================================================
# Phase 4 — Volume & impact: first-passage touch, sigma-volume matrix, RVOL base
# ============================================================================
def first_passage_up(a: float, mu: float, sigma: float) -> float:
    """P(running max of arithmetic BM (mu, sigma) over the horizon reaches level a>0).
    a = log(barrier/S) > 0; mu, sigma are TOTAL drift/stdev over the horizon (log space).
    Reflection principle with drift. Driftless: 2*Phi(-a/sigma)."""
    if a <= 0:
        return 1.0
    if sigma <= 0:
        return 0.0
    t1 = norm_cdf((mu - a) / sigma)
    t2 = math.exp(min(2.0 * mu * a / (sigma * sigma), 700.0)) * norm_cdf((-mu - a) / sigma)
    return max(0.0, min(1.0, t1 + t2))


def first_passage_down(a: float, mu: float, sigma: float) -> float:
    """P(running min reaches level a<0). a = log(barrier/S) < 0. By reflection of -X."""
    if a >= 0:
        return 1.0
    return first_passage_up(-a, -mu, sigma)


def _log_returns(closes: Sequence[float]) -> List[float]:
    out = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0 and closes[i] > 0:
            out.append(math.log(closes[i] / closes[i - 1]))
    return out


def volume_ahead(rows: Sequence[Sequence], horizons=HORIZONS,
                 sigma_bins=(-3, -2, -1, 0, 1, 2, 3)) -> Dict:
    """From daily [date, close, vol] rows build the sigma-volume matrix
    M[horizon]["lo..hi"] = {n, meanCumVol} = E[cumulative volume | terminal kσ move], plus a
    volume baseline for RVOL/Hawkes. retZ = h-step log-return / (daily σ · √h) (global σ)."""
    closes = [float(r[1]) for r in rows if r[1] is not None]
    vols = [float(r[2]) for r in rows if len(r) > 2 and r[2] is not None]
    if len(closes) < 40 or len(vols) != len(closes):
        return {"sigvol": {}, "base": {}}
    lr = _log_returns(closes)
    sd = math.sqrt(_var(lr)) if len(lr) > 2 else 0.0
    paths = []
    labels = []
    for label, days, _p in horizons:
        h = max(1, round(days))
        labels.append(label)
        denom = (sd * math.sqrt(h)) or 1e-9
        for i in range(0, len(closes) - h):
            if closes[i] <= 0 or closes[i + h] <= 0:
                continue
            rh = math.log(closes[i + h] / closes[i])
            cum = sum(vols[i + 1:i + h + 1])
            paths.append({"horizon": label, "retZ": rh / denom, "cumVol": cum})
    sv = sigma_volume_matrix(paths, labels, list(sigma_bins))
    # round meanCumVol
    for h in sv:
        for b in sv[h]:
            mv = sv[h][b]["meanCumVol"]
            if mv is not None:
                sv[h][b]["meanCumVol"] = int(round(mv))
    last20 = vols[-20:] if len(vols) >= 20 else vols
    logv = [math.log(v) for v in vols if v > 0]
    # lag-1 autocorrelation of log-volume = self-excitation / clustering proxy (Hawkes-adjacent)
    acf1 = None
    if len(logv) > 5:
        m = _mean(logv)
        num = sum((logv[i] - m) * (logv[i - 1] - m) for i in range(1, len(logv)))
        den = sum((v - m) ** 2 for v in logv) or 1e-9
        acf1 = num / den
    base = {
        "avgVol20": int(round(_mean(last20))) if last20 else None,
        "medVol": int(round(sorted(vols)[len(vols) // 2])) if vols else None,
        "volOfVol": round(math.sqrt(_var(logv)), 4) if len(logv) > 2 else None,
        "volAcf1": (round(acf1, 4) if acf1 is not None else None),   # >0 = bursty/clustered
        "dailySigma": round(sd, 6),
    }
    return {"sigvol": sv, "base": base}


def _sigma_h(lr: Sequence[float], h: int, sd: float) -> float:
    """Horizon σ as a FIRST-CLASS blended forecast — the single source of truth for H-step scale. Prefers
    metrics.sigma_horizon (empirical HV term structure + EWMA recency + bounded variance-ratio multiplier)
    over the unconditional sd·√h, falling back to sd·√h only when the blended estimate is unavailable
    (short series). This replaces silent √H scaling in the forward-looking forecast band per the
    rolling-HV/conformal design note."""
    try:
        import metrics
        s = metrics.sigma_horizon(list(lr), int(h))
        if s is not None and s == s and s > 0:
            return s
    except Exception:
        pass
    return sd * math.sqrt(h)


def touch_odds(rows: Sequence[Sequence], horizons=HORIZONS,
               lookback: int = 20, mu_per_day: float = 0.0) -> Dict:
    """Per-horizon touch-before-finish odds to the recent high (up) and low (down), via first-passage with
    the name's blended HORIZON σ (metrics.sigma_horizon, √h fallback). Returns {horizon: {pUp,pDn,levels}}."""
    closes = [float(r[1]) for r in rows if r[1] is not None]
    if len(closes) < lookback + 5:
        return {}
    S = closes[-1]
    lr = _log_returns(closes)
    sd = math.sqrt(_var(lr)) if len(lr) > 2 else 0.0
    win = closes[-lookback:]
    hi = max(win); lo = min(win)
    out = {}
    for label, days, _p in horizons:
        h = max(1, round(days))
        mu_h = mu_per_day * h
        sig_h = _sigma_h(lr, h, sd)            # blended horizon σ (single source of truth), √h fallback
        a_up = math.log(hi / S) if (hi > S and S > 0) else None
        a_dn = math.log(lo / S) if (lo < S and S > 0) else None
        out[label] = {
            "pUp": round(first_passage_up(a_up, mu_h, sig_h), 4) if a_up is not None else 1.0,
            "pDn": round(first_passage_down(a_dn, mu_h, sig_h), 4) if a_dn is not None else 1.0,
            "levelHigh": round(hi, 4), "levelLow": round(lo, 4), "S": round(S, 4),
        }
    return out


# ============================================================================
# Phase 5.5 — options-implied P/Q layer (Girsanov P<->Q discipline, honest labels)
# ============================================================================
def pq_layer(hz: Dict, iv_annual: Optional[float], iv_days: int = 30,
             earn_days_ahead: Optional[float] = None, omega_q: float = 0.5) -> Dict:
    """Per-horizon physical (P) vs risk-neutral (Q) variance, from the per-horizon unconditional
    vol (totVol = sigma_P, return-space) and an ATM implied vol (annualized) sqrt-time-scaled to
    each horizon (CME convention). Emits:
      sigP, sigQ, sigHouse (= omega_Q sigQ^2 + (1-omega_Q) sigP^2),
      eventShare = max(0, sigQ^2 - sigP^2)/sigQ^2   (implied-over-realized excess / VRP proxy;
                   concentrated around a catalyst when one is in-window — evtIn flags that),
      impliedAbsMove = sigQ*sqrt(2/pi)  (E|move|, the straddle),  sigmaEquiv = sigQ (1-sigma move).
    Keeps P and Q as separate, clearly-labeled quantities (never blends a straddle into a 1-sigma)."""
    DAYS = {h[0]: h[1] for h in HORIZONS}
    has_iv = (iv_annual is not None and iv_annual > 0)
    w = max(0.0, min(1.0, omega_q)) if has_iv else 0.0
    out_h = {}
    for label, H in (hz or {}).items():
        days = DAYS.get(label, 1)
        sigP = H.get("totVol")
        sigQ = (iv_annual * math.sqrt(days / 252.0)) if has_iv else None
        evt_in = (earn_days_ahead is not None and 0 <= earn_days_ahead <= days * 1.45)
        if sigQ is not None and sigP is not None:
            var_house = w * sigQ * sigQ + (1 - w) * sigP * sigP
            sig_house = math.sqrt(max(var_house, 0.0))
            excess = max(0.0, sigQ * sigQ - sigP * sigP)
            event_share = (excess / (sigQ * sigQ)) if sigQ > 0 else 0.0
            iam = sigQ * math.sqrt(2.0 / math.pi)
            seq = sigQ
        else:
            sig_house = sigP; event_share = None; iam = None; seq = None
        out_h[label] = {
            "sigP": round(sigP, 6) if sigP is not None else None,
            "sigQ": round(sigQ, 6) if sigQ is not None else None,
            "sigHouse": round(sig_house, 6) if sig_house is not None else None,
            "eventShare": round(event_share, 4) if event_share is not None else None,
            "impliedAbsMove": round(iam, 6) if iam is not None else None,
            "sigmaEquiv": round(seq, 6) if seq is not None else None,
            "evtIn": bool(evt_in),
        }
    return {"ivAnnual": round(iv_annual, 4) if has_iv else None, "ivDays": iv_days,
            "omegaQ": w, "modellable": bool(has_iv), "horizons": out_h}


# ============================================================================
# Phase 6 — Governance: ES (FRTB), challenger scorecard + release gate (SR 11-7),
#           scan-risk ladder (SPAN), SIMM-style decomposition, provenance.
# ============================================================================
def expected_shortfall(returns: Sequence[float], n_steps: int, alpha: float = 0.025) -> Optional[Dict]:
    """Expected Shortfall (Basel FRTB measure) of n-step returns at the (1-alpha) level:
    VaR = alpha-quantile of the loss distribution, ES = mean of the worst alpha tail."""
    r = [v for v in returns if v == v]
    n = max(1, int(n_steps))
    ys = sorted(sum(r[i:i + n]) for i in range(0, len(r) - n + 1))
    if len(ys) < 20:
        return None
    k = max(1, int(math.floor(alpha * len(ys))))
    return {"var": round(ys[k - 1], 6), "es": round(sum(ys[:k]) / k, 6), "alpha": alpha, "n": len(ys)}


def stressed_es(returns: Sequence[float], n_steps: int, alpha: float = 0.025, win: int = 52) -> Optional[Dict]:
    """Stressed ES: ES computed over the highest-variance trailing window (FRTB stress period)."""
    r = [v for v in returns if v == v]
    if len(r) < win + 10:
        return expected_shortfall(r, n_steps, alpha)
    best, bestsd = None, -1.0
    for i in range(0, len(r) - win + 1):
        w = r[i:i + win]; sd = _var(w)
        if sd > bestsd:
            bestsd, best = sd, w
    return expected_shortfall(best, n_steps, alpha)


def challenger_scorecard(returns: Sequence[float], n_steps: int, iv_annual: Optional[float] = None,
                         window: int = 26, alpha: float = 0.10, step_days: float = 5.0) -> Optional[Dict]:
    """Walk-forward CRPS for the model vs naive challengers — random-walk (zero drift, full-sample
    sigma), EWMA(0.94), and the options-implied Q-Gaussian — plus model coverage and a release-gate
    verdict (SR 11-7 outcomes analysis / benchmarking)."""
    r = [v for v in returns if v == v]
    T = len(r); n = max(1, int(n_steps))
    if T < window + n + 10:
        return None
    lam = 0.94
    ew = [None] * T
    if T > window:
        v = _var(r[:window])
        for t in range(window, T):
            v = lam * v + (1 - lam) * r[t - 1] * r[t - 1]; ew[t] = v
    z = 1.6448536269514722
    sq_step = (iv_annual * math.sqrt(step_days / 252.0)) if iv_annual else None
    # GARCH(1,1) challenger: fit params once (benchmark), then a CAUSAL conditional-variance path
    # so the n-step forecast at i uses only info <= i (no lookahead in the scoring).
    g = garch11_fit(r)
    hpath = None
    if g:
        ga, gb, gom, guv = g["alpha"], g["beta"], g["omega"], g["uncondVar"]
        hpath = [guv] * T; hh = guv
        for t in range(1, T):
            hh = gom + ga * r[t - 1] * r[t - 1] + gb * hh; hpath[t] = hh
    crps = {"model": [], "rw": [], "hv": [], "ewma": []}
    if hpath is not None:
        crps["garch"] = []
    if sq_step:
        crps["q"] = []
    covs = []
    for i in range(window, T - n + 1):
        win = r[i - window:i]; mu = _mean(win); sdw = math.sqrt(max(_var(win), 1e-12))
        y = sum(r[i:i + n]); rt = math.sqrt(n)
        crps["model"].append(crps_gaussian(y, n * mu, sdw * rt))
        full = r[:i]; sdf = math.sqrt(max(_var(full), 1e-12)) if len(full) > 2 else sdw
        crps["rw"].append(crps_gaussian(y, 0.0, sdf * rt))
        crps["hv"].append(crps_gaussian(y, 0.0, sdw * rt))   # empirical HV: zero-drift, trailing-window sigma
        sde = math.sqrt(max(ew[i] if ew[i] is not None else _var(win), 1e-12))
        crps["ewma"].append(crps_gaussian(y, n * mu, sde * rt))
        if hpath is not None:
            tot = sum(guv + ((ga + gb) ** kk) * (hpath[i] - guv) for kk in range(n))
            crps["garch"].append(crps_gaussian(y, n * mu, math.sqrt(max(tot, 1e-14))))
        if sq_step:
            crps["q"].append(crps_gaussian(y, n * mu, sq_step * rt))
        lo = n * mu - z * sdw * rt; hi = n * mu + z * sdw * rt
        covs.append(1 if lo <= y <= hi else 0)
    means = {kk: round(_mean(vv), 6) for kk, vv in crps.items()}
    winner = min(means, key=means.get)
    m = len(covs); kc = sum(covs); cov = kc / m
    wlo, whi = wilson_interval(kc, m)
    calibrated = bool(wlo <= (1 - alpha) <= whi)
    beats_rw = means["model"] <= means["rw"]
    if beats_rw and calibrated:
        gate, reason = "deployable", "beats random-walk on CRPS and calibrated"
    elif beats_rw:
        gate, reason = "research-only", "beats random-walk but miscalibrated"
    else:
        gate, reason = "research-only", "no CRPS edge over a driftless random walk"
    return {"crps": means, "winner": winner, "coverage": round(cov, 3),
            "wilsonLo": round(wlo, 3), "wilsonHi": round(whi, 3), "calibrated": calibrated,
            "beatsRW": beats_rw, "gate": gate, "reason": reason, "n": m}


def scan_risk(sigma_h: Optional[float], price_grid=(-3, -2, -1, 0, 1, 2, 3),
              vol_scn=(0.7, 1.0, 1.3)) -> Optional[Dict]:
    """CME SPAN-style scan: P&L (return) over a price-move x vol-scenario grid; scan risk = the
    worst-case loss across the array."""
    if not sigma_h or sigma_h <= 0:
        return None
    cells, worst = [], 0.0
    for vs in vol_scn:
        row = []
        for k in price_grid:
            ret = k * sigma_h * vs
            row.append(round(ret, 4)); worst = min(worst, ret)
        cells.append(row)
    return {"priceGrid": list(price_grid), "volScn": list(vol_scn), "cells": cells, "scanRisk": round(worst, 4)}


def simm_decomp(deps_top: Optional[Sequence[Dict]], sigP: Optional[float], sigQ: Optional[float]) -> Dict:
    """ISDA SIMM-style risk-class decomposition. Delta = the dominant learned factor sensitivity
    (genuine, from deps); Vega = sigma_Q - sigma_P (implied-vs-realized vol gap, genuine); Curvature
    is left None (honestly) — it needs option gamma we do not carry."""
    delta = None
    if deps_top:
        d0 = deps_top[0]
        delta = {"factor": d0.get("f"), "sensPctPerSigma": d0.get("sens")}
    vega = round(sigQ - sigP, 6) if (sigQ is not None and sigP is not None) else None
    return {"delta": delta, "vega": vega, "vegaNote": "sigma_Q - sigma_P (implied-realized vol gap)",
            "curvature": None, "curvatureNote": "needs option gamma (not carried)"}


_GOV_DAYS = {h[0]: h[1] for h in HORIZONS}


def governance_block(returns: Sequence[float], lin: Dict, iv_annual: Optional[float] = None,
                     gov_horizon: str = "20d", step_days: float = 5.0) -> Dict:
    """Assemble the per-name governance object (FRTB ES + stressed ES, SR 11-7 challenger gate,
    SPAN scan-risk). SIMM is added by the caller (needs deps + pq)."""
    n = max(1, round(_GOV_DAYS.get(gov_horizon, 20) / step_days))
    es = expected_shortfall(returns, n)
    ses = stressed_es(returns, n)
    ch = challenger_scorecard(returns, n, iv_annual, step_days=step_days)
    hzv = (lin.get("horizons") or {}).get(gov_horizon, {})
    sr = scan_risk(hzv.get("totVol"))
    gate = ch["gate"] if ch else "blocked"
    gate_reason = ch["reason"] if ch else "insufficient history for outcomes analysis"
    return {"horizon": gov_horizon, "es975": es, "stressedES": ses, "challenger": ch,
            "scanRisk": sr, "releaseGate": gate, "gateReason": gate_reason}


# ============================================================================
# Second/Third Build — causal macro-support (DML) + EVT/t-copula tail layer
# ============================================================================
def _corr(a, b):
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    a, b = a[:n], b[:n]
    ma, mb = _mean(a), _mean(b)
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = math.sqrt(sum((x - ma) ** 2 for x in a)); db = math.sqrt(sum((x - mb) ** 2 for x in b))
    return num / (da * db) if da > 0 and db > 0 else 0.0


def _ols_resid(y, cols):
    """Residuals of y regressed on [1] + cols (normal equations, small K). cols: list of series."""
    n = len(y)
    X = [[1.0] + [cols[j][i] for j in range(len(cols))] for i in range(n)]
    k = len(X[0])
    # XtX and Xty
    XtX = [[sum(X[i][a] * X[i][b] for i in range(n)) for b in range(k)] for a in range(k)]
    Xty = [sum(X[i][a] * y[i] for i in range(n)) for a in range(k)]
    # Gaussian elimination with partial pivot + ridge for stability
    for d in range(k):
        XtX[d][d] += 1e-8
    A = [row[:] + [Xty[r]] for r, row in enumerate(XtX)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(A[r][c]))
        if abs(A[p][c]) < 1e-12:
            continue
        A[c], A[p] = A[p], A[c]
        piv = A[c][c]
        A[c] = [v / piv for v in A[c]]
        for r in range(k):
            if r != c and abs(A[r][c]) > 0:
                f = A[r][c]; A[r] = [A[r][j] - f * A[c][j] for j in range(k + 1)]
    beta = [A[r][k] for r in range(k)]
    resid = [y[i] - sum(beta[a] * X[i][a] for a in range(k)) for i in range(n)]
    return resid


def _slope(y, x):
    n = min(len(y), len(x)); y, x = y[:n], x[:n]
    mx = _mean(x); sx = sum((v - mx) ** 2 for v in x)
    if sx <= 0:
        return 0.0, 0.0
    my = _mean(y)
    b = sum((x[i] - mx) * (y[i] - my) for i in range(n)) / sx
    resid = [y[i] - (my + b * (x[i] - mx)) for i in range(n)]
    s2 = sum(r * r for r in resid) / max(1, n - 2)
    se = math.sqrt(s2 / sx)
    return b, se


def causal_support(y, factors, min_n=30):
    """Per-factor causal-support label via partial regression (DML with linear nuisance = FWL,
    appropriate for a small macro-factor set). Three honest labels:
      merely-correlative — marginal correlation present, but the partialled-out effect CI straddles 0
                           (explained away by the other factors);
      predictive         — the factor LEADS forward returns (lag-1) even if not contemporaneously causal;
      plausibly-causal   — partialled-out effect is significant AND sign-stable across halves.
    Returns ranked list {f, marginal, partial, ciLo, ciHi, predLag, stable, label}."""
    labels = list(factors.keys())
    n = len(y)
    if n < min_n or len(labels) < 2:
        return []
    out = []
    for lab in labels:
        Tj = factors[lab]
        others = [factors[l] for l in labels if l != lab and factors[l]]
        marg = _corr(y, Tj)
        ry = _ols_resid(y, others); rt = _ols_resid(Tj, others)
        theta, se = _slope(ry, rt)
        lo, hi = theta - 1.96 * se, theta + 1.96 * se
        sig = (lo > 0 or hi < 0)
        h = n // 2
        oth_a = [o[:h] for o in others]; oth_b = [o[h:] for o in others]
        t1, _ = _slope(_ols_resid(y[:h], oth_a), _ols_resid(Tj[:h], oth_a))
        t2, _ = _slope(_ols_resid(y[h:], oth_b), _ols_resid(Tj[h:], oth_b))
        stable = (t1 * t2 > 0) and sig
        predlag = _corr(y[1:], Tj[:-1]) if n > 4 else 0.0
        thr = 1.96 / math.sqrt(n)
        if stable:
            label = "plausibly-causal"
        elif abs(predlag) > thr:
            label = "predictive"
        elif abs(marg) > thr:
            label = "merely-correlative"
        else:
            label = "weak"
        out.append({"f": lab, "marginal": round(marg, 3), "partial": round(theta, 4),
                    "ciLo": round(lo, 4), "ciHi": round(hi, 4), "predLag": round(predlag, 3),
                    "stable": bool(stable), "label": label})
    out.sort(key=lambda d: -abs(d["partial"]))
    return out


def evt_gpd_tail(returns, q=0.10):
    """Peaks-over-threshold EVT (Pickands-Balkema-de Haan): fit a GPD to the lower-tail exceedances,
    return tail index xi, threshold u, exceedance count, GPD-based ES, and the EVT add-on (GPD-ES
    minus empirical-ES). Method-of-moments GPD."""
    r = sorted(v for v in returns if v == v)
    n = len(r)
    if n < 50:
        return None
    ui = max(1, int(math.floor(q * n)))
    u = r[ui - 1]                       # lower-tail threshold (a loss, negative)
    exc = [u - r[i] for i in range(ui)]  # positive exceedance magnitudes below u
    Nu = len(exc)
    if Nu < 10:
        return None
    m = _mean(exc); v = _var(exc)
    if v <= 0:
        return None
    xi = 0.5 * (1.0 - m * m / v)         # GPD MoM shape
    sigma = m * (1.0 - xi)               # GPD MoM scale
    sigma = max(sigma, 1e-9)
    p = 0.025                            # 97.5% tail
    # POT VaR/ES on the loss side (losses = -returns); u_loss = -u
    u_loss = -u
    try:
        var_p = u_loss + (sigma / xi) * (((n / Nu) * (p)) ** (-xi) - 1) if abs(xi) > 1e-6 \
                else u_loss + sigma * math.log((Nu / n) / p)
        es_p = (var_p + sigma - xi * u_loss) / (1 - xi) if xi < 1 else var_p
    except Exception:
        return None
    emp = expected_shortfall(returns, 1, alpha=p)
    emp_es = -emp["es"] if emp else var_p
    return {"xi": round(xi, 4), "threshold": round(u, 6), "exceedances": Nu,
            "gpdES": round(-es_p, 6), "evtAddOn": round(-(es_p - emp_es), 6),
            "copula": "t", "note": "POT/GPD lower-tail; t-copula recommended over Gaussian"}


def tail_dependence(a, b, q=0.10):
    """Empirical lower/upper tail-dependence coefficients between two return series (a=name, b=market):
    lambda_L = P(b in lower q | a in lower q), lambda_U = P(b in upper q | a in upper q)."""
    nA = min(len(a), len(b))
    if nA < 50:
        return None
    a, b = a[:nA], b[:nA]
    sa = sorted(a); sb = sorted(b)
    k = max(1, int(math.floor(q * nA)))
    aL, aU = sa[k - 1], sa[nA - k]
    bL, bU = sb[k - 1], sb[nA - k]
    inAL = [i for i in range(nA) if a[i] <= aL]
    inAU = [i for i in range(nA) if a[i] >= aU]
    lamL = (sum(1 for i in inAL if b[i] <= bL) / len(inAL)) if inAL else 0.0
    lamU = (sum(1 for i in inAU if b[i] >= bU) / len(inAU)) if inAU else 0.0
    return {"lambdaLower": round(lamL, 3), "lambdaUpper": round(lamU, 3), "q": q,
            "gaussianRef": round(q, 3)}   # independent baseline ~ q


# ============================================================================
# Second Build spine — factor covariance (BFB'+D), Black-Litterman + entropy
#                      pooling, alert score.
# ============================================================================
def _ols_coef(y, cols):
    """Coefficients [intercept, b1..bk] of y on [1]+cols (ridge-stabilized normal equations)."""
    n = len(y)
    X = [[1.0] + [cols[j][i] for j in range(len(cols))] for i in range(n)]
    k = len(X[0])
    XtX = [[sum(X[i][a] * X[i][b] for i in range(n)) for b in range(k)] for a in range(k)]
    Xty = [sum(X[i][a] * y[i] for i in range(n)) for a in range(k)]
    for d in range(k):
        XtX[d][d] += 1e-8
    A = [XtX[r][:] + [Xty[r]] for r in range(k)]
    for c in range(k):
        pv = max(range(c, k), key=lambda r: abs(A[r][c]))
        if abs(A[pv][c]) < 1e-12:
            continue
        A[c], A[pv] = A[pv], A[c]
        piv = A[c][c]; A[c] = [v / piv for v in A[c]]
        for r in range(k):
            if r != c and abs(A[r][c]) > 0:
                f = A[r][c]; A[r] = [A[r][j] - f * A[c][j] for j in range(k + 1)]
    return [A[r][k] for r in range(k)]


def factor_covariance(factors, lam=0.94):
    """EWMA factor covariance matrix Sigma_f (RiskMetrics lambda). factors: dict {label: series}."""
    labs = [l for l in factors if factors[l]]
    if len(labs) < 2:
        return None
    n = min(len(factors[l]) for l in labs)
    series = {l: factors[l][-n:] for l in labs}
    K = len(labs)
    cov = [[0.0] * K for _ in range(K)]
    for i in range(K):
        for j in range(i, K):
            a = series[labs[i]]; b = series[labs[j]]
            ma = _mean(a); mb = _mean(b)
            c = (a[0] - ma) * (b[0] - mb)
            for t in range(1, n):
                c = lam * c + (1 - lam) * (a[t] - ma) * (b[t] - mb)
            cov[i][j] = cov[j][i] = c
    ver = "fcov-" + str(abs(hash(tuple(labs))) % 100000)
    return {"factors": labs, "cov": [[round(v, 8) for v in row] for row in cov],
            "lam": lam, "version": ver, "n": n}


def factor_decomp(y, factors, factor_cov):
    """Multi-factor risk decomposition Sigma = b' Sigma_f b + d  (Barra/Axioma style).
    Returns exposures b, specific variance d, factor variance, total, explained fraction."""
    labs = (factor_cov or {}).get("factors") or [l for l in factors if factors[l]]
    cols = [factors[l] for l in labs if factors.get(l)]
    labs = [l for l in labs if factors.get(l)]
    if len(labs) < 2 or len(y) < 3 * len(labs):
        return None
    coef = _ols_coef(y, cols)
    b = coef[1:]
    resid = [y[i] - (coef[0] + sum(b[j] * cols[j][i] for j in range(len(b)))) for i in range(len(y))]
    d = _var(resid)
    cov = factor_cov["cov"] if factor_cov else None
    if cov:
        # align b to factor_cov ordering
        idx = {l: i for i, l in enumerate(factor_cov["factors"])}
        bb = [0.0] * len(factor_cov["factors"])
        for j, l in enumerate(labs):
            if l in idx:
                bb[idx[l]] = b[j]
        fv = sum(bb[i] * cov[i][k] * bb[k] for i in range(len(bb)) for k in range(len(bb)))
    else:
        fv = sum(b[j] ** 2 * _var(cols[j]) for j in range(len(b)))
    fv = max(0.0, fv); tot = fv + d
    return {"exposures": {labs[j]: round(b[j], 4) for j in range(len(b))},
            "specificVar": round(d, 8), "factorVar": round(fv, 8), "totalVar": round(tot, 8),
            "explainedPct": round(100.0 * fv / tot, 1) if tot > 0 else 0.0,
            "factorCovVersion": (factor_cov or {}).get("version")}


def black_litterman(prior_mu, prior_var, views):
    """Scalar Black-Litterman: precision-weighted blend of an equilibrium/historical prior with one
    or more views. views = [{q: view return, omega: view variance}]. Returns posterior mu/var and
    the prior so the UI can show both (the spec requires storing prior AND posterior)."""
    prior_var = max(prior_var, 1e-12)
    prec = 1.0 / prior_var
    num = prior_mu / prior_var
    for v in views or []:
        om = max(v.get("omega", 1e9), 1e-12); prec += 1.0 / om; num += v.get("q", 0.0) / om
    post_var = 1.0 / prec
    return {"priorMu": round(prior_mu, 6), "postMu": round(num * post_var, 6),
            "priorVar": round(prior_var, 8), "postVar": round(post_var, 8),
            "nViews": len(views or [])}


def entropy_pool(probs, x, target, iters=60):
    """Meucci entropy pooling (single linear view): reweight scenario probs to satisfy E_q[x]=target
    with minimal relative entropy -> exponential tilt q_i ∝ p_i exp(theta x_i). Newton on theta.
    Returns {q, theta, kl, achieved}."""
    n = len(probs)
    if n < 2 or len(x) != n:
        return None
    p = list(probs); s = sum(p) or 1.0; p = [v / s for v in p]
    lo, hi = min(x), max(x)
    if not (lo <= target <= hi):
        target = min(hi, max(lo, target))
    theta = 0.0
    for _ in range(iters):
        w = [p[i] * math.exp(theta * x[i]) for i in range(n)]
        z = sum(w) or 1e-12
        q = [v / z for v in w]
        m = sum(q[i] * x[i] for i in range(n))
        var = sum(q[i] * (x[i] - m) ** 2 for i in range(n))
        if var < 1e-15:
            break
        step = (m - target) / var
        theta -= step
        if abs(step) < 1e-10:
            break
    w = [p[i] * math.exp(theta * x[i]) for i in range(n)]
    z = sum(w) or 1e-12
    q = [v / z for v in w]
    kl = sum(q[i] * math.log(q[i] / p[i]) for i in range(n) if q[i] > 0 and p[i] > 0)
    return {"q": [round(v, 4) for v in q], "theta": round(theta, 4), "kl": round(kl, 5),
            "achieved": round(sum(q[i] * x[i] for i in range(n)), 6)}


def alert_score(p_max, edge, es99, vfwd, adv, M, G, c=0.01):
    """Spec alert score A = p_max * |mu_post - mu_prior|/(ES99 + c) * (V_fwd/ADV) * M * G.
    Rewards view-driven edge, penalizes tail risk, boosts liquidity, gates on modellability/governance."""
    es = abs(es99) if es99 else 0.0
    liq = (vfwd / adv) if (adv and adv > 0 and vfwd) else 1.0
    liq = max(0.1, min(3.0, liq))
    A = max(0.0, p_max) * (abs(edge) / (es + c)) * liq * (1.0 if M else 0.0) * max(0.0, min(1.0, G))
    return round(A, 4)


# ============================================================================
# Second/Third Build remainder — pricers, Kalman, MV-Hawkes + impact, resampling
#   tests (stationary bootstrap / Reality Check / SPA / Romano-Wolf), SIMM bucket,
#   FRTB SBA + PLA, STANS ES, scenario cube, entropy-pool regime reweighting.
# ============================================================================
def bs_call(S, K, T, r, sigma):
    """Black-Scholes European call."""
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)


def _heston_cf(u, S, T, r, v0, kappa, theta, xi, rho, j):
    """Heston characteristic function (little-trap form), j in {1,2}."""
    i = complex(0, 1)
    b = kappa - rho * xi if j == 1 else kappa
    u_ = u - i if j == 1 else u
    a = kappa * theta
    d = ((rho * xi * i * u - b) ** 2 - xi * xi * (2 * (0.5 * i * u * (1 if j == 1 else -1) - 0.5 * u * u))) ** 0.5
    # use standard: d = sqrt((rho xi i u - b)^2 + xi^2 (i u + u^2)) with j-sign on drift term
    uj = 0.5 if j == 1 else -0.5
    d = ((b - rho * xi * i * u) ** 2 - xi * xi * (2 * uj * i * u - u * u)) ** 0.5
    g = (b - rho * xi * i * u - d) / (b - rho * xi * i * u + d)
    eDT = (math.e ** (0))  # placeholder
    exp_dT = (2.718281828459045 ** (0))
    C = r * i * u * T + (a / (xi * xi)) * ((b - rho * xi * i * u - d) * T - 2 * (((1 - g * (2.718281828459045 ** (-d * T))) / (1 - g)).__abs__() and 0) )
    # robust closed form
    import cmath
    d = cmath.sqrt((b - rho * xi * i * u) ** 2 - xi * xi * (2 * uj * i * u - u * u))
    g = (b - rho * xi * i * u - d) / (b - rho * xi * i * u + d)
    edt = cmath.exp(-d * T)
    C = r * i * u * T + (a / (xi * xi)) * ((b - rho * xi * i * u - d) * T - 2 * cmath.log((1 - g * edt) / (1 - g)))
    D = ((b - rho * xi * i * u - d) / (xi * xi)) * ((1 - edt) / (1 - g * edt))
    return cmath.exp(C + D * v0 + i * u * math.log(S))


def heston_call(S, K, T, r, v0, kappa, theta, xi, rho, umax=100.0, n=200):
    """Heston European call via Gil-Pelaez / trapezoidal integration of the two probabilities."""
    import cmath
    i = complex(0, 1)
    def Pj(j):
        s = 0.0; du = umax / n
        for m in range(1, n + 1):
            u = (m - 0.5) * du
            cf = _heston_cf(u, S, T, r, v0, kappa, theta, xi, rho, j)
            s += (cmath.exp(-i * u * math.log(K)) * cf / (i * u)).real * du
        return 0.5 + s / math.pi
    P1 = Pj(1); P2 = Pj(2)
    return max(0.0, S * P1 - K * math.exp(-r * T) * P2)


def merton_call(S, K, T, r, sigma, lam, muJ, sigJ, nmax=40):
    """Merton jump-diffusion European call: Poisson-weighted sum of BS prices."""
    kappa = math.exp(muJ + 0.5 * sigJ * sigJ) - 1
    lam_ = lam * (1 + kappa)
    price = 0.0
    for nn in range(nmax):
        pois = math.exp(-lam_ * T) * (lam_ * T) ** nn / math.factorial(nn)
        sig_n = math.sqrt(sigma * sigma + nn * sigJ * sigJ / T)
        r_n = r - lam * kappa + nn * (muJ + 0.5 * sigJ * sigJ) / T
        price += pois * bs_call(S, K, T, r_n, sig_n)
        if pois < 1e-12 and nn > lam_ * T + 5:
            break
    return price


def kalman_local_level(y, q=1e-4, r=1e-3):
    """Local-level Kalman filter (latent fair value / drift): x_t = x_{t-1}+w(q), y_t = x_t+v(r).
    Returns the filtered latent state series."""
    if not y:
        return []
    x = y[0]; P = 1.0; out = []
    for obs in y:
        P = P + q                      # predict
        K = P / (P + r)                # gain
        x = x + K * (obs - x)          # update
        P = (1 - K) * P
        out.append(x)
    return out


def hawkes_mv_intensity(mu, alpha, beta, events, now):
    """Multivariate Hawkes intensity vector at `now`. mu: [K], alpha: [K][K] (excitation of i by j),
    beta: decay, events: [(channel, t)]. lambda_i = mu_i + sum_k alpha[i][ch_k] exp(-beta (now-t_k))."""
    K = len(mu)
    lam = list(mu)
    for (ch, t) in events:
        if t <= now:
            decay = math.exp(-beta * (now - t))
            for i in range(K):
                lam[i] += alpha[i][ch] * decay
    return lam


def sqrt_impact(sigma_daily, participation, y=1.0):
    """Square-root market-impact law for metaorders: impact = y * sigma_daily * sqrt(Q/ADV)."""
    return y * sigma_daily * math.sqrt(max(participation, 0.0))


def stationary_bootstrap_indices(n, p=0.1, seed=0):
    """Politis-Romano stationary bootstrap: geometric-length blocks (mean 1/p)."""
    rng = random.Random(seed)
    idx = []
    i = rng.randrange(n)
    for _ in range(n):
        idx.append(i)
        if rng.random() < p:
            i = rng.randrange(n)
        else:
            i = (i + 1) % n
    return idx


def reality_check(f, B=500, p=0.1, seed=1):
    """White's Reality Check. f: list of per-model performance differentials (model better = positive),
    each a series of length n. Returns RC p-value for H0: no model beats the benchmark."""
    M = len(f); n = len(f[0]) if M else 0
    if M == 0 or n < 20:
        return None
    means = [_mean(fk) for fk in f]
    V = max(math.sqrt(n) * mk for mk in means)
    rng = random.Random(seed); cnt = 0
    for b in range(B):
        ix = stationary_bootstrap_indices(n, p, seed=seed + b)
        vb = max(math.sqrt(n) * (_mean([f[k][j] for j in ix]) - means[k]) for k in range(M))
        if vb >= V:
            cnt += 1
    return round(cnt / B, 4)


def spa_test(f, B=500, p=0.1, seed=2):
    """Hansen's SPA (studentized). Returns SPA p-value (consistent recentering)."""
    M = len(f); n = len(f[0]) if M else 0
    if M == 0 or n < 20:
        return None
    means = [_mean(fk) for fk in f]
    sds = [math.sqrt(max(_var(fk), 1e-12)) for fk in f]
    T = max(0.0, max(math.sqrt(n) * means[k] / sds[k] for k in range(M)))
    thr = [-sds[k] * math.sqrt(2 * math.log(math.log(n))) / math.sqrt(n) for k in range(M)]
    rng = random.Random(seed); cnt = 0
    for b in range(B):
        ix = stationary_bootstrap_indices(n, p, seed=seed + b)
        tb = 0.0
        for k in range(M):
            mk = _mean([f[k][j] for j in ix])
            center = means[k] if means[k] >= thr[k] else 0.0
            tb = max(tb, math.sqrt(n) * (mk - center) / sds[k])
        if tb >= T:
            cnt += 1
    return round(cnt / B, 4)


def romano_wolf(f, B=500, p=0.1, alpha=0.05, seed=3):
    """Romano-Wolf stepdown FWER control. Returns per-model {tstat, rejected}."""
    M = len(f); n = len(f[0]) if M else 0
    if M == 0 or n < 20:
        return None
    means = [_mean(fk) for fk in f]; sds = [math.sqrt(max(_var(fk), 1e-12)) for fk in f]
    t = [math.sqrt(n) * means[k] / sds[k] for k in range(M)]
    order = sorted(range(M), key=lambda k: -t[k])
    rejected = set(); active = list(order)
    while active:
        boot_max = []
        for b in range(B):
            ix = stationary_bootstrap_indices(n, p, seed=seed + b)
            mx = max(math.sqrt(n) * (_mean([f[k][j] for j in ix]) - means[k]) / sds[k] for k in active)
            boot_max.append(mx)
        boot_max.sort()
        crit = boot_max[min(len(boot_max) - 1, int(math.ceil((1 - alpha) * len(boot_max))) - 1)]
        newly = [k for k in active if t[k] > crit]
        if not newly:
            break
        for k in newly:
            rejected.add(k)
        active = [k for k in active if k not in rejected]
    return [{"model": k, "tstat": round(t[k], 3), "rejected": k in rejected} for k in range(M)]


def simm_bucket(ws, corr):
    """SIMM/FRTB sensitivity bucket aggregation K_b = sqrt(sum_i sum_j corr_ij WS_i WS_j).
    ws: weighted sensitivities list; corr: scalar off-diagonal correlation."""
    n = len(ws)
    if n == 0:
        return 0.0
    s = sum(ws[i] * ws[j] * (1.0 if i == j else corr) for i in range(n) for j in range(n))
    return round(math.sqrt(max(0.0, s)), 6)


def frtb_sba(delta_ws, vega_ws, curv, corr_scenarios=(0.35, 0.6, 0.85)):
    """FRTB standardized sensitivities-based capital under low/med/high correlation scenarios:
    K = sqrt(Kdelta^2 + Kvega^2 + curvature^2)."""
    out = {}
    for nm, rho in zip(("low", "med", "high"), corr_scenarios):
        kd = simm_bucket(delta_ws, rho); kv = simm_bucket(vega_ws, rho)
        out[nm] = round(math.sqrt(kd * kd + kv * kv + (curv or 0.0) ** 2), 6)
    return out


def pla_test(pnl_risk, pnl_full):
    """FRTB P&L Attribution: agreement between risk-model P&L and full-reval P&L. Spearman corr +
    a normalized mean-abs gap -> traffic light (green/amber/red)."""
    n = min(len(pnl_risk), len(pnl_full))
    if n < 20:
        return None
    def _rank(a):
        order = sorted(range(len(a)), key=lambda i: a[i]); rk = [0] * len(a)
        for r, i in enumerate(order):
            rk[i] = r
        return rk
    ra, rb = _rank(pnl_risk[:n]), _rank(pnl_full[:n])
    sp = _corr([float(x) for x in ra], [float(x) for x in rb])
    sd = math.sqrt(max(_var(pnl_full[:n]), 1e-12))
    gap = sum(abs(pnl_risk[i] - pnl_full[i]) for i in range(n)) / n / sd
    zone = "green" if (sp >= 0.8 and gap <= 0.5) else ("amber" if (sp >= 0.7 and gap <= 0.9) else "red")
    return {"spearman": round(sp, 3), "gap": round(gap, 3), "zone": zone}


def stans_es(returns, alpha=0.01, stress_mult=1.5, two_day=True):
    """OCC STANS-style base ES: 99% ES (2-day horizon) with EVT conservatism + a stress add-on."""
    n2 = 2 if two_day else 1
    base = expected_shortfall(returns, n2, alpha)
    if not base:
        return None
    ev = evt_gpd_tail(returns, q=0.05)
    es = base["es"]
    if ev and ev.get("gpdES") is not None:
        es = min(es, ev["gpdES"])         # EVT conservatism (more severe)
    return {"es99_2d": round(es, 6), "stressedES": round(es * stress_mult, 6),
            "evtFloor": (ev.get("gpdES") if ev else None), "alpha": alpha}


def scenario_cube(sigma_by_horizon, spot_grid=(-3, -2, -1, 0, 1, 2, 3), vol_scns=(0.7, 1.0, 1.3)):
    """SPAN-style scenario cube: returns[horizon][volScenario][spotShock] = k*sigma_h*volScn.
    Plus a flat downloadable risk-array parameter object and per-horizon worst-case scan risk."""
    cube = {}; params = []; worst = {}
    for h, sig in (sigma_by_horizon or {}).items():
        if not sig:
            continue
        rows = []
        w = 0.0
        for vs in vol_scns:
            row = []
            for k in spot_grid:
                ret = round(k * sig * vs, 5); row.append(ret); w = min(w, ret)
                params.append({"horizon": h, "volScn": vs, "spotSigma": k, "pnl": ret})
            rows.append(row)
        cube[h] = rows; worst[h] = round(w, 5)
    return {"spotGrid": list(spot_grid), "volScn": list(vol_scns), "cube": cube,
            "scanRisk": worst, "riskArray": params}


def entropy_pool_regimes(post, branch_drifts, target_mu):
    """Apply Meucci entropy pooling: reweight the regime posterior so the mixture mean equals the
    BL posterior target, with minimal relative entropy. Returns the reweighted regime weights."""
    if not post or len(post) != len(branch_drifts):
        return None
    ep = entropy_pool(post, branch_drifts, target_mu)
    return ep["q"] if ep else None
