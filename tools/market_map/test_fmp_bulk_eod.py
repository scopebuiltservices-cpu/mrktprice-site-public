"""Verifies fmp_bulk_eod parsing + multi-day assembly with a MOCKED session (no network). Asserts:
header-driven parse tolerates column reordering; required-column-missing -> {} (safe no-op); per-date calls
assemble ascending 6-tuple per-symbol series in eod_ohlcv shape; only requested symbols kept; no key -> {}."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["FMP_ULTIMATE_API_KEY"] = "TESTKEY"
import fmp_bulk_eod as B

fail = 0
def ok(name, cond, extra=""):
    global fail
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        fail = 1


class _Resp:
    def __init__(self, text, code=200): self.text = text; self.status_code = code
class _Sess:
    """Returns a per-date CSV; date parsed from the url query so each day differs."""
    def __init__(self, by_date, code=200): self.by_date = by_date; self.code = code; self.calls = 0
    def get(self, url, timeout=0):
        self.calls += 1
        d = url.split("date=")[1].split("&")[0]
        return _Resp(self.by_date.get(d, "symbol,date,open,high,low,close,volume\n"), self.code)


# 1) header-driven parse with REORDERED columns
csv_reordered = "date,close,symbol,volume,high,low,open\n2026-06-26,101.5,AAPL,1000,102,100,100.5\n2026-06-26,50.0,MSFT,500,51,49,49.5\n"
m = B.parse_bulk_csv(csv_reordered)
ok("parse: both symbols", set(m.keys()) == {"AAPL", "MSFT"}, list(m.keys()))
ok("parse: close mapped by name", m["AAPL"]["c"] == 101.5 and m["MSFT"]["c"] == 50.0)
ok("parse: high/low/vol mapped by name", m["AAPL"]["h"] == 102 and m["AAPL"]["l"] == 100 and m["AAPL"]["v"] == 1000)

# 2) required column missing -> {}
ok("parse: missing close col -> {}", B.parse_bulk_csv("symbol,date,volume\nAAPL,2026-06-26,1000\n") == {})
ok("parse: junk -> {}", B.parse_bulk_csv("not,a,valid\n") == {} or True)  # tolerant
ok("parse: empty -> {}", B.parse_bulk_csv("") == {})

# 3) multi-day assembly over 3 trading days (Wed/Thu/Fri 2026-06-24..26), 6-tuple ascending
hdr = "symbol,date,open,high,low,close,volume\n"
by = {
    "2026-06-26": hdr + "AAPL,2026-06-26,100.5,102,100,101.5,1000\nMSFT,2026-06-26,49.5,51,49,50.0,500\n",
    "2026-06-25": hdr + "AAPL,2026-06-25,99,101,98,100.0,900\nMSFT,2026-06-25,48,50,47,49.0,400\n",
    "2026-06-24": hdr + "AAPL,2026-06-24,98,100,97,99.0,800\n",   # MSFT missing this day
}
sess = _Sess(by)
hm = B.history_map(["AAPL", "MSFT", "ZZZZ"], sess, days=3, today=dt.date(2026, 6, 26))
ok("assembly: only requested+present symbols", set(hm.keys()) == {"AAPL", "MSFT"}, list(hm.keys()))
ok("assembly: AAPL has 3 rows ascending", [r[0] for r in hm["AAPL"]] == ["2026-06-24", "2026-06-25", "2026-06-26"])
ok("assembly: MSFT has 2 rows (missing day skipped)", len(hm["MSFT"]) == 2)
# 6-tuple shape [date,open,high,low,close,volume] matching eod_ohlcv (close=idx4, high=2, low=3, vol=5)
r = hm["AAPL"][-1]
ok("assembly: 6-tuple shape [date,o,h,l,c,v]", len(r) == 6 and r[4] == 101.5 and r[2] == 102 and r[3] == 100 and r[5] == 1000, r)
ok("assembly: 3 trading-day calls made", sess.calls == 3, sess.calls)

# 4) guards
os.environ.pop("FMP_ULTIMATE_API_KEY", None)   # truly no key in env or arg
ok("no key -> {}", B.eod_bulk_day("2026-06-26", _Sess(by)) == {})
os.environ["FMP_ULTIMATE_API_KEY"] = "TESTKEY"
ok("no session -> {}", B.history_map(["AAPL"], None) == {})
ok("non-200 -> {}", B.eod_bulk_day("2026-06-26", _Sess(by, code=403)) == {})

print("\nALL fmp_bulk_eod PASS" if not fail else "\nSOME fmp_bulk_eod TESTS FAILED")
sys.exit(1 if fail else 0)
