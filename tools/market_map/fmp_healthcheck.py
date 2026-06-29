#!/usr/bin/env python3
"""fmp_healthcheck.py — standalone, fast FMP Ultimate health probe across ALL endpoints the pipeline
uses, so the live status is known WITHOUT running a full nightly market-map build.

Probes /stable: quote, historical-price-eod/full, income-statement, analyst-estimates, earnings,
treasury-rates, commodities-list. Each call is classified (ok | invalid_key | rate_limited |
plan_or_endpoint | empty | http_error | network) via fmp_connector.classify. Emits fmp_health.json:
  {asof, key, overall, endpoints:[{name, ok, reason, status, ms, n}]}
overall = "ok" | "degraded" (price/fundamentals endpoint down) | "down" (key invalid / all fail) | "no_key".

Run on a 6-hourly schedule (see .github/workflows/fmp-health.yml). Network in CI; the per-endpoint logic
is offline-tested via an injectable fetcher. Research only."""
import argparse, json, os, sys, time, datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fmp_connector as FC

STABLE = "https://financialmodelingprep.com/stable"

# (name, path-template, critical?) — critical endpoints drive the degraded/down verdict
ENDPOINTS = [
    ("quote",        "quote?symbol=AAPL",                              True),
    ("eod",          "historical-price-eod/full?symbol=AAPL",          True),
    ("income",       "income-statement?symbol=AAPL&period=quarter&limit=1", True),
    ("estimates",    "analyst-estimates?symbol=AAPL&limit=1",          False),
    ("earnings",     "earnings?symbol=AAPL&limit=1",                   False),
    ("treasury",     "treasury-rates",                                 False),
    ("commodities",  "commodities-list",                               False),
]


def _real_get(url, timeout=15):
    import requests
    t0 = time.time()
    try:
        r = requests.get(url, timeout=timeout)
        try:
            body = r.json()
        except Exception:
            body = r.text
        return r.status_code, body, int((time.time() - t0) * 1000)
    except Exception as e:
        return 0, {"_network_error": str(e)[:120]}, int((time.time() - t0) * 1000)


def probe(get=None, key=None):
    """Probe all endpoints. `get(url)->(status, body, ms)` is injectable for offline tests."""
    get = get or _real_get
    key = key if key is not None else FC._key()
    if not key:
        return {"asof": dt.datetime.utcnow().isoformat() + "Z", "key": False, "overall": "no_key",
                "endpoints": []}
    rows = []
    for name, path, critical in ENDPOINTS:
        sep = "&" if "?" in path else "?"
        url = "%s/%s%sapikey=%s" % (STABLE, path, sep, key)
        status, body, ms = get(url)
        if status == 0:
            reason, msg = "network", (body or {}).get("_network_error", "network error") if isinstance(body, dict) else "network error"
        else:
            reason, msg = FC.classify(status, body)
        n = len(body) if isinstance(body, list) else (1 if (isinstance(body, dict) and reason == "ok") else 0)
        rows.append({"name": name, "ok": reason == "ok", "reason": reason, "status": status,
                     "ms": ms, "n": n, "critical": critical, "msg": (msg or "")[:80]})
    # overall verdict
    if any(r["reason"] == "invalid_key" for r in rows):
        overall = "down"
    elif all(not r["ok"] for r in rows):
        overall = "down"
    elif any((r["critical"] and not r["ok"]) for r in rows):
        overall = "degraded"
    else:
        overall = "ok"
    return {"asof": dt.datetime.utcnow().isoformat() + "Z", "key": True, "overall": overall,
            "endpoints": rows, "okCount": sum(1 for r in rows if r["ok"]), "total": len(rows)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="fmp_health.json")
    ap.add_argument("--strict", action="store_true", help="exit 1 if overall != ok")
    a = ap.parse_args()
    rep = probe()
    tmp = a.out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rep, f, separators=(",", ":"))
    os.replace(tmp, a.out)
    sys.stderr.write("fmp_healthcheck: overall=%s key=%s ok=%s/%s -> %s\n" % (
        rep["overall"], rep["key"], rep.get("okCount", 0), rep.get("total", 0), a.out))
    for r in rep["endpoints"]:
        if not r["ok"]:
            sys.stderr.write("  [%s] %s (HTTP %s, %s)\n" % (r["reason"].upper(), r["name"], r["status"], r["msg"]))
    return 1 if (a.strict and rep["overall"] != "ok") else 0


if __name__ == "__main__":
    raise SystemExit(main())
