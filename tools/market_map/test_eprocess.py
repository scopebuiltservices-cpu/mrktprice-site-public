"""Planted-structure test for eprocess.conformal_eprocess — the anytime-valid calibration test martingale.
Asserts: on a CALIBRATED (Uniform) PIT stream the e-process stays quiet (eMax < warn, level 'ok'); a
LOCATION-biased stream fires (mean PIT != 1/2); an OVER-DISPERSED (U-shaped, mean still 1/2) stream fires
via the DISPERSION component (proving it catches what the location bet misses); an UNDER-DISPERSED (humped)
stream also fires on dispersion; Ville sanity (eMax >= eValue, pAnytime = 1/eMax); guards."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eprocess as E

fail = 0


def ok(name, cond, extra=""):
    global fail
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        fail = 1


N = 600
# 1) calibrated: U ~ Uniform(0,1)
rng = random.Random(20250701)
cal = [rng.random() for _ in range(N)]
rc = E.conformal_eprocess(cal)
ok("calibrated: produced", rc is not None)
ok("calibrated: stays quiet (level ok)", rc["level"] == "ok", (rc["level"], rc["eMax"]))
ok("calibrated: eMax < warn", rc["eMax"] < rc["warn"], rc["eMax"])

# 2) location bias: PIT mean ~0.35 (forecast centerline biased) -> U = z*0.7
rng = random.Random(2)
loc = [rng.random() * 0.7 for _ in range(N)]
rl = E.conformal_eprocess(loc)
ok("location bias: fires (warn+)", rl["level"] in ("warn", "kill"), (rl["level"], rl["eMax"]))
ok("location bias: location component drives it", rl["components"]["loc"]["hedgedMax"] >= rl["components"]["disp"]["hedgedMax"])

# 3) over-dispersion: bands too NARROW -> PIT U-shaped (arcsine), mean 1/2 but piled at 0/1
rng = random.Random(3)
over = [math.sin(math.pi * rng.random() / 2.0) ** 2 for _ in range(N)]   # arcsine on [0,1], mean 1/2
ro = E.conformal_eprocess(over)
mean_over = sum(over) / len(over)
ok("over-dispersion: mean still ~1/2", abs(mean_over - 0.5) < 0.05, mean_over)
ok("over-dispersion: fires (warn+)", ro["level"] in ("warn", "kill"), (ro["level"], ro["eMax"]))
ok("over-dispersion: DISPERSION component drives it (loc would miss)",
   ro["components"]["disp"]["hedgedMax"] > ro["components"]["loc"]["hedgedMax"])

# 4) under-dispersion: bands too WIDE -> PIT humped near 1/2 (low variance), mean 1/2
rng = random.Random(4)
under = [0.5 + (rng.random() - 0.5) * 0.25 for _ in range(N)]
ru = E.conformal_eprocess(under)
ok("under-dispersion: fires on dispersion", ru["level"] in ("warn", "kill") and
   ru["components"]["disp"]["hedgedMax"] > ru["components"]["loc"]["hedgedMax"], (ru["level"], ru["eMax"]))

# 5) Ville / bookkeeping sanity
ok("eMax >= eValue (running sup)", rl["eMax"] >= rl["eValue"] - 1e-9)
ok("pAnytime = 1/eMax capped", abs(rc["pAnytime"] - min(1.0, 1.0 / rc["eMax"])) < 1e-3)
ok("miscalibration pAnytime small", rl["pAnytime"] < 0.05, rl["pAnytime"])

# 6) guards
ok("too few PIT -> None", E.conformal_eprocess([0.5] * 10) is None)
ok("out-of-range PIT filtered", E.conformal_eprocess([0.4, 1.7, -0.2] + [0.5] * 25) is not None)

print("\nALL eprocess PASS" if not fail else "\nSOME eprocess TESTS FAILED")
sys.exit(1 if fail else 0)
