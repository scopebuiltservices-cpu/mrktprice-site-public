#!/usr/bin/env python3
"""
validation_engine.py — research-overfit promotion gate (the "Omitted Strategies" #2): make overfit control
a MACHINE-READABLE gate, not a research note. Provides:
  purged_kfold(n, k, embargo)  purged + embargoed time-series CV splits (no serial-correlation leakage).
  pbo_cscv(M, S)               Probability of Backtest Overfitting via Combinatorially-Symmetric CV
                               (Bailey, Borwein, Lopez de Prado, Zhu 2017). Pure noise -> ~0.5; real edge -> low.
  promotion_gate(dsr, pbo)     deployable iff DSR >= min_dsr AND PBO <= max_pbo (Deflated Sharpe lives in
                               rank_engine.deflated_sharpe). Returns {deployable, reasons}.

Verified-engine pattern: authoritative; validation_engine.js is locked to tools/validation_golden.json.
Pure-stdlib. Research only.
"""
import json, math, os, itertools

__all__ = ["purged_kfold", "pbo_cscv", "promotion_gate"]


def purged_kfold(n, k, embargo=0):
    """Purged + embargoed k-fold splits for time series: each test fold is a CONTIGUOUS block; the train
    set excludes the test block AND `embargo` observations on each side. Returns [(train_idx, test_idx)]."""
    if k < 2 or n < k:
        return []
    fold = n // k; out = []
    for i in range(k):
        lo = i * fold; hi = n if i == k - 1 else (i + 1) * fold
        test = list(range(lo, hi))
        elo = max(0, lo - embargo); ehi = min(n, hi + embargo)
        train = [j for j in range(n) if j < elo or j >= ehi]
        out.append((train, test))
    return out


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def pbo_cscv(M, S=8):
    """Probability of Backtest Overfitting (CSCV). M: T x N performance matrix (rows=periods,
    cols=strategy candidates). Partition rows into S even blocks; for every choice of S/2 blocks as
    in-sample vs the rest out-of-sample, take the IS-best strategy and record its relative OOS rank ->
    logit. PBO = fraction of splits where the IS winner lands below the OOS median (logit < 0)."""
    T = len(M); N = len(M[0]) if T else 0
    if S % 2 or T < S or N < 2:
        return None
    blk = T // S
    blocks = [list(range(i * blk, T if i == S - 1 else (i + 1) * blk)) for i in range(S)]
    half = S // 2
    n_below = 0; tot = 0
    for combo in itertools.combinations(range(S), half):
        isset = set(combo)
        is_rows = [r for b in combo for r in blocks[b]]
        oos_rows = [r for b in range(S) if b not in isset for r in blocks[b]]
        is_perf = [_mean([M[r][c] for r in is_rows]) for c in range(N)]
        oos_perf = [_mean([M[r][c] for r in oos_rows]) for c in range(N)]
        nstar = max(range(N), key=lambda c: is_perf[c])
        order = sorted(range(N), key=lambda c: oos_perf[c])
        rank = order.index(nstar) + 1
        omega = rank / (N + 1.0)
        lam = math.log(omega / (1.0 - omega))
        n_below += (1 if lam < 0 else 0); tot += 1
    return (n_below / tot) if tot else None


def promotion_gate(dsr, pbo, min_dsr=0.95, max_pbo=0.5):
    """Machine-readable release gate: deployable only if DSR >= min_dsr AND PBO <= max_pbo."""
    okd = (dsr is not None and dsr >= min_dsr)
    okp = (pbo is not None and pbo <= max_pbo)
    reasons = []
    if not okd:
        reasons.append("DSR %.3f < %.2f (selection-adjusted Sharpe not significant)" % (dsr if dsr is not None else float("nan"), min_dsr))
    if not okp:
        reasons.append("PBO %.2f > %.2f (high backtest-overfit probability)" % (pbo if pbo is not None else float("nan"), max_pbo))
    return {"deployable": bool(okd and okp), "dsr": dsr, "pbo": pbo, "reasons": reasons or ["passes DSR + PBO"]}


def gen_fixture():
    # deterministic 24x4 performance matrix: strategy 0 has a genuine per-period edge, others are a fixed
    # pseudo-pattern (no RNG, so Py and JS lock to identical PBO).
    T, N = 24, 4
    M = [[((i * 7 + c * 13) % 11 - 5) / 5.0 + (0.6 if c == 0 else 0.0) for c in range(N)] for i in range(T)]
    pbo = pbo_cscv(M, S=6)
    splits = purged_kfold(20, 4, embargo=2)
    g_ok = promotion_gate(0.99, 0.10)
    g_dsr = promotion_gate(0.80, 0.10)
    g_pbo = promotion_gate(0.99, 0.70)
    return {"fixture_version": 1, "case": "validation-core",
            "M": M, "S": 6, "pbo": pbo,
            "splits": [[tr, te] for tr, te in splits],
            "gateOk": g_ok, "gateDsr": g_dsr, "gatePbo": g_pbo}


def main():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "validation_golden.json")
    json.dump(gen_fixture(), open(p, "w"), separators=(",", ":"))
    print("wrote", os.path.normpath(p))


if __name__ == "__main__":
    main()
