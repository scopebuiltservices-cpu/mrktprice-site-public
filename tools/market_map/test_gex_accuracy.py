"""Regression tests for the GEX accuracy fixes: per-contract time-to-expiry and IV sanity."""
import options_gex as og

def t_per_contract_T():
    spot=100.0
    near=[{"strike":100,"type":"C","oi":1000,"iv":0.25,"dte":7}]
    far =[{"strike":100,"type":"C","oi":1000,"iv":0.25,"dte":365}]
    gn=og.compute_gex(near,spot,30); gf=og.compute_gex(far,spot,30)
    assert abs(gn["gexTotal"])>abs(gf["gexTotal"])*3, "short-dated ATM gamma must dominate long-dated"
    assert gn["frontDays"]==7 and gf["frontDays"]==365, "frontDays must reflect each contract's real expiry"
    print("  PASS  per-contract maturity (near %d vs far %d, ratio %.1fx)"%(
        gn["gexTotal"],gf["gexTotal"],abs(gn["gexTotal"])/max(abs(gf["gexTotal"]),1)))

def t_iv_sanity():
    spot=100.0
    poll=[{"strike":100,"type":"C","oi":500,"iv":0.22,"dte":30},
          {"strike":100,"type":"P","oi":500,"iv":0.23,"dte":30},
          {"strike":20, "type":"C","oi":800,"iv":2.88,"dte":30}]   # garbage deep-ITM IV
    gp=og.compute_gex(poll,spot,30)
    assert gp["atmIV"] is not None and gp["atmIV"]<40, "ATM IV must ignore the 288%% deep-ITM quote"
    print("  PASS  IV sanity bound keeps ATM-IV clean (%.0f%%)"%gp["atmIV"])

def t_exp_uses_front_expiry():
    spot=100.0
    ch=[{"strike":100,"type":"C","oi":300,"iv":0.20,"dte":14},
        {"strike":100,"type":"C","oi":300,"iv":0.20,"dte":200}]
    g=og.compute_gex(ch,spot,30)
    assert g["frontDays"]==14, "expected move must anchor on the nearest expiry"
    print("  PASS  expected-move anchors on front expiry (%dd)"%g["frontDays"])

def t_empty_and_degenerate():
    assert og.compute_gex([],100,30) is None
    assert og.compute_gex([{"strike":0,"type":"C","oi":1,"iv":0.2}],100,30) is None
    print("  PASS  empty / degenerate inputs handled")

if __name__=="__main__":
    t_per_contract_T(); t_iv_sanity(); t_exp_uses_front_expiry(); t_empty_and_degenerate()
    print("\nALL GEX-ACCURACY TESTS PASS")
