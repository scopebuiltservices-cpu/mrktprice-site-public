"""Planted parser tests: real Ken French CSV layout (prose preamble, header, daily percent rows,
annual-section cutoff, missing-value sentinel), FF5 + Momentum merge, round-trip cache."""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import factor_returns as F

FF5 = """This file was created by CMPT_ME_BEME_RETS using the 202506 CRSP database.

,Mkt-RF,SMB,HML,RMW,CMA,RF
19630701,  0.10, -0.41, -0.97,  0.68, -1.18,  0.012
19630702, -0.50,  0.20,  0.30, -0.10,  0.05,  0.012
19630703,  1.20, -0.30, -0.20,  0.40, -0.50,  0.012

  Annual Factors: January-December
,Mkt-RF,SMB,HML,RMW,CMA,RF
1964,  16.30,  3.00,  1.00,  2.00, -1.00,  3.54
"""

MOM = """This file was created ...

,Mom
19630701,   0.55
19630702,  -0.22
19630703,   0.88

  Annual Factors:
,Mom
1964,  5.0
"""

def test_parse_daily_only():
    t = F.parse_ff_csv(FF5)
    assert set(t.keys()) == {19630701, 19630702, 19630703}, list(t.keys())
    # percent -> fraction
    assert abs(t[19630701]["MktRF"] - 0.0010) < 1e-12, t[19630701]["MktRF"]
    assert abs(t[19630702]["SMB"] - 0.0020) < 1e-12
    assert abs(t[19630701]["RF"] - 0.00012) < 1e-12
    assert "Mkt-RF" not in t[19630701] and "MktRF" in t[19630701]  # normalized
    print("  PASS  FF5 parse: 3 daily rows, percent->fraction, annual section excluded")

def test_parse_momentum():
    m = F.parse_ff_csv(MOM)
    assert set(m.keys()) == {19630701, 19630702, 19630703}
    assert abs(m[19630702]["Mom"] + 0.0022) < 1e-12
    print("  PASS  Momentum parse: 3 rows, header ',Mom' detected")

def test_merge_and_roundtrip():
    ff5 = F.parse_ff_csv(FF5); mom = F.parse_ff_csv(MOM)
    rows = F.merge_factor_tables(ff5, mom)
    assert len(rows) == 3 and rows[0]["date"] == 19630701
    assert abs(rows[0]["Mom"] - 0.0055) < 1e-12 and abs(rows[1]["Mom"] + 0.0022) < 1e-12
    tmp = tempfile.mkdtemp(); out = os.path.join(tmp, "data", "ff_factors.csv")
    F._write_cache(rows, out)
    back = F.load_factor_csv(out)
    assert len(back) == 3
    assert abs(back[0]["MktRF"] - 0.0010) < 1e-9 and abs(back[2]["RMW"] - 0.0040) < 1e-9
    assert abs(back[0]["RF"] - 0.00012) < 1e-9
    print("  PASS  merge FF5+Mom + write/read round-trip preserves fractions")

def test_missing_sentinel():
    txt = ",Mkt-RF,SMB,HML,RMW,CMA,RF\n19700101, -99.99, 0.10, 0.20, 0.30, 0.40, 0.01\n\n"
    t = F.parse_ff_csv(txt)
    assert t[19700101]["MktRF"] is None and abs(t[19700101]["SMB"] - 0.001) < 1e-12
    print("  PASS  -99.99 missing-value sentinel -> None")

if __name__ == "__main__":
    test_parse_daily_only(); test_parse_momentum(); test_merge_and_roundtrip(); test_missing_sentinel()
    print("\nALL FACTOR_RETURNS TESTS PASSED")
