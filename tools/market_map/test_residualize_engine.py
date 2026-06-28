"""Planted tests: OLS recovers known betas; residualize strips the factor-explained part, keeps idio edge."""
import sys, os, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import residualize_engine as R

def _gen(seed, T=500, true_betas=None):
    rng = random.Random(seed)
    if true_betas is None:
        true_betas = {"MktRF": 1.10, "SMB": 0.40, "HML": -0.30, "RMW": 0.20, "CMA": 0.05, "Mom": 0.60}
    rows, excess = [], []
    for _ in range(T):
        r = {f: rng.gauss(0, 0.01) for f in R.FACTORS}      # daily factor returns ~1% sd
        rows.append(r)
        idio = rng.gauss(0, 0.005)
        ne = sum(true_betas[f] * r[f] for f in R.FACTORS) + idio
        excess.append(ne)
    return rows, excess, true_betas

def test_recovers_betas():
    rows, excess, tb = _gen(1)
    fit = R.factor_betas(excess, rows)
    for f in R.FACTORS:
        assert abs(fit["betas"][f] - tb[f]) < 0.05, (f, fit["betas"][f], tb[f])
    assert fit["r2"] > 0.7, fit["r2"]
    print("  PASS  OLS recovers planted betas (max err < 0.05, R2=%.3f)" % fit["r2"])

def test_residualize_strips_factor_bet():
    rows, excess, tb = _gen(2)
    fit = R.factor_betas(excess, rows)
    prem = R.factor_premia(rows)
    H = 21
    factor_exp = H * sum(fit["betas"][f] * prem[f] for f in R.FACTORS)
    # Case A: alpha is PURELY a factor bet -> residual ~ 0
    a = R.residualize(factor_exp, fit["betas"], prem, H)
    assert abs(a["muResid"]) < 1e-9, a["muResid"]
    # Case B: alpha = factor bet + genuine idio edge delta -> residual ~ delta
    delta = 0.03
    b = R.residualize(factor_exp + delta, fit["betas"], prem, H)
    assert abs(b["muResid"] - delta) < 1e-9, b["muResid"]
    print("  PASS  residualize: pure factor bet -> 0; factor+%.0f%% idio -> %.4f kept" % (delta*100, b["muResid"]))

def test_premia_mean_and_ewma():
    rows, _, _ = _gen(3, T=300)
    pm = R.factor_premia(rows)
    pe = R.factor_premia(rows, halflife=60)
    assert all(f in pm and f in pe for f in R.FACTORS)
    # mean over symmetric noise ~ 0
    assert abs(pm["MktRF"]) < 0.01
    print("  PASS  factor_premia mean + EWMA(halflife) compute over all 6 factors")

def test_drops_missing_rows():
    rows, excess, _ = _gen(4, T=200)
    rows[10]["HML"] = None; excess[20] = None     # one bad factor, one bad target
    fit = R.factor_betas(excess, rows)
    assert fit["n"] <= 198
    print("  PASS  rows with missing factor/target dropped (n=%d)" % fit["n"])

if __name__ == "__main__":
    test_recovers_betas(); test_residualize_strips_factor_bet(); test_premia_mean_and_ewma(); test_drops_missing_rows()
    print("\nALL RESIDUALIZE ENGINE TESTS PASSED")
