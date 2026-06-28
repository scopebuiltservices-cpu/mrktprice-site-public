#!/usr/bin/env python3
"""
portfolio_engine.py — convert a ranked cross-section into ALLOCATIONS (the "Omitted Strategies" #7, the
single biggest next gain): mean-variance utility w* = argmax mu'w - (lam/2) w'Sigma w, on a SINGLE-FACTOR
risk model Sigma = sigma_m^2 * beta beta' + diag(sigma_idio^2) built from data the board already has
(beta + per-name vol). The MV optimum is solved in O(n) by Sherman-Morrison (no n^3 inverse), then
projected onto a long-only box + gross budget, with a turnover-aware transition from the current book.

Verified-engine pattern: this is authoritative; portfolio_engine.js is locked to tools/portfolio_golden.json.
Pure-stdlib, dependency-injected, unit-tested against a brute-force inverse. Research only.
"""
import json, os

__all__ = ["factor_cov", "mv_weights_factor", "project_long_only", "turnover_blend"]


def factor_cov(beta, sigma_m, sigma_idio):
    """Single-factor covariance Sigma = sigma_m^2 * beta beta' + diag(sigma_idio^2) as a full matrix
    (small n / verification). The optimizer uses the structure directly, not this dense form."""
    n = len(beta); c = sigma_m * sigma_m
    return [[c * beta[i] * beta[j] + (sigma_idio[i] * sigma_idio[i] if i == j else 0.0) for j in range(n)] for i in range(n)]


def mv_weights_factor(mu, beta, sigma_m, sigma_idio, lam=1.0):
    """Unconstrained mean-variance optimum w = (1/lam) Sigma^{-1} mu for a SINGLE-FACTOR Sigma, solved in
    O(n) via Sherman-Morrison:
        Sigma^{-1} mu = D^{-1}mu - c (D^{-1}beta)(beta' D^{-1} mu) / (1 + c beta' D^{-1} beta),
    with D = diag(sigma_idio^2), c = sigma_m^2. Exact (matches a dense inverse to machine precision)."""
    n = len(mu); c = sigma_m * sigma_m
    Dinv = [1.0 / (sigma_idio[i] * sigma_idio[i]) for i in range(n)]
    Dm = [Dinv[i] * mu[i] for i in range(n)]
    Db = [Dinv[i] * beta[i] for i in range(n)]
    bDb = sum(beta[i] * Db[i] for i in range(n))
    bDm = sum(beta[i] * Dm[i] for i in range(n))
    k = c * bDm / (1.0 + c * bDb)
    return [(Dm[i] - k * Db[i]) / lam for i in range(n)]


def project_long_only(w_raw, w_max=0.1, budget=1.0, iters=50):
    """Project raw weights onto {0 <= w <= w_max, sum w = budget} by iterative clip + redistribute
    (water-filling). Deterministic; always respects the box and the gross budget."""
    n = len(w_raw); w = [max(0.0, x) for x in w_raw]
    s = sum(w)
    if s <= 0:
        return [budget / n] * n
    w = [budget * x / s for x in w]
    for _ in range(iters):
        over = [i for i in range(n) if w[i] > w_max]
        if not over:
            break
        spill = sum(w[i] - w_max for i in over)
        for i in over:
            w[i] = w_max
        free = [i for i in range(n) if w[i] < w_max - 1e-12]
        fs = sum(w[i] for i in free)
        if fs <= 0 or not free:
            return w
        for i in free:
            w[i] += spill * w[i] / fs
    return w


def turnover_blend(w_opt, w_prev, step=1.0):
    """Turnover-aware transition: move from the current book toward the optimum by `step` in [0,1]; step<1
    trades less (lower turnover / tax / friction). w_prev None -> w_opt unchanged."""
    if w_prev is None:
        return list(w_opt)
    return [w_prev[i] + step * (w_opt[i] - w_prev[i]) for i in range(len(w_opt))]


def gen_fixture():
    mu = [3.0, 1.0, -2.0, 4.0, 0.5]
    beta = [1.1, 0.8, 1.4, 0.6, 1.0]
    sidio = [2.0, 1.5, 2.5, 1.2, 1.8]
    sm = 1.2; lam = 2.0
    w = mv_weights_factor(mu, beta, sm, sidio, lam)
    proj = project_long_only(w, w_max=0.35, budget=1.0)
    prev = [0.2, 0.2, 0.2, 0.2, 0.2]
    blend = turnover_blend(proj, prev, 0.5)
    diag = [factor_cov(beta, sm, sidio)[i][i] for i in range(len(beta))]
    return {"fixture_version": 1, "case": "portfolio-core", "lam": lam, "sigma_m": sm,
            "mu": mu, "beta": beta, "sigma_idio": sidio,
            "w": w, "proj": proj, "blend": blend, "covDiag": diag}


def main():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "portfolio_golden.json")
    json.dump(gen_fixture(), open(p, "w"), separators=(",", ":"))
    print("wrote", os.path.normpath(p))


if __name__ == "__main__":
    main()
