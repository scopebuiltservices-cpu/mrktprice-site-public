#!/usr/bin/env python3
"""
universe_smoke.py — does this environment have the data sources to build the universe + rank correctly?

Probes every source the S&P500/Nasdaq/Dow/Russell universe, the macro/commodity betas, and the real-rate
curve depend on, and prints what is reachable. Read-only, fail-soft. Run:  python3 universe_smoke.py
Exit 0 if the CORE (constituents + prices + commodities + real rate) is reachable; 1 otherwise.
"""
import os, sys, json
try:
    import requests
except Exception:
    print("requests not installed"); sys.exit(1)
S = requests.Session(); S.headers.update({"User-Agent": "MrktPrice smoke/1.0"})
STABLE = "https://financialmodelingprep.com/stable"; V3 = "https://financialmodelingprep.com/api/v3"
def key():
    for k in ("FMP_ULTIMATE_API_KEY", "FMP_API_KEY", "FMP_UTIMATE_API_KEY"):
        v = os.environ.get(k)
        if v: return v
    return None
def get(url):
    try:
        r = S.get(url, timeout=30)
        return (r.status_code, r.json() if r.headers.get("content-type","").startswith("application/json") else r.text)
    except Exception as e:
        return (None, str(e)[:120])
def n(x): return len(x) if isinstance(x, list) else 0
K = key(); core_ok = True
print("=" * 64); print("MrktPrice universe data-source smoke test"); print("=" * 64)
print("FMP key present:", bool(K), "(env FMP_ULTIMATE_API_KEY)")
if K:
    for label, stable_ep, v3_ep, need in [
        ("S&P 500 constituents", "sp500-constituent", "sp500_constituent", True),
        ("Nasdaq-100 constituents", "nasdaq-constituent", "nasdaq_constituent", False),
        ("Dow 30 constituents", "dowjones-constituent", "dowjones_constituent", True),
    ]:
        sc, d = get("%s/%s?apikey=%s" % (STABLE, stable_ep, K))
        if n(d) == 0:
            sc, d = get("%s/%s?apikey=%s" % (V3, v3_ep, K))
        cnt = n(d); ok = cnt > 0
        print("  [%s] %-26s %s" % ("OK " if ok else "MISS", label, ("%d names" % cnt) if ok else "no data (plan may gate this endpoint)"))
        if need and not ok: core_ok = False
    sc, d = get("%s/company-screener?exchange=NASDAQ&isActivelyTrading=true&limit=50&apikey=%s" % (STABLE, K))
    ok = n(d) > 0; print("  [%s] %-26s %s" % ("OK " if ok else "MISS", "Nasdaq company-screener", ("%d (sample)" % n(d)) if ok else "no data"))
    if not ok: core_ok = False
    sc, d = get("%s/historical-price-eod/full?symbol=AAPL&apikey=%s" % (STABLE, K))
    ok = bool(d) and (n(d) > 0 or isinstance(d, dict))
    print("  [%s] %-26s %s" % ("OK " if ok else "MISS", "Per-name EOD prices", "AAPL history reachable" if ok else "no data"))
    if not ok: core_ok = False
    sc, d = get("%s/commodities-list?apikey=%s" % (STABLE, K))
    ok = n(d) > 0; print("  [%s] %-26s %s" % ("OK " if ok else "MISS", "Commodities list", ("%d commodities" % n(d)) if ok else "no data"))
    if not ok: core_ok = False
else:
    print("  -> FMP key NOT set. REQUIRED for constituents + prices + commodities."); core_ok = False
# Keyless: real-rate curve (FRED) + Russell 2000 (iShares IWM)
sc, d = get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10")
ok = sc == 200 and "DFII10" in str(d); print("  [%s] %-26s %s" % ("OK " if ok else "MISS", "Real-rate curve (FRED)", "DFII keyless CSV reachable" if ok else "unreachable"))
if not ok: core_ok = False
sc, d = get("https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund")
ok = sc == 200 and "Ticker" in str(d); print("  [%s] %-26s %s" % ("OK " if ok else "MISS", "Russell 2000 (iShares IWM)", "holdings CSV reachable" if ok else "unreachable (Russell falls back to yfinance)"))
print("-" * 64)
print("Optional enrichment (NOT needed for the rank): TWELVEDATA_API_KEY (IV),",
      "ALPACA keys (options/GEX), FINNHUB_API_KEY (earnings beats), EODHD_API_KEY (short interest).")
for k in ("TWELVEDATA_API_KEY", "ALPACA_API_KEY", "FINNHUB_API_KEY", "EODHD_API_KEY"):
    print("  %-22s %s" % (k + ":", "set" if os.environ.get(k) else "not set (enrichment tile blank; rank unaffected)"))
print("=" * 64)
print("CORE RANKING DATA:", "READY ✓" if core_ok else "INCOMPLETE ✗ (see MISS rows)")
sys.exit(0 if core_ok else 1)
