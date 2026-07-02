#!/usr/bin/env python3
"""fmp_bulk_eod.py — FMP BULK end-of-day price path (the true "handful of calls" fetch).

Instead of one HTTP call PER TICKER (~700 serial calls that rate-limit and time out), this fetches the
WHOLE universe's EOD for a single date in ONE call — /stable/eod-bulk?date=YYYY-MM-DD — so assembling N
days of history costs ~N calls TOTAL regardless of universe size. Rows are returned in the SAME 6-tuple
shape as fmp_history.eod_ohlcv ([date, open, high, low, close, volume]) so it is a drop-in source.

DESIGN — safe by construction:
  * Header-driven CSV parsing: columns are located BY NAME (case-insensitive), so column reordering or
    extra columns never break it.
  * Every failure path returns {} (no key, no session, non-200, schema mismatch, parse error) so a wrong
    endpoint/plan is a harmless NO-OP and the caller simply falls back to the per-ticker / prefetch path.
  * Endpoint slug + column aliases are env-overridable (MRKT_FMP_EOD_BULK_SLUG) so it can be pointed at the
    exact FMP slug once validated against a live Ultimate key — no code change.

OPT-IN: NOT wired into the nightly build yet. Validate `eod_bulk_day()` against a live key first, then the
build can call history_map() to warm PriceSource before the per-name loop. Pure stdlib + injected session."""
import csv
import datetime as dt
import io
import os
import time

STABLE = "https://financialmodelingprep.com/stable"
SLUG = os.environ.get("MRKT_FMP_EOD_BULK_SLUG", "eod-bulk").strip() or "eod-bulk"


def _key():
    return os.environ.get("FMP_ULTIMATE_API_KEY", "").strip()


def _col(header, *names):
    low = [str(h).strip().lower() for h in header]
    for n in names:
        if n in low:
            return low.index(n)
    return -1


def parse_bulk_csv(text):
    """Parse an eod-bulk CSV -> {SYMBOL: {date,o,h,l,c,v}}. Header-driven; returns {} on any problem."""
    try:
        rows = list(csv.reader(io.StringIO(text or "")))
    except Exception:
        return {}
    if len(rows) < 2:
        return {}
    h = rows[0]
    iS = _col(h, "symbol", "ticker"); iD = _col(h, "date")
    iO = _col(h, "open"); iH = _col(h, "high"); iL = _col(h, "low")
    iC = _col(h, "close", "adjclose", "adjusted_close"); iV = _col(h, "volume")
    if min(iS, iD, iC) < 0:                       # required columns missing -> refuse (safe no-op)
        return {}

    def g(row, i):
        if i < 0 or i >= len(row):
            return None
        v = str(row[i]).strip()
        if v in ("", "null", "NaN", "None"):
            return None
        try:
            return float(v)
        except Exception:
            return None

    out = {}
    for row in rows[1:]:
        if len(row) <= max(iS, iD, iC):
            continue
        sym = str(row[iS]).strip().upper()
        c = g(row, iC)
        if not sym or c is None:
            continue
        out[sym] = {"date": str(row[iD]).strip()[:10], "o": g(row, iO), "h": g(row, iH),
                    "l": g(row, iL), "c": c, "v": g(row, iV) or 0.0}
    return out


def _get(sess, url, timeout=12, tries=2):
    for i in range(tries):
        try:
            r = sess.get(url, timeout=timeout)
        except Exception:
            time.sleep(0.4 * (i + 1)); continue
        sc = getattr(r, "status_code", 0)
        if sc == 200:
            return r
        if sc in (429, 500, 502, 503, 504):
            time.sleep(0.6 * (i + 1)); continue
        return r
    return None


def eod_bulk_day(date_iso, sess, key=None):
    """ONE call: every symbol's EOD for date_iso. Returns {SYM:{...}} or {} (safe no-op on any failure)."""
    key = key or _key()
    if not key or sess is None:
        return {}
    url = "%s/%s?date=%s&apikey=%s" % (STABLE, SLUG, date_iso, key)
    r = _get(sess, url)
    if r is None or getattr(r, "status_code", 0) != 200:
        return {}
    return parse_bulk_csv(getattr(r, "text", "") or "")


def history_map(symbols, sess, days=260, key=None, max_calls=300, sleep=0.0, today=None):
    """Assemble {SYM: [[date,open,high,low,close,volume], ... ascending]} for `symbols` over ~`days` trading
    days via per-date eod-bulk calls (bounded by max_calls). Same 6-tuple shape as fmp_history.eod_ohlcv, so
    it can seed PriceSource directly. Only requested symbols are kept. Any failure -> {} (safe no-op)."""
    key = key or _key()
    want = {str(s).strip().upper() for s in (symbols or []) if s}
    if not key or sess is None or not want:
        return {}
    acc = {}
    d = today or dt.date.today()
    got = 0
    while got < min(int(days), int(max_calls)):
        if d.weekday() < 5:                        # skip weekends; holidays return empty -> harmless
            day = eod_bulk_day(d.isoformat(), sess, key)
            got += 1
            for sym in want:
                row = day.get(sym)
                if row and row.get("c") is not None:
                    c = row["c"]
                    acc.setdefault(sym, []).append([
                        row["date"], row.get("o"), row.get("h") if row.get("h") is not None else c,
                        row.get("l") if row.get("l") is not None else c, c, row.get("v") or 0.0])
            if sleep:
                time.sleep(sleep)
        d -= dt.timedelta(days=1)
    for sym in acc:
        acc[sym].sort(key=lambda x: x[0])
    return acc
