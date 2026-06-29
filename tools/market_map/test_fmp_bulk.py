"""Offline tests for fmp_bulk.py — CSV parse + defensive field pick + merge (no network)."""
import fmp_bulk as FB

RATIOS = "symbol,priceToEarningsRatioTTM,priceToBookRatioTTM,netProfitMarginTTM,debtToEquityRatioTTM,dividendYieldTTM,freeCashFlowYieldTTM\nAAPL,31.2,48.5,0.25,1.45,0.005,0.031\nMSFT,35.0,12.1,0.36,0.30,0.008,0.025\n"
METRICS = "symbol,returnOnEquityTTM\nAAPL,1.45\nMSFT,0.38\n"
TARGETS = "symbol,lastMonthAvgPriceTarget,lastMonthCount\nAAPL,305.5,28\nMSFT,520.0,30\n"
RATING  = "symbol,rating,ratingScore\nAAPL,A,4\nMSFT,A-,4\n"

def test_csv_parse():
    rows = FB.parse_bulk_csv(RATIOS)
    assert len(rows) == 2 and rows[0]["symbol"] == "AAPL"

def test_json_body_tolerated():
    rows = FB.parse_bulk_csv('[{"symbol":"X","peRatioTTM":"10"}]')
    assert rows and rows[0]["symbol"] == "X"

def test_merge_all_four():
    m = FB.merge(FB.parse_bulk_csv(RATIOS), FB.parse_bulk_csv(METRICS), FB.parse_bulk_csv(TARGETS), FB.parse_bulk_csv(RATING))
    a = m["AAPL"]
    assert abs(a["pe"] - 31.2) < 1e-9 and abs(a["roe"] - 1.45) < 1e-9
    assert abs(a["targetAvg"] - 305.5) < 1e-9 and a["rating"] == "A" and a["ratingScore"] == 4
    assert "FMP bulk" in a["src"]

def test_defensive_alt_field_names():
    # alternate field spellings still parse
    r = FB.parse_bulk_csv("symbol,peRatioTTM,pbRatioTTM\nQ,9.5,1.1\n")
    m = FB.merge(r, [], [], [])
    assert abs(m["Q"]["pe"] - 9.5) < 1e-9 and abs(m["Q"]["pb"] - 1.1) < 1e-9

if __name__ == "__main__":
    test_csv_parse(); test_json_body_tolerated(); test_merge_all_four(); test_defensive_alt_field_names()
    print("test_fmp_bulk: 4/4 PASS")
