"""Planted-structure tests for debt_engine.py — exact arithmetic + tilt sign/bounds + None-safety."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import debt_engine as D

fail = 0


def ok(name, cond, extra=""):
    global fail
    if cond:
        print("  PASS ", name)
    else:
        print("  FAIL ", name, extra); fail = 1


def close(a, b, tol=1e-6):
    return a is not None and abs(a - b) <= tol


# --- primitives (exact) ---
ok("net_debt positive", close(D.net_debt(100, 30), 70.0))
ok("net_debt net-cash negative", close(D.net_debt(20, 50), -30.0))
ok("net_debt None on missing", D.net_debt(None, 30) is None)
ok("EV base", close(D.enterprise_value(1000, 100, 30), 1070.0))
ok("EV with pref+nci", close(D.enterprise_value(1000, 100, 30, preferred=10, minority_interest=5), 1085.0))
ok("EV/EBITDA", close(D.ev_ebitda(1070, 200), 5.35))
ok("EV/EBITDA None on EBITDA<=0", D.ev_ebitda(1070, 0) is None and D.ev_ebitda(1070, -5) is None)
ok("netDebt/EBITDA", close(D.net_debt_to_ebitda(70, 200), 0.35))
ok("D/E", close(D.debt_to_equity(100, 500), 0.2))
ok("D/E None on equity<=0", D.debt_to_equity(100, 0) is None and D.debt_to_equity(100, -50) is None)
ok("interest coverage", close(D.interest_coverage(300, 20), 15.0))
ok("coverage handles signed interest", close(D.interest_coverage(300, -20), 15.0))
ok("coverage None on zero interest", D.interest_coverage(300, 0) is None)

# --- debt growth (exact) ---
g = D.debt_growth([100, 110, 121])
ok("growth pct", g and g["pct"] == [0.1, 0.1])
ok("growth cagr", g and close(g["cagr"], 0.1))
ok("growth last", g and close(g["last"], 0.1))
ok("growth None on <2 pts", D.debt_growth([100]) is None)

# --- leverage tilt (sign + bounds) ---
t_cash = D.leverage_tilt(None, None, None, is_net_cash=True)
ok("tilt net-cash == +1", close(t_cash, 1.0))
t_bad = D.leverage_tilt(6.0, 0.5, {"cagr": 0.25}, is_net_cash=False)
ok("tilt high-lev is negative", t_bad is not None and t_bad < 0, t_bad)
ok("tilt bounded [-1,1]", t_bad is not None and -1.0 <= t_bad <= 1.0, t_bad)
t_good = D.leverage_tilt(0.5, 12.0, {"cagr": -0.05}, is_net_cash=False)
ok("tilt strong-credit is positive", t_good is not None and t_good > 0, t_good)
ok("tilt None when no components", D.leverage_tilt(None, None, None, is_net_cash=False) is None)

# --- report bundles ---
r_nc = D.debt_report(mktcap=1000, total_debt=20, cash=50, equity=500, ebitda=200, ebit=300, interest_expense=5)
ok("report net-cash verdict", r_nc["verdict"] == "net cash" and r_nc["netCash"] is True)
ok("report net-cash tilt>0", r_nc["tilt"] is not None and r_nc["tilt"] > 0)
r_hi = D.debt_report(mktcap=1000, total_debt=1200, cash=50, equity=400, ebitda=200, ebit=150,
                     interest_expense=90, debt_series=[600, 900, 1200])
ok("report high-lev verdict", r_hi["verdict"] == "high leverage", r_hi["verdict"])
ok("report high-lev tilt<0", r_hi["tilt"] is not None and r_hi["tilt"] < 0, r_hi["tilt"])
ok("report carries growth", r_hi["growth"] is not None and r_hi["growth"]["levels"] == 3)
r_empty = D.debt_report()
ok("report all-None safe", r_empty["verdict"] == "insufficient data" and r_empty["tilt"] is None)

print("\nALL debt_engine PASS" if not fail else "\nSOME debt_engine TESTS FAILED")
sys.exit(1 if fail else 0)
