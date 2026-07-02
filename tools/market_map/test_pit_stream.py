"""Planted-structure test for pit_stream — matured studentized residuals -> expanding-window PIT ->
conformal e-process. Asserts: a STATIONARY well-specified residual stream yields ~uniform PIT and a quiet
alarm; a MEAN-DRIFTING stream (calibration degrading over time) fires; a VARIANCE-DRIFTING stream fires;
PIT values are in [0,1]; guards. Composes predictive_cdf + eprocess end-to-end."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pit_stream as PS

fail = 0


def ok(name, cond, extra=""):
    global fail
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        fail = 1


def recs(zs):
    return [{"z": z} for z in zs]


N = 500

# 1) stationary well-specified: z ~ iid N(0,1) -> expanding PIT ~ Uniform -> quiet
rng = random.Random(101)
cal = recs([rng.gauss(0, 1) for _ in range(N)])
ps = PS.pit_series(cal)
ok("pit_series produced", len(ps) > 100, len(ps))
ok("PIT in [0,1]", all(0.0 <= u <= 1.0 for u in ps))
ac = PS.calibration_alarm(cal)
ok("stationary: alarm produced", ac is not None)
ok("stationary: quiet (ok)", ac["level"] == "ok", (ac["level"], ac["eMax"]))
ok("stationary: source + nPit stamped", ac.get("nPit", 0) > 100 and "expanding-window" in ac.get("source", ""))

# 2) mean drift: residual centering degrades over the stream (ramp 0 -> +2) -> later PIT skews high -> fires
rng = random.Random(102)
drift = recs([rng.gauss(0, 1) + 2.0 * (t / N) for t in range(N)])
ad = PS.calibration_alarm(drift)
ok("mean drift: fires (warn+)", ad and ad["level"] in ("warn", "kill"), ad and (ad["level"], ad["eMax"]))

# 3) variance drift: dispersion grows over the stream -> later |z| large vs past -> fires
rng = random.Random(103)
vdrift = recs([rng.gauss(0, 1) * (1.0 + 2.5 * (t / N)) for t in range(N)])
av = PS.calibration_alarm(vdrift)
ok("variance drift: fires (warn+)", av and av["level"] in ("warn", "kill"), av and (av["level"], av["eMax"]))

# 4) guards
ok("too few matured -> [] series", PS.pit_series(recs([0.1] * 30)) == [])
ok("too few matured -> None alarm", PS.calibration_alarm(recs([0.1] * 30)) is None)
ok("ignores non-numeric z", isinstance(PS.pit_series(recs([0.0] * 80) + [{"z": None}, {"nope": 1}]), list))

print("\nALL pit_stream PASS" if not fail else "\nSOME pit_stream TESTS FAILED")
sys.exit(1 if fail else 0)
