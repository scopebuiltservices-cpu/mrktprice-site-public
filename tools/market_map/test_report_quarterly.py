import report_engine as RE
import report_render as RR

N = {
  "t":"AAPL","n":"Apple","sec":"Technology","idx":["S"],
  "earn":{"q":[
    {"d":"2025-07-31","a":1.57,"e":1.44,"q":3,"y":2025,"s":9.0},
    {"d":"2025-10-30","a":1.85,"e":1.73,"q":4,"y":2025,"s":6.9},
    {"d":"2026-01-29","a":2.85,"e":2.67,"q":1,"y":2026,"s":6.7},
    {"d":"2026-04-30","a":2.01,"e":1.95,"q":2,"y":2026,"s":3.1}],
    "next":{"d":"2026-07-30","a":None,"e":1.88,"q":3,"y":2026,"s":None},
    "estCons":{"eps":8.75,"period":"2026-09-27","rev":None}},
  "val":{"pe":34.2,"fpe":29.5,"peg":1.18,"evb":26.3,"peSec":27.1,"evSec":25.2,
         "epsg":0.218,"revg":0.166,"overall":"supported","reason":"PEG 1.18 fair"},
  "dcf":155.96,"dcfGap":0.8196,"fcfY":2.43,"tgtUpside":0.1523,
  "ptgt":{"tgt":327.0,"high":400.0,"low":253.0},
  "vol":24.3,"ivol":27.8,"pvol":27.7,"atr":3.25,"vr":1.08,"jump":0.1,"hl":34.5,"regime":"random-walk",
  "ema21d":-3.61,"ema21sig":-0.53,"ema21sl":-1.35,
  "opt":{"pw":255.0,"cw":280.0,"gex":267.5},
  "flow":{"net1m":-0.083,"net3m":0.142,"in":181222708686,"out":214169867761},
  "mfi":50.9,"brk":0,"odds":{"beat":0.8},"alerts":["likely beat 80%","insider selling"],
  "ret":{"1m":-9.19,"3m":12.88,"12m":41.69},"secRel":1.0,
}
MM={"names":[N],"asof":"2026-06-28"}

def test_quarterly():
    q=RE.quarterly_block(N)
    assert len(q["history"])==4
    assert q["history"][0]["label"]=="Q3 2025"
    assert q["history"][-1]["label"]=="Q2 2026"            # sorted by date
    assert all(r["beat"] for r in q["history"])            # all 4 beat
    assert q["nReports"]==4 and q["beatRate"]==100.0
    assert q["nextExpected"]["label"]=="Q3 2026" and q["nextExpected"]["estEPS"]==1.88
    assert q["nextExpected"].get("actualEPS") is None      # expected only, not yet reported
    assert q["fwdConsensus"]["eps"]==8.75
    print("quarterly: expected-vs-actual + next-expected + consensus OK")

def test_quarterly_miss():
    n2=dict(N); n2["earn"]={"q":[{"d":"2026-01-29","a":1.0,"e":1.2,"q":1,"y":2026,"s":-16.7}]}
    q=RE.quarterly_block(n2)
    assert q["history"][0]["beat"] is False and q["beatRate"]==0.0
    print("quarterly: miss correctly graded")

def test_multiples():
    m=RE.multiples_block(N)
    assert m["pe"]==34.2 and m["fpe"]==29.5 and m["peg"]==1.18
    assert m["evEbitda"]==26.3 and m["peSector"]==27.1
    assert m["dcfFair"]==155.96 and m["dcfGapPct"]==82.0
    assert m["target"]["low"]==253.0 and m["target"]["high"]==400.0
    assert m["targetUpsidePct"]==15.2 and m["verdict"]=="supported"
    print("multiples: P/E/PEG/EV-EBITDA + DCF + target range + verdict OK")

def test_vol_range():
    v=RE.vol_range_block(N)
    assert v["realizedVolPct"]==24.3 and v["impliedVolPct"]==27.8 and v["parkinsonVolPct"]==27.7
    assert v["atr"]==3.25 and v["varianceRatio"]==1.08 and v["regime"]=="random-walk"
    assert v["jumpRatio"]==0.1 and v["halfLifeDays"]==34.5
    assert v["ema21DistPct"]==-3.61 and v["ema21Sigma"]==-0.53
    assert v["rangeOptions"]["support"]==255.0 and v["rangeOptions"]["resistance"]==280.0
    assert v["rangeAnalyst"]["low"]==253.0 and v["rangeAnalyst"]["high"]==400.0
    print("vol/range: realized/implied/parkinson/ATR + regime + option+analyst range OK")

def test_vol_regime_derived():
    n2=dict(N); n2.pop("regime"); n2["vr"]=1.30
    assert RE.vol_range_block(n2)["regime"]=="trending"
    n3=dict(N); n3.pop("regime"); n3["vr"]=0.70
    assert RE.vol_range_block(n3)["regime"]=="mean-reverting"
    print("vol/range: variance-ratio regime fallback OK")

def test_volume_triggers():
    vt=RE.volume_triggers_block(N)
    assert vt["flowNet1mPct"]==-8.3 and vt["flowNet3mPct"]==14.2
    assert vt["inflowSharePct"]==46.0           # 181.2/(181.2+214.2)
    assert vt["mfi"]==50.9 and vt["breakout"] is False
    assert vt["beatProb"]==80.0
    assert "likely beat 80%" in vt["alerts"]
    print("volume triggers: flow net + inflow share + MFI + beat-prob + alerts OK")

def test_render_company_has_sections():
    c=RE.company_report(MM,"AAPL")
    html=RR.render_company(c)
    for needle in ("Quarterly reports","Est EPS","Actual EPS","Multiples","EV / EBITDA",
                   "Volatility &amp; trading range","Regime","Volume / flow triggers","MFI","beat"):
        assert needle in html, "missing: "+needle
    assert "Q3 2025" in html and "Q3 2026" in html   # history + upcoming both rendered
    print("render: all 4 new company sections present in HTML")

if __name__=="__main__":
    for fn in sorted(k for k in dict(globals()) if k.startswith("test_")):
        globals()[fn]()
    print("ALL test_report_quarterly PASS")
