"""regime_ic.py — 2-state Gaussian HMM regime labeler + regime-conditional IC. Lets the board read a
state-conditioned information coefficient: mu_{i,t} = IC(state_t, factor) * sigma_{i,t} * z_{i,t}, so the
same signal is up-weighted in the regime where it has historically worked and down-weighted where it hasn't.
Pure stdlib (Baum-Welch EM + Viterbi); verified against planted regime-switching structure. Research only."""
import math

__all__ = ["gaussian_hmm_2state", "viterbi_path", "regime_ic", "state_conditioned_mu"]


def _npdf(x, mu, var):
    var = max(var, 1e-12)
    return math.exp(-0.5 * (x - mu) ** 2 / var) / math.sqrt(2.0 * math.pi * var)


def gaussian_hmm_2state(x, iters=60):
    """Fit a 2-state Gaussian HMM by Baum-Welch. Returns {mu:[2], var:[2], trans:[2][2], pi:[2], gamma}.
    States are ordered so state 0 = LOWER variance (calm), state 1 = HIGHER variance (stress)."""
    T = len(x)
    if T < 10:
        m = sum(x) / T if T else 0.0
        return {"mu": [m, m], "var": [1e-6, 1e-6], "trans": [[.5, .5], [.5, .5]], "pi": [.5, .5], "gamma": [[.5, .5]] * T}
    m = sum(x) / T
    v = sum((xi - m) ** 2 for xi in x) / T
    mu = [m - 0.5 * math.sqrt(v), m + 0.5 * math.sqrt(v)]
    var = [v * 0.5, v * 1.5]
    A = [[0.9, 0.1], [0.1, 0.9]]
    pi = [0.5, 0.5]
    for _ in range(iters):
        # forward-backward with scaling
        al = [[0.0, 0.0] for _ in range(T)]
        c = [0.0] * T
        for k in range(2):
            al[0][k] = pi[k] * _npdf(x[0], mu[k], var[k])
        c[0] = sum(al[0]) or 1e-300
        al[0] = [a / c[0] for a in al[0]]
        for t in range(1, T):
            for k in range(2):
                al[t][k] = (al[t - 1][0] * A[0][k] + al[t - 1][1] * A[1][k]) * _npdf(x[t], mu[k], var[k])
            c[t] = sum(al[t]) or 1e-300
            al[t] = [a / c[t] for a in al[t]]
        be = [[0.0, 0.0] for _ in range(T)]
        be[T - 1] = [1.0, 1.0]
        for t in range(T - 2, -1, -1):
            for k in range(2):
                be[t][k] = sum(A[k][j] * _npdf(x[t + 1], mu[j], var[j]) * be[t + 1][j] for j in range(2)) / c[t + 1]
        gamma = [[al[t][k] * be[t][k] for k in range(2)] for t in range(T)]
        for t in range(T):
            s = sum(gamma[t]) or 1e-300
            gamma[t] = [g / s for g in gamma[t]]
        # xi sums
        xis = [[0.0, 0.0], [0.0, 0.0]]
        for t in range(T - 1):
            denom = 0.0
            tmp = [[0.0, 0.0], [0.0, 0.0]]
            for i in range(2):
                for j in range(2):
                    tmp[i][j] = al[t][i] * A[i][j] * _npdf(x[t + 1], mu[j], var[j]) * be[t + 1][j]
                    denom += tmp[i][j]
            denom = denom or 1e-300
            for i in range(2):
                for j in range(2):
                    xis[i][j] += tmp[i][j] / denom
        # M-step
        pi = gamma[0][:]
        for i in range(2):
            gsum = sum(gamma[t][i] for t in range(T - 1)) or 1e-300
            for j in range(2):
                A[i][j] = xis[i][j] / gsum
        for k in range(2):
            gk = sum(gamma[t][k] for t in range(T)) or 1e-300
            mu[k] = sum(gamma[t][k] * x[t] for t in range(T)) / gk
            var[k] = max(sum(gamma[t][k] * (x[t] - mu[k]) ** 2 for t in range(T)) / gk, 1e-12)
    # order: state 0 = lower variance
    if var[0] > var[1]:
        mu = [mu[1], mu[0]]; var = [var[1], var[0]]
        A = [[A[1][1], A[1][0]], [A[0][1], A[0][0]]]; pi = [pi[1], pi[0]]
        gamma = [[g[1], g[0]] for g in gamma]
    return {"mu": mu, "var": var, "trans": A, "pi": pi, "gamma": gamma}


def viterbi_path(x, hmm):
    """Most-likely state sequence given a fitted hmm (states already ordered calm=0/stress=1)."""
    T = len(x)
    mu, var, A, pi = hmm["mu"], hmm["var"], hmm["trans"], hmm["pi"]
    def lp(p): return math.log(max(p, 1e-300))
    d = [[lp(pi[k]) + lp(_npdf(x[0], mu[k], var[k])) for k in range(2)]]
    bk = [[0, 0]]
    for t in range(1, T):
        row = [0.0, 0.0]; b = [0, 0]
        for k in range(2):
            cand = [d[t - 1][j] + lp(A[j][k]) for j in range(2)]
            b[k] = 0 if cand[0] >= cand[1] else 1
            row[k] = cand[b[k]] + lp(_npdf(x[t], mu[k], var[k]))
        d.append(row); bk.append(b)
    last = 0 if d[T - 1][0] >= d[T - 1][1] else 1
    path = [last]
    for t in range(T - 1, 0, -1):
        last = bk[t][last]; path.append(last)
    path.reverse()
    return path


def regime_ic(ic_by_period, regime_path, factors):
    """ic_by_period: list of {factor: ic} per period; regime_path: state per period. Returns
    {state: {factor: mean_ic, '_n': count}}."""
    out = {0: {f: [] for f in factors}, 1: {f: [] for f in factors}}
    cnt = {0: 0, 1: 0}
    for t, rec in enumerate(ic_by_period):
        if t >= len(regime_path):
            break
        s = regime_path[t]; cnt[s] += 1
        for f in factors:
            v = rec.get(f)
            if v is not None:
                out[s][f].append(v)
    res = {}
    for s in (0, 1):
        res[s] = {f: (sum(out[s][f]) / len(out[s][f]) if out[s][f] else 0.0) for f in factors}
        res[s]["_n"] = cnt[s]
    return res


def state_conditioned_mu(state, ic_state, sigma, z, factor):
    return ic_state.get(state, {}).get(factor, 0.0) * sigma * z
