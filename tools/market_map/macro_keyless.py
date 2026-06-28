#!/usr/bin/env python3
"""
macro_keyless.py — KEYLESS macro driver series for the Bull/Bear rank, from the St. Louis Fed
fredgraph CSV (no API key). Closes the biggest ranking-critical coverage hole: previously the macro
betas (n['mb']) collapsed to 0% without an FMP/FRED key, which zeroed the Macro-betas domain AND the
macro tilt in the rank. This populates RATE / DXY / VIX / OIL (and breakevens) for every name, keylessly.

Returns weekly pct-change series keyed to match build_market_map's macro dict (RATE=10y nominal yield,
DXY=broad dollar, VIX=equity vol, OIL=WTI), in the SAME units the per-name Lasso betas are fit on.
Pure-stdlib; the CSV parse + weekly-change + alignment are unit-tested offline (no network).
"""
import sys

# FRED series id -> macro factor key the build/board expects.
SERIES = {"DGS10": "RATE", "DTWEXBGS": "DXY", "VIXCLS": "VIX", "DCOILWTICO": "OIL", "T10YIE": "BREAKEVEN"}
__all__ = ["parse_fred_multi", "weekly_pct", "to_macro", "fetch_macro_keyless", "SERIES"]


def parse_fred_multi(text):
    """fredgraph.csv (multi-series) -> {date: {SERIESID: float}} keeping rows with at least one value.
    FRED uses '.' for missing; those cells are skipped."""
    import csv, io
    out = {}
    rdr = csv.reader(io.StringIO(text or ""))
    hdr = next(rdr, None)
    if not hdr:
        return out
    idx = {h.strip().upper(): i for i, h in enumerate(hdr)}
    di = idx.get("DATE", 0)
    cols = {sid: idx.get(sid) for sid in SERIES if sid in idx}
    for row in rdr:
        if not row or len(row) <= di:
            continue
        d = row[di].strip(); rec = {}
        for sid, ci in cols.items():
            if ci is not None and ci < len(row):
                v = row[ci].strip()
                if v and v != ".":
                    try:
                        rec[sid] = float(v)
                    except Exception:
                        pass
        if d and rec:
            out[d] = rec
    return out


def _ffill(dates, by_date, sid):
    """Forward-filled daily level series for one FRED id over the sorted date axis."""
    out = []; last = None
    for d in dates:
        v = by_date.get(d, {}).get(sid)
        if v is not None:
            last = v
        out.append(last)
    return out


def weekly_pct(levels, step=5):
    """Weekly (step-day) pct change of a level series, dropping leading None. Matches the build's
    'weekly pct-change of the level' convention (e.g. FRED DGS10)."""
    lv = [x for x in levels if x is not None]
    if len(lv) < step + 1:
        return []
    wk = lv[::step]
    return [(wk[i] / wk[i - 1] - 1.0) for i in range(1, len(wk)) if wk[i - 1] not in (0, None)]


def to_macro(by_date):
    """{date:{sid:val}} -> {macroKey: weekly-pct-change series} over the common date axis."""
    dates = sorted(by_date)
    macro = {}
    for sid, key in SERIES.items():
        lv = _ffill(dates, by_date, sid)
        wp = weekly_pct(lv)
        if len(wp) >= 8:
            macro[key] = wp
    return macro


def fetch_macro_keyless(session=None, days=420):
    """Pull the keyless fredgraph multi-series CSV and return {macroKey: weekly-pct series}, or {} on failure."""
    try:
        import requests, datetime
    except Exception:
        return {}
    end = datetime.date.today(); start = end - datetime.timedelta(days=days + 40)
    ids = ",".join(SERIES.keys())
    url = ("https://fred.stlouisfed.org/graph/fredgraph.csv?id=%s&cosd=%s&coed=%s"
           % (ids, start.isoformat(), end.isoformat()))
    try:
        r = (session or requests).get(url, timeout=30)
        if r.status_code != 200:
            sys.stderr.write("macro_keyless: HTTP %s\n" % r.status_code)
            return {}
        m = to_macro(parse_fred_multi(r.text))
        sys.stderr.write("macro_keyless: keys=%s\n" % ",".join(sorted(m.keys())))
        return m
    except Exception as e:
        sys.stderr.write("macro_keyless: %s\n" % str(e)[:160])
        return {}
