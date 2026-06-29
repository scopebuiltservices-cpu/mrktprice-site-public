"""Offline tests for sector_seed.apply_authoritative (in-build sector override)."""
import sector_seed as SS

def test_override_preserves_seed():
    names = [{"t": "JPM", "sec": "Technology"}, {"t": "AAPL", "sec": "Technology"}, {"t": "USO", "sec": "Commodity"}]
    prof = {"JPM": {"sector": "Financials"}, "AAPL": {"sector": "Technology"}, "USO": {"sector": None}}
    done = SS.apply_authoritative(names, prof)
    by = {n["t"]: n for n in names}
    assert done == 1                                        # only JPM changed
    assert by["JPM"]["sec"] == "Financials" and by["JPM"]["secSeed"] == "Technology"
    assert by["AAPL"]["sec"] == "Technology" and by["AAPL"]["secSeed"] == "Technology"  # seed preserved even when unchanged
    assert by["USO"]["sec"] == "Commodity" and by["USO"].get("secSeed") is None         # ETF untouched

def test_empty_profile_noop():
    names = [{"t": "X", "sec": "Energy"}]
    assert SS.apply_authoritative(names, {}) == 0 and names[0]["sec"] == "Energy"

if __name__ == "__main__":
    test_override_preserves_seed(); test_empty_profile_noop()
    print("test_sector_seed: 2/2 PASS")
