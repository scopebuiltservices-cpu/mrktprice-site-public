"""Offline parser tests for fmp_float.py (no network) — covers FMP shares-float field-name variants."""
import fmp_float as FF

def test_floatshares_present():
    p=[{"symbol":"AAPL","date":"2026-06-01","floatShares":1.46e10,"outstandingShares":1.49e10,"freeFloat":97.9}]
    d=FF.parse_float(p); assert abs(d["floatShares"]-1.46e10)<1 and abs(d["outShares"]-1.49e10)<1, d

def test_derive_from_pct():
    # floatShares absent -> derive from freeFloat% * outstanding
    p=[{"symbol":"XYZ","outstandingShares":1.0e8,"freeFloat":60.0}]
    d=FF.parse_float(p); assert abs(d["floatShares"]-6.0e7)<1, d

def test_alt_field_names():
    p=[{"symbol":"Q","float":5.0e7,"sharesOutstanding":8.0e7}]
    d=FF.parse_float(p); assert abs(d["floatShares"]-5.0e7)<1 and abs(d["outShares"]-8.0e7)<1, d

def test_empty_none():
    assert FF.parse_float([]) is None and FF.parse_float({}) is None

if __name__=="__main__":
    test_floatshares_present(); test_derive_from_pct(); test_alt_field_names(); test_empty_none()
    print("test_fmp_float: 4/4 PASS")
