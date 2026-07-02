"""Planted-structure test for expectations_engine.expected_band_boot (dependence-aware stationary-bootstrap
endpoint prediction interval). Asserts: it produces a bracketing band, is deterministic under a fixed seed,
is monotone in the confidence level, is empirically well-calibrated (walk-forward containment ~ level) on an
i.i.d. series, and is WIDER than the i.i.d. parametric band on a positively-autocorrelated series (dependence
inflates multi-step dispersion)."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import expectations_engine as EE

fail = 0


def ok(name, cond, extra=""):
    global fail
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        fail = 1


def rw(seed, n=600, vol=0.012):
    rng = random.Random(seed); c = [100.0]
    for _ in range(n):
        c.append(c[-1] * math.exp(rng.gauss(0, vol)))
    return c


def ar1(seed, n=600, a=0.55, vol=0.011):
    """Positively-autocorrelated log returns (r_t = a*r_{t-1} + eps) -> multi-step variance > H*var1."""
    rng = random.Random(seed); c = [100.0]; e = 0.0
    for _ in range(n):
        e = a * e + rng.gauss(0, vol); c.append(c[-1] * math.exp(e))
    return c


H = 21
rwc = rw(1)
b = EE.expected_band_boot(rwc[-1], rwc, level=0.90, H=H)
ok("rw: produced", b is not None)
ok("rw: brackets price", b and b["lo"] < rwc[-1] < b["hi"], b)
ok("rw: kind labeled", b and "bootstrap" in b["kind"])

# determinism (fixed seed)
b2 = EE.expected_band_boot(rwc[-1], rwc, level=0.90, H=H)
ok("deterministic under seed", b and b2 and b["lo"] == b2["lo"] and b["hi"] == b2["hi"])

# monotone in level
b70 = EE.expected_band_boot(rwc[-1], rwc, level=0.70, H=H)
b95 = EE.expected_band_boot(rwc[-1], rwc, level=0.95, H=H)
ok("wider at higher level", b70 and b95 and (b95["hi"] - b95["lo"]) > (b70["hi"] - b70["lo"]),
   (b70 and b70["rangePct"], b95 and b95["rangePct"]))

# empirical walk-forward containment ~ level on the i.i.d. series
level = 0.90
hit = 0; tot = 0
for t in range(120, len(rwc) - H, 5):
    bb = EE.expected_band_boot(rwc[t], rwc[:t + 1], level=level, H=H)
    if not bb:
        continue
    tot += 1
    if bb["lo"] <= rwc[t + H] <= bb["hi"]:
        hit += 1
cov = hit / tot if tot else 0.0
ok("rw: walk-forward containment ~ level (0.90)", tot >= 20 and abs(cov - level) <= 0.12, "cov=%.3f n=%d" % (cov, tot))

# dependence effect: on AR(1)+ the bootstrap half-width (log) exceeds the i.i.d. parametric z*sd*sqrt(H)
ac = ar1(7)
lr = [math.log(ac[i] / ac[i - 1]) for i in range(1, len(ac))]
m = sum(lr) / len(lr); sd = math.sqrt(sum((x - m) ** 2 for x in lr) / (len(lr) - 1))
z = EE._norm_ppf(0.95)
iid_hw_log = z * sd * math.sqrt(H)                       # i.i.d. parametric half-width in log space
bab = EE.expected_band_boot(ac[-1], ac, level=0.90, H=H)
boot_hw_log = math.log(bab["hi"] / bab["lo"]) / 2.0 if bab else None
ok("ar1+: bootstrap wider than i.i.d. parametric", boot_hw_log is not None and boot_hw_log > iid_hw_log * 1.05,
   "boot=%.4f iid=%.4f" % (boot_hw_log or -1, iid_hw_log))

# guards
ok("thin history -> None", EE.expected_band_boot(100.0, [100.0] * 20, H=H) is None)
ok("bad price -> None", EE.expected_band_boot(0, rwc, H=H) is None)

print("\nALL expected_band_boot PASS" if not fail else "\nSOME expected_band_boot TESTS FAILED")
sys.exit(1 if fail else 0)
