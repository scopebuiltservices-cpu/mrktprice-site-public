"""Locks the yfinance CIRCUIT BREAKER in price_source.PriceSource — the fix for the live-deploy blocker where
per-ticker Yahoo fetches hang ~10s each (curl 28) on GitHub-Actions IPs and, across a ~700-name universe,
blow the build's ~20-min budget so the 'refusing to publish synthetic data' guard trips and marketmap.json
goes stale. The breaker disables yfinance after N consecutive failures, bounding wasted time to ~N x 10s.
Dependency-injected mocks — no network."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import price_source as PS

fail = 0


def ok(name, cond, extra=""):
    global fail
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        fail = 1


class _HangHist:
    def history(self, *a, **k):
        raise RuntimeError("Failed to perform, curl: (28) Operation timed out")  # simulate Yahoo hang


class _HangYF:
    def Ticker(self, sym):
        return _HangHist()


class _GoodFMP:
    def have_key(self):
        return True

    def eod_ohlcv(self, sym, sess=None, min_rows=10):
        return [["2026-01-%02d" % (i + 1), 0, 101.0, 99.0, 100.0, 1000] for i in range(12)]


# 1) yfinance-only, always hanging: breaker must trip and disable yf
ps = PS.PriceSource(fmp=None, yf=_HangYF())
res = [ps.get("T%d" % i) for i in range(10)]
ok("all yf-hang gets return None (miss)", all(r is None for r in res))
ok("breaker tripped", ps.health.get("yfTripped") is True)
ok("yf disabled after trip", ps.yf is None)
ok("trip at threshold (default 5)", ps._yf_break == 5)

# 2) FMP-primary healthy: yfinance is never touched; breaker stays untripped
ps2 = PS.PriceSource(fmp=_GoodFMP(), yf=_HangYF())
g = ps2.get("AAPL")
ok("FMP primary returns rows", g is not None and g["src"] == "fmp" and len(g["cl"]) == 12)
ok("breaker untripped when FMP healthy", ps2.health.get("yfTripped") is False)
ok("FMP health counted", ps2.health["fmp"] == 1 and ps2.health["yf"] == 0)

# 3) success on yf resets the consecutive-fail counter (breaker only trips on a *run* of failures)
class _FlakyYF:
    def __init__(self):
        self.n = 0
        import types
        self._df = None

    def Ticker(self, sym):
        outer = self
        class _H:
            def history(self, *a, **k):
                outer.n += 1
                raise RuntimeError("curl 28")
        return _H()

ps3 = PS.PriceSource(fmp=None, yf=_FlakyYF())
ps3._yf_break = 3
for i in range(2):
    ps3.get("X%d" % i)
ok("no trip below threshold", ps3.health.get("yfTripped") is False and ps3._yf_fail == 2)

print("\nALL price_source breaker PASS" if not fail else "\nSOME price_source breaker TESTS FAILED")
sys.exit(1 if fail else 0)
