"""Locks the SERVER calibration wire that lights the terminal's calibration chip:
   closes -> projledger.walk_forward (no-lookahead matured residuals) -> studentized z
          -> pit_stream.calibration_alarm (predictive-CDF PIT -> conformal e-process).
This is the exact composition build_market_map.build() stamps as snap['calibEprocess'] and terminal.html's
renderCalibMark() reads via window.MMAP.calibEprocess. Asserts: enough pooled matured residuals produce a
well-formed anytime-valid alarm dict (level in ok/warn/kill, pAnytime=1/eMax, nPit reported); the guard
returns None below the minimum; and the field is JSON-serializable (so it survives into marketmap.json)."""
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projledger as PL
import pit_stream as PS

fail = 0


def ok(name, cond, extra=""):
    global fail
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        fail = 1


def _series(rng, n=400, vol=0.02, drift=0.0):
    px, out = 100.0, [100.0]
    for _ in range(n):
        px *= (1.0 + rng.gauss(drift, vol))
        out.append(round(px, 4))
    return out


def _pool(series_list):
    """Reproduce the build wire exactly: walk_forward -> horizon-21 (or first) matured (pred,real,sigma) ->
    studentized residual records {z}. Time order preserved within each name (expanding-window PIT is valid)."""
    mat = []
    for c in series_list:
        wf = PL.walk_forward(c)
        if not wf:
            continue
        rows = wf.get(21) or wf[sorted(wf.keys())[0]]
        for pr, rl, sg in rows:
            if sg and sg > 0:
                mat.append({"z": (rl - pr) / sg})
    return mat


rng = random.Random(7)
mat = _pool([_series(rng) for _ in range(12)])
ok("pool produced >=60 matured residuals", len(mat) >= 60, len(mat))

ce = PS.calibration_alarm(mat)
ok("alarm produced on sufficient history", ce is not None)
if ce:
    ok("level in {ok,warn,kill}", ce["level"] in ("ok", "warn", "kill"), ce["level"])
    ok("pAnytime = 1/eMax (capped at 1)", abs(ce["pAnytime"] - min(1.0, 1.0 / ce["eMax"])) < 1e-3, (ce["pAnytime"], ce["eMax"]))
    ok("nPit reported and positive", ce.get("nPit", 0) > 0, ce.get("nPit"))
    ok("eMax finite and >= 0", math.isfinite(ce["eMax"]) and ce["eMax"] >= 0, ce["eMax"])
    ok("JSON-serializable (survives into marketmap.json)", isinstance(json.dumps(ce), str))

# guard: below the >=60 matured floor the build stamps None (chip stays dark), never raises
ok("guard: <60 matured -> None (no-op)", PS.calibration_alarm([{"z": 0.1}] * 20) is None)

print("\nALL calib_wire PASS" if not fail else "\nSOME calib_wire TESTS FAILED")
sys.exit(1 if fail else 0)
