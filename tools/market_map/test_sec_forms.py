"""Offline tests: parse a planted EDGAR submissions JSON -> correct event stream + severities + summary."""
import sys, os, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sec_forms as S

SUB = {"filings": {"recent": {
    "form":            ["8-K", "4", "SC 13D", "8-K", "10-Q", "SC 13G/A", "3", "DEF 14A"],
    "filingDate":      ["2026-06-20", "2026-06-18", "2026-06-10", "2026-05-30", "2026-05-01", "2026-04-15", "2026-03-02", "2026-02-01"],
    "items":           ["2.02,9.01", "", "", "4.02", "", "", "", ""],
    "accessionNumber": ["a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8"],
}}}

def test_parse_filters_and_severity():
    ev = S.events_from_submissions(SUB, since=400, today=dt.date(2026, 6, 28))
    forms = [e["form"] for e in ev]
    assert "10-Q" not in forms and "DEF 14A" not in forms        # untracked dropped
    assert forms[0] == "8-K" and ev[0]["date"] == "2026-06-20"   # newest first
    # 8-K 2.02 severity = 0.60 (max over 2.02/9.01; 9.01 unknown->0.25)
    assert abs(ev[0]["sev"] - 0.60) < 1e-9, ev[0]["sev"]
    # the restatement 8-K (4.02) scored 0.95
    k = next(e for e in ev if e["items"] == ["4.02"]); assert abs(k["sev"] - 0.95) < 1e-9
    # 13D base severity 0.85
    d = next(e for e in ev if e["form"] == "SC 13D"); assert abs(d["sev"] - 0.85) < 1e-9
    print("  PASS  parse: tracked-only, newest-first, 8-K item severity (2.02=0.60, 4.02=0.95), 13D=0.85")

def test_summary_counts_and_intensity():
    ev = S.events_from_submissions(SUB, since=400, today=dt.date(2026, 6, 28))
    sm = S.summarize(ev, today=dt.date(2026, 6, 28))
    assert sm["n8k"] == 2 and sm["n13d"] == 1 and sm["n13g"] == 1 and sm["nins"] == 2, sm
    assert sm["intensity"] > 0 and sm["last"]["form"] == "8-K"
    print("  PASS  summary: counts {8K:%d,13D:%d,13G:%d,ins:%d}, intensity=%.3f, last=8-K"
          % (sm["n8k"], sm["n13d"], sm["n13g"], sm["nins"], sm["intensity"]))

def test_items_parser():
    assert S._items_list("Item 2.02, Item 9.01") == ["2.02", "9.01"]
    assert S._items_list("") == []
    print("  PASS  8-K items parser handles 'Item X.YY' formatting")

def test_empty():
    sm = S.summarize([], today=dt.date(2026, 6, 28))
    assert sm["intensity"] == 0.0 and sm["last"] is None
    print("  PASS  empty event stream -> zero intensity, no false events")

if __name__ == "__main__":
    test_parse_filters_and_severity(); test_summary_counts_and_intensity(); test_items_parser(); test_empty()
    print("\nALL SEC_FORMS TESTS PASSED")
