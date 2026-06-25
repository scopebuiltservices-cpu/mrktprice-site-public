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
import math
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


def lineage_object(returns: Sequence[float], horizons=PRIMARY_HORIZONS,
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
        }
    return {
        "K": K, "regimeNow": regime_now,
        "post": [round(p, 4) for p in post],
        "trans": [[round(v, 4) for v in row] for row in trans],
        "means": [round(m, 6) for m in means],
        "vols": [round(math.sqrt(max(v, 0)), 6) for v in vars],
        "branches": [{"regime": b["regime"], "p": round(b["p"], 4)} for b in branches],
        "horizons": hz,
        "stepDays": step_days_per_unit,
    }
