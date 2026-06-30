#!/usr/bin/env python3
"""needs_rebuild.py — SELF-HEALING rebuild trigger for the nightly Market Map build.

The map build only runs on a tools/market_map change, a [rebuild] tag, manual dispatch, or the cron.
Two failure modes can then silently strand the LIVE site on stale data while the terminal banner reads
"FMP Ultimate is NOT pulling … last successful FMP pull: never this run":

  (1) ENGINE DRIFT — an engine upgrade (e.g. switching prices to FMP-primary via price_source.py) that
      did not re-trigger a MAP rebuild, so the new engine's output never published. The committed
      marketmap.json is then an OLD-engine artifact (yfinance-primary, no fmpLastOk/priceSrc health
      fields) and the terminal, finding fmpLastOk absent, prints "never this run".
  (2) STUCK NIGHTLY — a missed/failed nightly so `asof` drifts days behind today.

This prints "true" when the PUBLISHED marketmap.json should be force-rebuilt:
  - file missing or unparseable
  - asof older than --max-stale-days (default 2)
  - OLD ENGINE: dataHealth lacks BOTH current FMP-primary price-health fields (priceSrc AND fmpLastOk),
    or `source` still says prices came from yfinance-primary
Else prints "false". Always exit 0 (a decision helper, not a gate). Pure stdlib. Verified.

CLI: python3 needs_rebuild.py marketmap.json [--max-stale-days 2]
Wire (pages.yml detect step):
    if [ "$(python3 tools/market_map/needs_rebuild.py marketmap.json)" = "true" ]; then need=true; fi
"""
import argparse, datetime as dt, json, sys


def needs_rebuild(map_path, max_stale_days=2, today=None):
    """Returns (bool, reason)."""
    try:
        with open(map_path, "r", encoding="utf-8") as f:
            m = json.load(f)
    except FileNotFoundError:
        return True, "marketmap.json missing"
    except Exception as e:
        return True, "marketmap.json unparseable (%s)" % (type(e).__name__)

    dh = m.get("dataHealth") or {}
    src = (m.get("source") or "")
    # OLD ENGINE: the current FMP-primary engine emits priceSrc + fmpLastOk in dataHealth; their absence
    # (or a yfinance-primary source label) means the published artifact predates the FMP-primary upgrade.
    old_engine = (("priceSrc" not in dh) and ("fmpLastOk" not in dh)) or ("yfinance prices" in src)
    if old_engine:
        return True, "published map built by an OLDER engine (FMP-primary price-health fields absent)"

    asof = m.get("asof") or ""
    today = today or dt.date.today()
    try:
        d = dt.date.fromisoformat(asof)
    except Exception:
        return True, "asof missing/invalid (%r)" % asof
    age = (today - d).days
    if age > max_stale_days:
        return True, "published map is %d days stale (asof %s > %d-day budget)" % (age, asof, max_stale_days)

    return False, "fresh, current-engine (asof %s, %d day(s) old)" % (asof, age)


def main():
    ap = argparse.ArgumentParser(description="Decide whether the published marketmap.json must be force-rebuilt.")
    ap.add_argument("map", nargs="?", default="marketmap.json")
    ap.add_argument("--max-stale-days", type=int, default=2)
    a = ap.parse_args()
    need, reason = needs_rebuild(a.map, a.max_stale_days)
    sys.stderr.write("needs_rebuild: %s — %s\n" % (need, reason))
    print("true" if need else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
