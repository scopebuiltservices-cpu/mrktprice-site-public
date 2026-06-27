#!/usr/bin/env python3
"""Tests for warehouse.py (quarterly-timeline normalized warehouse + basis flags + manifest).
Run: python3 test_warehouse.py"""
import os, sys, tempfile, shutil, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import warehouse as wh
F=[]
def ok(n,c,d=""):
    print(("  PASS  " if c else "  FAIL  ")+n+("" if c else "  -> "+str(d)))
    if not c: F.append(n)

dates=["2025-01-02","2025-01-03","2025-01-06","2025-01-07","2025-01-08"]
raw=[100,101,102,103,104]
df=wh.normalize_prices("aapl",dates,raw,divs={2:1.0})
ok("three distinct bases kept as separate columns", set(["raw_close","split_adj_close","total_return"]).issubset(df.columns))
ok("raw basis unchanged (not overwritten)", list(df["raw_close"])==raw)
ok("total_return includes the dividend (TR last > raw-only TR last)", df["total_return"].iloc[-1] > 100.0*raw[-1]/raw[0], df["total_return"].iloc[-1])
ok("basis flags attached + documented", df.attrs["basis_flags"]["total_return"]["dividends"] is True)
ok("ticker uppercased", df["ticker"].iloc[0]=="AAPL")

ok("deterministic file name matches spec convention",
   wh.deterministic_name("AAPL","NASDAQ","2025-01-01","2025-12-31","2026-06-27","price_panel","parquet")
   =="AAPL_NASDAQ_2025-01-01_2025-12-31_2026-06-27_price_panel.parquet")

tmp=tempfile.mkdtemp(prefix="wh_")
try:
    res=wh.write_table(df,tmp,"AAPL","NASDAQ","2025-01-02","2025-01-08","2026-06-27","prices")
    ok("table written (parquet or csv fallback)", os.path.exists(res["path"]), res)
    ok("write reports format + rows + sha16", res["rows"]==5 and len(res["sha16"])==16, res)
    back=wh.read_table(res["path"])
    ok("round-trip preserves rows + raw basis", len(back)==5 and list(back["raw_close"])==raw)
    man=wh.manifest({"ticker":"AAPL","basis":"total_return"},[res],asof="2026-06-27",source="test")
    mp=wh.write_manifest(man,tmp,"AAPL","NASDAQ","2025-01-02","2025-01-08","2026-06-27")
    m=json.load(open(mp))
    ok("manifest carries basis flags + default basis", m["default_basis"]=="total_return" and "raw_close" in m["basis_flags"])
    ok("manifest links table format + hash (auditability)", m["tables"][0]["sha16"]==res["sha16"])
    ok("manifest filename deterministic", mp.endswith("AAPL_NASDAQ_2025-01-02_2025-01-08_2026-06-27_manifest.json"))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n"+("ALL WAREHOUSE TESTS PASSED" if not F else "%d FAILED: %s"%(len(F),F)))
raise SystemExit(1 if F else 0)
