import sys, os, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proj_server as S

def _ou_series(seed, n=900, theta=0.03, mu=math.log(100), sd=0.01):
    rng = random.Random(seed); lp = mu; out = []
    for _ in range(n):
        lp = lp + theta * (mu - lp) + rng.gauss(0, sd)     # discrete OU around mu
        out.append(math.exp(lp))
    return out

def test_ou_recovers_meanrev():
    c = _ou_series(1)
    lp = [math.log(x) for x in c]
    ou = S.ou_fit(lp)
    assert ou["theta"] > 0.005, ou["theta"]                 # detects mean reversion
    # if price is BELOW long-run mean, OU drift should be POSITIVE (revert up)
    below = ou["mu"] - 0.05
    assert S.ou_drift(below, ou, 21) > 0
    print("  PASS  OU fit recovers mean reversion (theta=%.3f); drift reverts toward mu" % ou["theta"])

def test_blend_beats_naive_on_meanrev():
    # walk-forward: does blend_drift have positive skill vs no-change on a mean-reverting series?
    c = _ou_series(2, n=1200)
    H = 21; preds = []; reals = []
    for t in range(60, len(c) - H, 3):
        d = S.blend_drift(c[:t], H, w_ou=1.0, w_mom=0.0)     # OU component (the edge source); no lookahead
        preds.append(d); reals.append(math.log(c[t - 1 + H] / c[t - 1]))
    n = len(preds)
    mse_m = sum((reals[i] - preds[i]) ** 2 for i in range(n)) / n
    mse_n = sum(r * r for r in reals) / n
    skill = 1 - mse_m / mse_n
    assert skill > 0.0, skill                               # beats naive on a mean-reverting world
    print("  PASS  OU drift skill-vs-naive on mean-reverting series = %.3f (>0)" % skill)

def test_no_lookahead():
    c = _ou_series(3, n=400)
    d1 = S.blend_drift(c[:200], 10)
    c2 = c[:]; 
    for i in range(200, len(c2)): c2[i] *= 1.4
    d2 = S.blend_drift(c2[:200], 10)
    assert abs(d1 - d2) < 1e-12
    print("  PASS  no-lookahead: drift at t uses only closes[:t]")

if __name__ == "__main__":
    test_ou_recovers_meanrev(); test_blend_beats_naive_on_meanrev(); test_no_lookahead()
    print("\nALL PROJ_SERVER TESTS PASSED")
