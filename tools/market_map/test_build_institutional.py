"""Offline tests for build_institutional: (1) the period filename labels match the live SEC convention
(rolling 3-month month-range, post-Mar-2024); (2) INFOTABLE aggregation + universe match + QoQ flow."""
import sys, os, io, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_institutional as B

def test_period_labels_match_sec():
    # As of 2026-06-28 the two newest PUBLISHED periods on sec.gov are:
    #   01mar2026-31may2026_form13f.zip  and  01dec2025-28feb2026_form13f.zip
    pw = B.period_windows(dt.date(2026, 6, 28))
    labels = [lab for _e, lab in pw]
    assert labels[0] == "01mar2026-31may2026", labels[0]
    assert labels[1] == "01dec2025-28feb2026", labels[1]
    # leap-year Feb end honored (2024 had 29 Feb)
    pw24 = B.period_windows(dt.date(2024, 6, 28))
    assert any(lab == "01dec2023-29feb2024" for _e, lab in pw24), [l for _e,l in pw24]
    # nothing from the future leaks in (e.g. a period ending after today)
    assert all((dt.date(2026,6,28)-e).days >= 20 for e,_l in pw)
    print("  PASS  period labels match live SEC convention (01mar2026-31may2026, 01dec2025-28feb2026; leap-Feb ok)")

def test_url_built():
    # download_quarter builds {BASE}/{label}_form13f.zip — confirm the full URL matches the SEC path
    lab = "01mar2026-31may2026"
    url = f"{B.BASE}/{lab}_form13f.zip"
    assert url == "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/01mar2026-31may2026_form13f.zip", url
    print("  PASS  download URL matches the SEC data-set path exactly")

def test_aggregate_match_flow():
    # planted INFOTABLE.tsv (tab-delimited) for two managers holding AAPL + one holding MSFT
    hdr = "ACCESSION_NUMBER\tNAMEOFISSUER\tCUSIP\tVALUE\tSSHPRNAMT\tSSHPRNAMTTYPE\tPUTCALL\n"
    cur = hdr + "\n".join([
        "ACC1\tAPPLE INC\t037833100\t1000000\t5000\tSH\t",
        "ACC2\tAPPLE INC\t037833100\t2000000\t9000\tSH\t",
        "ACC3\tMICROSOFT CORP\t594918104\t3000000\t4000\tSH\t",
        "ACC4\tAPPLE INC\t037833100\t9999\t100\tSH\tCALL",   # option -> excluded
    ]) + "\n"
    prev = hdr + "\n".join([
        "ACC9\tAPPLE INC\t037833100\t800000\t10000\tSH\t",   # prev AAPL 10000 sh -> curr 14000 = +40% accumulation
        "ACC8\tMICROSOFT CORP\t594918104\t3000000\t5000\tSH\t",  # prev MSFT 5000 -> curr 4000 = -20% distribution
    ]) + "\n"
    ac = B.aggregate_infotable(io.StringIO(cur))
    ap = B.aggregate_infotable(io.StringIO(prev))
    assert ac["037833100"]["shares"] == 14000 and ac["037833100"]["holders"] == 2, ac["037833100"]
    uni = [("AAPL", "Apple Inc"), ("MSFT", "Microsoft Corp")]
    cur_m = B.match_universe(ac, uni); prev_m = B.match_universe(ap, uni)
    assert set(cur_m) == {"AAPL", "MSFT"}, list(cur_m)
    flow = B.institutional_flow(cur_m, prev_m)
    assert flow["AAPL"]["verdict"] == "accumulation" and flow["AAPL"]["dShares"] == 40.0, flow["AAPL"]
    assert flow["MSFT"]["verdict"] == "distribution" and flow["MSFT"]["dShares"] == -20.0, flow["MSFT"]
    print("  PASS  INFOTABLE aggregate + CUSIP/name match + QoQ flow (AAPL +40%% accum, MSFT -20%% distrib; options excluded)")

if __name__ == "__main__":
    test_period_labels_match_sec(); test_url_built(); test_aggregate_match_flow()
    print("\nALL BUILD_INSTITUTIONAL TESTS PASSED")
