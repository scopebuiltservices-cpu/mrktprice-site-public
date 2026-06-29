#!/usr/bin/env python3
"""beta_board.py — POST-BUILD enrichment: raw OLS beta -> Vasicek-ADJUSTED beta (econometric correction).

External-enrichment pattern. For each name's committed weekly returns (n["wr"]):
  1. LEAVE-ONE-OUT equal-weighted market (excluding the name itself — regressing a stock on an index that
     INCLUDES it induces spurious self-correlation that biases beta up, worst for high-variance names).
  2. OLS beta + classical SE vs that market.
  3. VASICEK cross-sectional shrinkage toward the mean, weighted by precision wᵢ=σ²_cross/(σ²_cross+seᵢ²):
     noisy (high-SE) betas shrink more — a proper empirical-Bayes estimator.
(NOT Dimson: Dimson corrects DAILY non-synchronous trading of thin names; on weekly large-cap data it only
adds variance. The Dimson estimator lives in beta_adjust.py for that use case.)
Writes n["betaRaw"] (the recomputed OLS) and overwrites n["beta"] with the shrunk value the board's market-
drag term then uses. Idempotent; verified. Research only, not advice."""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import beta_adjust as BA


def _ew_market(series):
    if not series:
        return []
    L = min(len(s) for s in series)
    return [sum(s[t] for s in series) / len(series) for t in range(L)]


def enrich(mm, prior=None):
    names = mm.get("names") or []
    rbn = {}
    for n in names:
        wr = n.get("wr")
        if wr and len(wr) >= 30:
            rbn[n.get("t") or n.get("sym")] = [float(x) if (x is not None and x == x) else 0.0 for x in wr]
    if len(rbn) < 5:
        return 0
    L = min(len(v) for v in rbn.values())
    rbn = {k: v[:L] for k, v in rbn.items()}
    series = list(rbn.values())
    full = _ew_market(series)
    N = len(series)
    order = list(rbn.keys())
    betas = []; ses = []
    for tk in order:
        wr = rbn[tk]
        loo = [(N * full[t] - wr[t]) / (N - 1) for t in range(L)] if N > 1 else full
        b, se = BA.ols_beta_se(wr, loo)
        betas.append(b); ses.append(se)
    shr = BA.vasicek(betas, ses, prior=prior)              # prior=None -> cross-sectional mean
    raw = {order[i]: betas[i] for i in range(len(order))}
    adj = {order[i]: shr[i] for i in range(len(order))}
    done = 0
    for n in names:
        tk = n.get("t") or n.get("sym")
        a = adj.get(tk); r = raw.get(tk)
        if a is not None and a == a:
            if r is not None and r == r:
                n["betaRaw"] = round(r, 2)                  # the recomputed OLS that was adjusted
            elif n.get("beta") is not None:
                n["betaRaw"] = n["beta"]
            n["beta"] = round(a, 2)
            done += 1
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="marketmap.json")
    a = ap.parse_args()
    try:
        mm = json.load(open(a.map))
    except Exception as e:
        sys.stderr.write("beta_board: cannot read %s (%s)\n" % (a.map, str(e)[:80]))
        return 1
    done = enrich(mm)
    tmp = a.map + ".tmp"
    with open(tmp, "w") as f:
        json.dump(mm, f, separators=(",", ":"))
    os.replace(tmp, a.map)
    sys.stderr.write("beta_board: Vasicek-adjusted %d betas -> %s\n" % (done, a.map))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
