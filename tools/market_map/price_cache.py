#!/usr/bin/env python3
"""
price_cache.py — incremental + concurrent price-fetch planner (verified core).

At a ~5,000-name universe the legacy build does one SERIAL, FULL-history FMP call per name every night.
This module turns that into: (1) fetch only the DELTA since the last cached bar per name, (2) MERGE it into
the stored history, (3) run the network fetches CONCURRENTLY. Warm-state nightly cost drops from ~5,000
full pulls to ~5,000 tiny deltas run N-wide — orders of magnitude less wall-clock and FMP quota.

Pure-stdlib; the planning/merge logic is deterministic and unit-tested offline (no network).
The actual HTTP still goes through the existing price_source.PriceSource (FMP Ultimate -> yfinance).
"""
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

_FIELDS = ("dates", "cl", "vo", "hi", "lo")


def _busdays(d1, d2):
    """Weekday gap between two ISO dates (proxy for trading days; holidays ignored, safe over-estimate)."""
    a = datetime.date.fromisoformat(str(d1)[:10]); b = datetime.date.fromisoformat(str(d2)[:10])
    if b <= a:
        return 0
    n = 0; cur = a
    while cur < b:
        cur += datetime.timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


def last_cached_date(cached):
    ds = (cached or {}).get("dates") or []
    return ds[-1] if ds else None


def fetch_plan(cached, today, min_rows=30, max_stale_days=45):
    """Decide how to fetch. Returns (mode, since) where mode in {'full','delta','none'}:
      full  -> no/short cache, or cache so stale a full refresh is simpler/safer (since=None)
      delta -> cache is fresh enough; fetch only bars after `since` (the last cached date)
      none  -> already current through `today` (since=last cached date)"""
    ds = (cached or {}).get("dates") or []
    if len(ds) < min_rows:
        return ("full", None)
    last = ds[-1]
    gap = _busdays(last, today)
    if gap <= 0:
        return ("none", last)
    if gap > max_stale_days:
        return ("full", None)
    return ("delta", last)


def merge_bars(cached, fresh):
    """Merge fresh OHLCV into cached: dedup by date, append only new dates, keep date-sorted."""
    out = {k: list((cached or {}).get(k, [])) for k in _FIELDS}
    have = set(out["dates"])
    fd = (fresh or {}).get("dates", [])
    for i, d in enumerate(fd):
        if d in have:
            continue
        for k in _FIELDS:
            v = (fresh or {}).get(k, [])
            out[k].append(v[i] if i < len(v) else None)
        have.add(d)
    order = sorted(range(len(out["dates"])), key=lambda i: str(out["dates"][i]))
    for k in _FIELDS:
        out[k] = [out[k][i] for i in order]
    return out


def concurrent_fetch(symbols, getter, workers=8):
    """Run getter(sym) over symbols concurrently. Returns {sym: result_or_None}. getter must be thread-safe
    (price_source.PriceSource uses an independent requests.Session, which is)."""
    res = {}
    if not symbols:
        return res
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as ex:
        futs = {ex.submit(getter, s): s for s in symbols}
        for f in as_completed(futs):
            s = futs[f]
            try:
                res[s] = f.result()
            except Exception:
                res[s] = None
    return res
