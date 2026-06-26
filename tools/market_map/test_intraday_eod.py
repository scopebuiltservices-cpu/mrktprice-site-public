#!/usr/bin/env python3
"""Unit tests for intraday_eod.py against planted structure. Run: python3 test_intraday_eod.py"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intraday_eod as ie

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# 1) volume profile: normalized, U-shaped
p = ie.tod_volume_profile(26)
ok("profile sums to 1", abs(sum(p) - 1.0) < 1e-9)
ok("profile is U-shaped (open & close > midday)", p[0] > p[13] and p[-1] > p[13])

# 2) volume_pace: if cum == typical-by-now, projected EOD == avg daily volume
avg = 1_000_000.0
half = 13
frac = sum(p[:half])
cum = avg * frac                                   # exactly a typical day's pace
vp = ie.volume_pace(cum, half, 26, avg)
ok("projected EOD volume recovers the typical day", abs(vp["projEodVol"] - avg) < 1.0, vp["projEodVol"])
ok("pace == 1.0 on a typical day", abs(vp["pace"] - 1.0) < 1e-6, vp["pace"])
vp2 = ie.volume_pace(cum * 1.5, half, 26, avg)
ok("pace > 1 when running hot", vp2["pace"] > 1.4)

# 3) close projection: constant drift -> exact; band widens with horizon
pr = ie.eod_close_projection(math.log(100.0), 0.001, 0.002, 10, open_px=99.0)
ok("close = exp(p + drift*rem)", abs(pr["close"] - math.exp(math.log(100.0) + 0.01)) < 1e-9)
ok("band brackets close", pr["lo"] < pr["close"] < pr["hi"])
ok("projected day % computed vs open", abs(pr["pctClose"] - (pr["close"] / 99.0 - 1.0)) < 1e-12)
pr_near = ie.eod_close_projection(math.log(100.0), 0.001, 0.002, 2)
ok("band narrows as close approaches", (pr_near["hi"] - pr_near["lo"]) < (pr["hi"] - pr["lo"]))

# 4) realized vol
rv = ie.intraday_rv([0.01, -0.008, 0.012, -0.005])
ok("rv positive + annualized", rv["rvDay"] > 0 and rv["rvAnn"] > rv["rvDay"])

# 5) end-to-end outlook: planted positive drift, 13 bars done -> bullish EOD, vol projects up
bars = []
p0 = math.log(100.0); price = 100.0
for k in range(13):
    r = 0.002
    p0 += r; price = math.exp(p0)
    bars.append({"bucket": k, "ret": r, "vol": avg * p[k], "p": p0, "price": price})
ctx = {"avgDailyVol": avg, "dailyHV": 0.20, "openPx": 100.0, "totalBuckets": 26}
o = ie.eod_outlook(bars, ctx)
ok("outlook returns", o is not None)
ok("13/26 buckets elapsed, 13 remaining", o["elapsed"] == 13 and o["remaining"] == 13)
ok("positive drift -> projected close above now", o["projClose"] > o["priceNow"])
ok("projected day % positive", o["projPct"] > 0)
ok("EOD volume projects to ~full day", abs(o["projEodVol"] - avg) / avg < 0.05, o["projEodVol"])
ok("projected RVOL ~1x on a typical-volume day", abs(o["projRVOL"] - 1.0) < 0.1, o["projRVOL"])
ok("RV vs HV ratio present", o["rvVsHv"] is not None)
ok("no look-ahead (uses only elapsed bars)", ie.eod_outlook(bars[:5], ctx)["elapsed"] == 5)

print("\n" + ("ALL INTRADAY-EOD TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
