"""Planted-structure test for direction_vr_validate.validate().

Asserts the honest behaviour of the VR-overlay validation that gates the terminal's Direction-Deck
synthesis line:
  1. Persistently MEAN-REVERTING name -> VALIDATED: following the push loses (baseline Sharpe<0), the
     fade-contra overlay wins (edge>0), the fade mechanism is significant, and DSR+PBO deploy.
  2. RANDOM WALK -> NOT VALIDATED: no selection-adjusted edge (DSR fails, no significant mechanism).
  3. Persistently TRENDING name -> NOT VALIDATED: following the push is already ~optimal, so the VR
     overlay is redundant (edge<=0) -> honestly not an improvement over direction-alone.
  4. NO-LOOKAHEAD: corrupting the tail of the series leaves every earlier window's signal
     (push / persist / fade / pnl) byte-identical -> the walk-forward uses only prefix information.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import direction_vr_validate as DV

fail = 0


def ok(name, cond, extra=""):
    global fail
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        fail = 1


def mean_revert(seed, n=1800, k=0.75, vol=0.012):
    rng = random.Random(seed); c = [100.0]; prev = 0.0
    for _ in range(n):
        z = rng.gauss(0, 1); step = vol * z - k * prev; prev = step; c.append(c[-1] * math.exp(step))
    return c


def trend(seed, n=1400, a=0.6, vol=0.010):
    rng = random.Random(seed); c = [100.0]; e = 0.0
    for _ in range(n):
        e = a * e + (1 - a) * rng.gauss(0, 1); c.append(c[-1] * math.exp(vol * e))
    return c


def rw(seed, n=1400, vol=0.012):
    rng = random.Random(seed); c = [100.0]
    for _ in range(n):
        c.append(c[-1] * math.exp(rng.gauss(0, vol)))
    return c


# 1. mean-reverting -> VALIDATED, fade-contra beats naive push-following
mr = DV.validate(mean_revert(1))
ok("MR verdict VALIDATED", mr["verdict"] == "VALIDATED", mr["verdict"])
ok("MR baseline (follow push) loses", mr["strategies"]["A_baseline"]["sharpe"] < 0, mr["strategies"]["A_baseline"]["sharpe"])
ok("MR fade-contra overlay wins", mr["strategies"]["C_persistFade"]["sharpe"] > 0, mr["strategies"]["C_persistFade"]["sharpe"])
ok("MR edge over direction-alone > 0", mr["edgeSharpe"] > 0, mr["edgeSharpe"])
ok("MR fade mechanism significant (push reverses)", mr["mechanism"]["fadeReverses"] is True, mr["mechanism"])
ok("MR gate deployable (DSR>=.95 & PBO<=.5)", mr["gate"]["deployable"] is True, (mr["dsr"], mr["pbo"]))

# 2. random walk -> NOT VALIDATED
r = DV.validate(rw(3))
ok("RW verdict NOT VALIDATED", r["verdict"] == "NOT VALIDATED", r["verdict"])
ok("RW gate NOT deployable", r["gate"]["deployable"] is False, (r["dsr"], r["pbo"]))

# 3. trending -> NOT VALIDATED (overlay redundant; following the push is already ~optimal)
tr = DV.validate(trend(2))
ok("TREND verdict NOT VALIDATED (overlay redundant)", tr["verdict"] == "NOT VALIDATED", tr["verdict"])
ok("TREND baseline (follow push) is positive", tr["strategies"]["A_baseline"]["sharpe"] > 0, tr["strategies"]["A_baseline"]["sharpe"])
ok("TREND overlay does not beat direction-alone", tr["edgeSharpe"] <= 0, tr["edgeSharpe"])

# 4. NO-LOOKAHEAD: corrupt the tail; every window ending before the corruption is unchanged
base = mean_revert(5, n=1000)
d0 = DV.validate(base, debug=True)["_windows"]
corrupt = list(base)
cut = len(corrupt) - 40
for i in range(cut, len(corrupt)):
    corrupt[i] = corrupt[i] * 3.0  # violent tail change
d1 = DV.validate(corrupt, debug=True)["_windows"]
# windows whose forward horizon (t+h, h=10) ends before the corruption must be identical
unchanged_ok = True
for w0, w1 in zip(d0, d1):
    if w0[0] + 10 < cut:  # this window's data is entirely in the untouched prefix
        if w0 != w1:
            unchanged_ok = False; break
ok("no-lookahead: pre-corruption windows byte-identical", unchanged_ok)
ok("no-lookahead: some later windows DID change (corruption took effect)", d0 != d1)

# gating on thin input
ok("thin history -> INSUFFICIENT", DV.validate([100.0] * 30)["verdict"] == "INSUFFICIENT")

print("\nALL direction_vr_validate PASS" if not fail else "\nSOME direction_vr_validate TESTS FAILED")
sys.exit(1 if fail else 0)
