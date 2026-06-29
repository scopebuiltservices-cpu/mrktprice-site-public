"""Offline tests for fmp_profile.py (CSV parse + FMP->canonical sector normalization)."""
import fmp_profile as FP

CSV = "symbol,sector,industry,exchangeShortName\nAAPL,Technology,Consumer Electronics,NASDAQ\nJPM,Financial Services,Banks,NYSE\nXOM,Energy,Oil & Gas,NYSE\nLIN,Basic Materials,Chemicals,NYSE\n"

def test_normalize_fmp_naming():
    assert FP.normalize_sector("Financial Services") == "Financials"
    assert FP.normalize_sector("Healthcare") == "Health Care"
    assert FP.normalize_sector("Consumer Cyclical") == "Consumer Disc."
    assert FP.normalize_sector("Basic Materials") == "Materials"
    assert FP.normalize_sector("Communication Services") == "Communication"
    assert FP.normalize_sector("Nonsense") is None

def test_rows_to_map_with_universe():
    m = FP.rows_to_map(FP.parse_profile_csv(CSV), universe={"AAPL", "JPM", "XOM"})
    assert "LIN" not in m                                   # filtered out (not in universe)
    assert m["JPM"]["sector"] == "Financials" and m["JPM"]["sectorRaw"] == "Financial Services"
    assert m["AAPL"]["sector"] == "Technology" and m["XOM"]["exchange"] == "NYSE"

if __name__ == "__main__":
    test_normalize_fmp_naming(); test_rows_to_map_with_universe()
    print("test_fmp_profile: 2/2 PASS")
