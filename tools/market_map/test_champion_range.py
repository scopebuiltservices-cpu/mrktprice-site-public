"""Planted-structure test for the range-aware _champion_sigma (Parkinson high/low blend).
Asserts: (1) with no highs/lows the result is BIT-IDENTICAL to the close-to-close champion (parity golden
and all prior behavior preserved); (2) supplying valid H/L engages the Parkinson blend and changes sigma;
(3) tighter intraday ranges -> smaller sigma than wider ranges (monotone in realized range); (4) degenerate
H/L (too few valid pairs) falls back to the close-to-close value."""
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


def series(seed, n=220, vol=0.012):
    rng = random.Random(seed); c = [100.0]
    for _ in range(n):
        c.append(c[-1] * math.exp(rng.gauss(0, vol)))
    return c


def bands(c, seed, halfrange):
    rng = random.Random(seed); hi = []; lo = []
    for x in c:
        p = abs(rng.gauss(0, halfrange)) + halfrange
        hi.append(x * (1 + p)); lo.append(x * (1 - p))
    return hi, lo


c = series(5)
H = 21
base = EE._champion_sigma(c, H)
ok("baseline produced", base is not None and base > 0)

# (1) None H/L => identical
ok("no H/L == close-to-close champion (parity preserved)", EE._champion_sigma(c, H, None, None) == base)

# (2) valid H/L engages the blend (differs from close-to-close)
hi, lo = bands(c, 7, 0.008)
sHL = EE._champion_sigma(c, H, hi, lo)
ok("H/L engages Parkinson blend (differs)", sHL is not None and abs(sHL - base) > 1e-9, (base, sHL))

# (3) monotone in realized range: tighter intraday range -> smaller sigma than wider range
hiT, loT = bands(c, 7, 0.003)   # tight
hiW, loW = bands(c, 7, 0.020)   # wide
sT = EE._champion_sigma(c, H, hiT, loT)
sW = EE._champion_sigma(c, H, hiW, loW)
ok("tighter range -> smaller sigma than wider range", sT < sW, (sT, sW))

# (4) degenerate H/L (all invalid) -> falls back to close-to-close
bad = [0.0] * len(c)
ok("degenerate H/L falls back to close-to-close", EE._champion_sigma(c, H, bad, bad) == base)

print("\nALL champion_range PASS" if not fail else "\nSOME champion_range TESTS FAILED")
sys.exit(1 if fail else 0)
