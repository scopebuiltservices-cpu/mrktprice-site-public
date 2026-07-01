#!/usr/bin/env python3
"""Planted tests for state_persistence.py. Run: python3 test_state_persistence.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from state_persistence import PersistenceGate, confirm_series, run_lengths

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

ok("run_lengths counts trailing True run", run_lengths([0, 1, 1, 0, 1]) == [0, 1, 2, 0, 1])

# --- single-bar flicker NEVER confirms with k_on=2 ---
flick = [False, True, False, True, False, True, False]
res = confirm_series(flick, k_on=2)
ok("1-bar flicker never confirms (k_on=2)", not any(res["confirmed"]), res["confirmed"])
ok("flicker: 0 episodes", res["episodes"] == 0)

# --- sustained run confirms exactly at the K_on-th consecutive window ---
g = PersistenceGate(k_on=3, k_off=2)
seq = [True, True, True, True]
states = [g.update(x)["confirmed"] for x in seq]
ok("confirms exactly on the 3rd consecutive in-state", states == [False, False, True, True], states)

# --- hysteresis: a single in-run dip does NOT clear until k_off consecutive exits ---
g2 = PersistenceGate(k_on=2, k_off=3)
pat = [True, True, True, False, True, True]      # one dip at index 3
confs = [g2.update(x)["confirmed"] for x in pat]
ok("confirmed by index1", confs[1] is True)
ok("single dip does NOT un-confirm (k_off=3)", confs[3] is True and confs[4] is True, confs)

# --- k_off consecutive exits DO clear ---
g3 = PersistenceGate(k_on=2, k_off=2)
pat3 = [True, True, False, False, True]
c3 = [g3.update(x)["confirmed"] for x in pat3]
ok("two consecutive exits clear the state", c3 == [False, True, True, False, False], c3)

# --- whipsaw reduction: confirmation yields fewer, longer episodes than raw crossings ---
raw = [True, False, True, False, True, True, True, True, True, False, True, False] * 5
r = confirm_series(raw, k_on=3, k_off=3)
raw_episodes = 0
prev = False
for f in raw:
    if f and not prev:
        raw_episodes += 1
    prev = f
ok("persistence gate cuts episode count vs raw crossings", r["episodes"] < raw_episodes, {"gate": r["episodes"], "raw": raw_episodes})
# hysteresis (k_off>1) deliberately holds through dips, so it can fill gaps and RAISE on-fraction while
# still cutting turnover. The 'never adds exposure' property belongs to the no-hysteresis case (k_off=1):
r_nohys = confirm_series(raw, k_on=3, k_off=1)
ok("no-hysteresis (k_off=1) never adds exposure: confirmedOnFrac <= rawOnFrac",
   r_nohys["confirmedOnFrac"] <= r_nohys["rawOnFrac"], r_nohys)
ok("hysteresis fills dips (confirmedOnFrac can exceed rawOnFrac) yet cuts episodes",
   r["confirmedOnFrac"] >= r_nohys["confirmedOnFrac"] and r["episodes"] <= r_nohys["episodes"],
   {"hys": r["episodes"], "noHys": r_nohys["episodes"]})
ok("dwell grows within a confirmed episode", max(r["dwell"]) >= 3, max(r["dwell"]))

print("\n" + ("ALL STATE-PERSISTENCE TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
