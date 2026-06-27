#!/usr/bin/env python3
"""Tests for report_bundle.py (quarterly-timeline HTML report). Run: python3 test_report_bundle.py"""
import os, sys, tempfile, shutil, random, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report_bundle as rb
F=[]
def ok(n,c,d=""):
    print(("  PASS  " if c else "  FAIL  ")+n+("" if c else "  -> "+str(d)))
    if not c: F.append(n)
rng=random.Random(5)

# synthetic aligned stock + benchmark, 400 trading days, with a dividend and a drawdown
N=400; dates=["2025-%02d-%02d"%(1+i//28,1+i%28) for i in range(N)]
bp=400.0; sp=100.0; bench=[]; close=[]
for i in range(N):
    mr=0.006*rng.gauss(0,1); sr=1.3*mr+0.004*rng.gauss(0,1)
    bp*=math.exp(mr); sp*=math.exp(sr)
    if i==250: sp*=0.82
    bench.append(bp); close.append(sp)
divs={120:0.5}
H=rb.build_report("AAPL", dates, close, bench_close=bench, divs=divs, earnings_idx=330, asof="2026-06-27")

ok("report is a full HTML document", H.startswith("<!doctype html") and H.rstrip().endswith("</html>"))
ok("contains the four required panels", all(s in H for s in ["KEY METRICS","NORMALIZED PERFORMANCE","DRAWDOWN"]))
ok("renders inline SVG (no external Plotly dependency)", "<svg" in H and "plotly" not in H.lower())
ok("states total-return basis (spec default)", "TOTAL RETURN" in H)
ok("includes beta + HAC t metric", "Beta" in H and "HAC t" in H)
ok("includes earnings CAR (event study ran)", "Latest earnings CAR" in H)
ok("max drawdown reflects the planted -18% shock", "Max drawdown" in H)
ok("ticker + as-of in header", "AAPL — Quarterly Timeline Report" in H and "2026-06-27" in H)

tmp=tempfile.mkdtemp(prefix="rb_")
try:
    p=rb.write_report(H, tmp, "AAPL","NASDAQ","2025-01-01","2025-12-31","2026-06-27")
    ok("writes deterministic filename", p.endswith("AAPL_NASDAQ_2025-01-01_2025-12-31_2026-06-27_report.html") and os.path.exists(p))
    ok("file non-trivial size", os.path.getsize(p)>1500, os.path.getsize(p))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# graceful degrade: no benchmark -> still builds, single line, no beta
H2=rb.build_report("MSFT", dates, close, asof="2026-06-27")
ok("builds without a benchmark (graceful)", "<svg" in H2 and "no benchmark" in H2)

print("\n"+("ALL REPORT-BUNDLE TESTS PASSED" if not F else "%d FAILED: %s"%(len(F),F)))
raise SystemExit(1 if F else 0)
