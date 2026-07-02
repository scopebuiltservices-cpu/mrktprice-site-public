"""Contract tests for contracts.HorizonSpec / TargetBasis — the typed forecast contracts that prevent
silent mixing of horizons and target spaces. All deterministic, pure stdlib."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contracts as C

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


# ---- HorizonSpec ----
hs = C.HorizonSpec(h=10, unit="bar", bar_minutes=5, session_minutes=390)
ok("bar horizon bars()==h", hs.bars() == 10, hs.bars())
ok("session_bars = session/bar", hs.session_bars() == 78.0, hs.session_bars())
ok("horizon_minutes = h*bar_minutes", hs.horizon_minutes() == 50, hs.horizon_minutes())
ok("day horizon bars()==h", C.HorizonSpec(h=21, unit="day", session_minutes=390).bars() == 21)
ok("h<=0 raises", raises(lambda: C.HorizonSpec(h=0, unit="day")))
ok("bar unit without bar_minutes raises", raises(lambda: C.HorizonSpec(h=5, unit="bar", session_minutes=390)))
ok("bar/minute unit without session_minutes raises", raises(lambda: C.HorizonSpec(h=5, unit="minute")))
ok("bad unit raises", raises(lambda: C.HorizonSpec(h=5, unit="week")))
ok("bad label_type raises", raises(lambda: C.HorizonSpec(h=5, unit="day", label_type="banana")))
ok("frozen/immutable", raises(lambda: setattr(hs, "h", 99)))
ok("key is stable", C.HorizonSpec(h=21, unit="day").key() == "21d/close", C.HorizonSpec(h=21, unit="day").key())

# ---- TargetBasis ----
tb = C.TargetBasis("log_return", "total_return")
ok("log_return transform", abs(tb.transform_terminal(100, 110) - math.log(1.1)) < 1e-12, tb.transform_terminal(100, 110))
ok("simple_return transform", abs(C.TargetBasis("simple_return", "raw_close").transform_terminal(100, 110) - 0.1) < 1e-12)
ok("price_delta transform", C.TargetBasis("price_delta", "raw_close").transform_terminal(100, 110) == 10.0)
ok("log_price transform", abs(C.TargetBasis("log_price", "raw_close").transform_terminal(100, 110) - math.log(110)) < 1e-12)
ok("raw_price transform", C.TargetBasis("raw_price", "raw_close").transform_terminal(100, 110) == 110)
ok("is_return_space", tb.is_return_space() and not C.TargetBasis("price_delta", "raw_close").is_return_space())
ok("bad target_space raises", raises(lambda: C.TargetBasis("touch", "raw_close")))
ok("bad price_basis raises", raises(lambda: C.TargetBasis("log_return", "options_iv")))
ok("non-positive price raises", raises(lambda: tb.transform_terminal(0, 110)))

# ---- compatibility gate ----
h1 = C.HorizonSpec(h=21, unit="day"); h2 = C.HorizonSpec(h=21, unit="day")
h3 = C.HorizonSpec(h=5, unit="day")
t1 = C.TargetBasis("log_return", "total_return"); t2 = C.TargetBasis("log_return", "raw_close")
ok("compatible: identical", C.compatible(h1, t1, h2, t1))
ok("incompatible: different horizon", not C.compatible(h1, t1, h3, t1))
ok("incompatible: different price basis", not C.compatible(h1, t1, h2, t2))

# ---- canonical defaults ----
ok("DAILY_21 default", C.DAILY_21.h == 21 and C.DAILY_21.unit == "day")
ok("TOTAL_RETURN default", C.TOTAL_RETURN.target_space == "log_return" and C.TOTAL_RETURN.price_basis == "total_return")

print("\nALL contracts PASS" if not fail else "\nSOME contracts TESTS FAILED")
sys.exit(1 if fail else 0)
