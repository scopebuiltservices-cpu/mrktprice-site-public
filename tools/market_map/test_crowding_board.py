"""Planted-structure tests for crowding_board.py (days-to-cover + crowding penalty + real-float denom)."""
import crowding_board as CB

def test_crowded_smallcap_flags():
    rows = [["2026-06-%02d" % (d + 1), 12.0, 800000] for d in range(25)]
    cr = CB.crowding_for({"fails": 4_000_000, "prevFails": 3_000_000, "level": "elevated", "trend": "rising"}, rows, 600_000_000)
    assert cr["dtc"] >= 4 and cr["squeeze"] and cr["pen"] > 0, cr

def test_liquid_megacap_quiet():
    rows = [["2026-06-%02d" % (d + 1), 283.0, 65_000_000] for d in range(25)]
    cr = CB.crowding_for({"fails": 388_949, "prevFails": 194_134, "level": "moderate", "trend": "rising"}, rows, 4_167_000_000_000)
    assert cr["dtc"] < 0.1 and not cr["squeeze"] and cr["pen"] < 0.01, cr

def test_no_short_returns_none():
    assert CB.crowding_for(None, [], 1e9) is None
    assert CB.crowding_for({"fails": 0}, [], 1e9) is None

def test_real_float_denominator_preferred():
    # real free float (30M) is used over the mcap/price proxy -> higher, correct SI%, src tagged +float
    rows = [["2026-06-%02d" % (d + 1), 12.0, 800000] for d in range(25)]
    cr = CB.crowding_for({"fails": 4_000_000, "level": "elevated", "trend": "rising"}, rows, 600_000_000, float_shares=30_000_000)
    assert abs(cr["siPct"] - (4_000_000 / 30_000_000 * 100)) < 1e-3 and cr["src"].endswith("+float"), cr

if __name__ == "__main__":
    test_crowded_smallcap_flags(); test_liquid_megacap_quiet(); test_no_short_returns_none(); test_real_float_denominator_preferred()
    print("test_crowding_board: 4/4 PASS")
