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
    ("estimates",    "analyst-estimates?symbol=AAPL&period=annual&limit=1",  False),  # period REQUIRED (bare -> HTTP 400)
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
                     "ms": ms, "n": n, "critical": critical, "msg": (msg or "")[:80], "fix": REMEDY.get(reason, "")})
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
            "endpoints": rows, "okCount": sum(1 for r in rows if r["ok"]), "total": len(rows),
            "action": _action(rows, overall)}


# Per-reason remediation the probe prints + writes into fmp_health.json so the result is self-explaining.
REMEDY = {
    "invalid_key": "The FMP_API_KEY secret is wrong/expired. Copy a fresh key from financialmodelingprep.com "
                   "(Dashboard -> API Keys) into the repo secret FMP_API_KEY, then re-run.",
    "rate_limited": "Daily/throughput limit hit. Wait for the quota to reset, reduce universe size, or upgrade "
                    "the plan. The key itself is valid.",
    "plan_or_endpoint": "Your key is VALID but its PLAN does not include this endpoint. Upgrade to the plan that "
                        "includes it (historical EOD / charts are on the paid 'Starter+'/Ultimate tiers), or stop "
                        "calling it.",
    "empty": "Endpoint returned an empty body (symbol/params or a transient). Usually safe to ignore if others pass.",
    "http_error": "Unexpected HTTP error. Check status/msg; often transient — re-run.",
    "network": "Could not reach FMP from CI (network/DNS). Re-run; if persistent, check GitHub Actions egress.",
}


def _action(rows, overall):
    """A single human action string for the whole probe (the most useful next step)."""
    if overall == "ok":
        return "All FMP Ultimate endpoints OK - nothing to do."
    by = {r["name"]: r for r in rows}
    if any(r["reason"] == "invalid_key" for r in rows):
        return "KEY INVALID. " + REMEDY["invalid_key"]
    # the diagnostic case: key works somewhere (e.g. quote/fundamentals) but the price path is plan-blocked
    quote_ok = by.get("quote", {}).get("ok") or by.get("income", {}).get("ok")
    eod = by.get("eod", {})
    if quote_ok and not eod.get("ok") and eod.get("reason") == "plan_or_endpoint":
        return ("KEY VALID but the HISTORICAL-EOD price endpoint is not in your plan tier. " + REMEDY["plan_or_endpoint"]
                + " (This is why the board falls back to yfinance prices.)")
    if any(r["reason"] == "rate_limited" for r in rows):
        return "RATE-LIMITED. " + REMEDY["rate_limited"]
    bad = [r["name"] for r in rows if not r["ok"]]
    return "Endpoints failing: %s. See each endpoint's .fix in this file." % ", ".join(bad)


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
            sys.stderr.write("  [%s] %s (HTTP %s, %s)\n      FIX: %s\n" % (
                r["reason"].upper(), r["name"], r["status"], r["msg"], r.get("fix", "")))
    if rep.get("action"):
        sys.stderr.write("\n  >>> ACTION: %s\n" % rep["action"])
    return 1 if (a.strict and rep["overall"] != "ok") else 0


if __name__ == "__main__":
    raise SystemExit(main())
