"""lineage_scoring.py — scoring / GARCH / quantile primitives + norm constants, extracted from
lineage.py to hold it under the file-line budget. Pure leaf math (no back-reference into lineage).
Re-exported by lineage.py so existing `from lineage import <name>` paths keep working."""
import math
from typing import Sequence, Tuple, Optional, Dict, List

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
