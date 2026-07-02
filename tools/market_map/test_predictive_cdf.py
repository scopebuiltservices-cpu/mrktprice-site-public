"""Planted-structure test for predictive_cdf.PredictiveCDF — the sample-based predictive distribution.
Asserts: monotone quantiles + cdf/quantile roundtrip; CRPS is proper (lower near the mode, higher in the
tail); on a HEAVY-TAILED truth the sample CRPS beats the Gaussian CRPS (same mean/variance); randomized
PIT of out-of-sample true draws is ~Uniform (KS); GPD tail-splice extrapolates beyond the sample max;
degenerate inputs raise."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import predictive_cdf as P

fail = 0


def ok(name, cond, extra=""):
    global fail
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        fail = 1


def raises(fn):
    try:
        fn(); return False
    except Exception:
        return True


def heavy_z(rng, n):
    """Normal variance-mixture: 90% N(0,1), 10% N(0,9) -> heavy-tailed, mean 0."""
    out = []
    for _ in range(n):
        s = 3.0 if rng.random() < 0.10 else 1.0
        out.append(rng.gauss(0, 1) * s)
    return out


rng = random.Random(11)
z = heavy_z(rng, 400)
pc = P.PredictiveCDF(mu=0.0, sigma=0.02, z_samples=z)

# monotonicity + roundtrip
q10, q50, q90 = pc.quantile(0.1), pc.quantile(0.5), pc.quantile(0.9)
ok("quantiles monotone", q10 < q50 < q90, (q10, q50, q90))
ok("cdf monotone", pc.cdf(q10) < pc.cdf(q50) < pc.cdf(q90))
ok("cdf/quantile roundtrip", abs(pc.cdf(pc.quantile(0.4)) - 0.4) < 0.03, pc.cdf(pc.quantile(0.4)))

# CRPS proper: lower near the sample median than far in the tail
ok("CRPS lower at center than tail", pc.crps_sample(q50) < pc.crps_sample(q50 + 6 * 0.02))

# sample CRPS beats Gaussian on heavy tails (fair: Gaussian uses matched mean/std of the SAME samples)
mean_s = sum(pc.samples) / pc.n
sd_s = math.sqrt(sum((s - mean_s) ** 2 for s in pc.samples) / (pc.n - 1))
rng2 = random.Random(29)
ys = [0.0 + 0.02 * zz for zz in heavy_z(rng2, 600)]        # fresh out-of-sample heavy-tailed truth
csamp = sum(pc.crps_sample(y) for y in ys) / len(ys)
cgauss = sum(P.crps_gaussian(mean_s, sd_s, y) for y in ys) / len(ys)
ok("sample CRPS <= Gaussian CRPS on heavy tails", csamp <= cgauss + 1e-9, "sample=%.6f gauss=%.6f" % (csamp, cgauss))

# randomized PIT of out-of-sample true draws ~ Uniform(0,1): KS distance small
rng3 = random.Random(7)
pits = sorted(pc.randomized_pit(y, u=rng3.random()) for y in ys)
n = len(pits); ks = 0.0
for i, u in enumerate(pits, start=1):
    ks = max(ks, abs(u - (i - 0.5) / n))
ok("randomized PIT ~ Uniform (KS small)", ks < 0.10, "ks=%.4f" % ks)
ok("PIT within [0,1]", all(0.0 <= u <= 1.0 for u in pits))

# GPD tail splice extrapolates beyond the empirical support at EXTREME quantiles (empirical clips at the
# sample max; GPD keeps growing). Check unbounded growth past the observed max, and monotone tail growth.
pcg = P.PredictiveCDF(mu=0.0, sigma=0.02, z_samples=z, gpd_tails=True)
smax = pc.samples[-1]
ok("GPD upper tail extrapolates beyond sample max at extreme p", pcg.quantile(0.99999) > smax, (pcg.quantile(0.99999), smax))
ok("GPD tail quantile grows with p", pcg.quantile(0.9999) < pcg.quantile(0.99999))
ok("GPD tail cdf monotone", pcg.cdf(smax) <= pcg.cdf(smax * 1.5) <= 1.0)

# guards
ok("too few samples raises", raises(lambda: P.PredictiveCDF(0, 0.02, [0.1] * 5)))
ok("sigma<=0 raises", raises(lambda: P.PredictiveCDF(0, 0, z)))
ok("crps_gaussian sane (0 at delta-ish)", P.crps_gaussian(0, 1e-9, 0.0) < 1e-3)

print("\nALL predictive_cdf PASS" if not fail else "\nSOME predictive_cdf TESTS FAILED")
sys.exit(1 if fail else 0)
