#!/usr/bin/env python3
"""FMP Ultimate HISTORICAL pulls — the paid feed yfinance/FRED can't match for the macro complex:
  * eod_history(symbol)      -> full daily OHLCV for any stock / ETF / commodity
  * treasury_curve()         -> the WHOLE Treasury curve (1M..30Y) daily + a real 2s10s slope
  * commodities_list()       -> FMP's tracked commodity universe (symbol,name)
  * commodities_history()    -> daily history for every commodity (or a chosen subset)
  * macro_from_fmp()         -> weekly-aligned RATE / SLOPE / OIL / GOLD / COPPER / NATGAS / SILVER ...
                                driver series + the raw curve/commodity series for the output block

Design rules:
  - KEY: reads FMP_API_KEY, falling back to FMP_ULTIMATE_API_KEY / FMP_UTIMATE_API_KEY (matches the
    GitHub Actions secret mapping) so whichever name the Ultimate secret carries is picked up.
  - FAIL-SOFT: any error -> None / {} so the caller can fall back to yfinance/stooq (labeled).
  - LABEL: every series is tagged source="FMP Ultimate" for the UI / splash provenance.
Research only; not investment advice.
"""
from __future__ import annotations
import os, time

STABLE = "https://financialmodelingprep.com/stable"
SOURCE_LABEL = "FMP Ultimate"

# FMP stable treasury field -> human tenor label (full curve, one call/day).
_TENORS = [("month1","1M"),("month2","2M"),("month3","3M"),("month6","6M"),
           ("year1","1Y"),("year2","2Y"),("year3","3Y"),("year5","5Y"),
           ("year7","7Y"),("year10","10Y"),("year20","20Y"),("year30","30Y")]

# The macro DRIVERS the build conditions every name on, mapped to FMP commodity symbols.
# (Reconciled against /commodities-list at runtime; unknown symbols are simply skipped.)
_DRIVER_SYMS = {"OIL":"CLUSD","BRENT":"BZUSD","NATGAS":"NGUSD","GOLD":"GCUSD","SILVER":"SIUSD",
                "COPPER":"HGUSD","PLATINUM":"PLUSD","PALLADIUM":"PAUSD","ALUMINUM":"ALIUSD",
                "CORN":"ZCUSD","WHEAT":"ZWUSD","SOYBEAN":"ZSUSD","COFFEE":"KCUSD","SUGAR":"SBUSD"}


def _key():
    for k in ("FMP_API_KEY", "FMP_ULTIMATE_API_KEY", "FMP_UTIMATE_API_KEY"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return ""


def have_key():
    return bool(_key())


def _get(s, url, timeout=25, tries=3):
    """GET with small backoff on transient codes. Returns Response or None."""
    import requests  # noqa
    for i in range(tries):
        try:
            r = s.get(url, timeout=timeout)
        except Exception:
            time.sleep(0.4 * (i + 1)); continue
        if r.status_code == 200:
            return r
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(0.6 * (i + 1)); continue
        return r  # 401/403/404 etc -> hand back so caller can stop cleanly
    return None


def _rows_from_eod(j):
    """Normalize FMP EOD payload (stable returns a bare list; legacy returns {'historical':[...]})
    into ascending [[date, close, volume], ...]."""
    rows = j if isinstance(j, list) else (j.get("historical") if isinstance(j, dict) else None)
    if not isinstance(rows, list) or not rows:
        return None
    out = []
    for d in rows:
        if not isinstance(d, dict):
            continue
        dt_ = d.get("date"); c = d.get("close")
        if dt_ and c is not None:
            try:
                out.append([str(dt_)[:10], round(float(c), 4), int(d.get("volume") or 0)])
            except Exception:
                pass
    out.sort(key=lambda x: x[0])
    return out or None


def eod_history(symbol, sess=None, frm=None, to=None, min_rows=40):
    """Full daily OHLCV close+volume for a stock/ETF/commodity -> [[date, close, vol], ...]. None on failure."""
    key = _key()
    if not key:
        return None
    import requests
    s = sess or requests.Session()
    url = "%s/historical-price-eod/full?symbol=%s&apikey=%s" % (STABLE, symbol, key)
    if frm:
        url += "&from=%s" % frm
    if to:
        url += "&to=%s" % to
    r = _get(s, url)
    if r is None or r.status_code != 200:
        return None
    try:
        rows = _rows_from_eod(r.json())
    except Exception:
        return None
    if not rows or len(rows) < min_rows:
        return None
    return rows


def treasury_curve(sess=None, days=420):
    """Whole Treasury curve daily. Returns:
       {'asof', 'source', 'tenors':{label:latest_rate}, 'series':{label:[(date,rate)]},
        'slope2s10s':[(date, y10-y2)]}  — or None."""
    key = _key()
    if not key:
        return None
    import requests, datetime as dt
    s = sess or requests.Session()
    to = dt.date.today(); frm = to - dt.timedelta(days=days)
    url = "%s/treasury-rates?from=%s&to=%s&apikey=%s" % (STABLE, frm.isoformat(), to.isoformat(), key)
    r = _get(s, url)
    if r is None or r.status_code != 200:
        return None
    try:
        j = r.json()
    except Exception:
        return None
    if not isinstance(j, list) or not j:
        return None
    j = [d for d in j if isinstance(d, dict) and d.get("date")]
    j.sort(key=lambda d: d["date"])
    series = {lab: [] for _, lab in _TENORS}
    for d in j:
        for fk, lab in _TENORS:
            v = d.get(fk)
            if v is not None:
                try:
                    series[lab].append((d["date"][:10], float(v)))
                except Exception:
                    pass
    slope = []
    for d in j:
        y10, y2 = d.get("year10"), d.get("year2")
        if y10 is not None and y2 is not None:
            try:
                slope.append((d["date"][:10], round(float(y10) - float(y2), 3)))
            except Exception:
                pass
    last = j[-1]
    tenors = {}
    for fk, lab in _TENORS:
        v = last.get(fk)
        try:
            tenors[lab] = float(v) if v is not None else None
        except Exception:
            tenors[lab] = None
    return {"asof": last["date"][:10], "source": SOURCE_LABEL,
            "tenors": tenors, "series": series, "slope2s10s": slope}


def commodities_list(sess=None):
    """[(symbol, name), ...] of FMP's tracked commodities, or None."""
    key = _key()
    if not key:
        return None
    import requests
    s = sess or requests.Session()
    r = _get(s, "%s/commodities-list?apikey=%s" % (STABLE, key))
    if r is None or r.status_code != 200:
        return None
    try:
        j = r.json()
    except Exception:
        return None
    if not isinstance(j, list):
        return None
    return [(d.get("symbol"), d.get("name")) for d in j if isinstance(d, dict) and d.get("symbol")]


def commodities_history(symbols=None, sess=None, days=420, cap=40):
    """Daily history for commodities -> {symbol: {'name','rows':[[d,c,v]],'source'}}.
    Defaults to FMP's full commodities-list (capped). None on failure / no key."""
    key = _key()
    if not key:
        return None
    import requests, datetime as dt
    s = sess or requests.Session()
    lst = None
    if symbols is None:
        lst = commodities_list(sess=s)
        symbols = [sym for sym, _ in (lst or [])][:cap]
    names = dict(lst or [])
    to = dt.date.today(); frm = (to - dt.timedelta(days=days)).isoformat()
    out = {}
    for sym in symbols:
        rows = eod_history(sym, sess=s, frm=frm, to=to.isoformat(), min_rows=20)
        if rows:
            out[sym] = {"name": names.get(sym, sym), "rows": rows, "source": SOURCE_LABEL}
    return out or None


def _weekly_pct(rows):
    """Daily [[date,close,vol]] -> weekly pct-change list (sample every 5 sessions), matching the
    FRED weekly convention used elsewhere in the build."""
    cl = [r[1] for r in rows if r[1] is not None and r[1] > 0]
    w = cl[::5]
    return [(w[i] / w[i - 1] - 1) for i in range(1, len(w)) if w[i - 1]]


def _weekly_diff(pairs):
    """[(date, level)] -> weekly first-difference list (for the 2s10s slope, which can cross zero
    so pct-change is unstable)."""
    lv = [v for _, v in pairs]
    w = lv[::5]
    return [(w[i] - w[i - 1]) for i in range(1, len(w))]


def macro_from_fmp(sess=None):
    """Build the macro driver dict from real FMP history + the raw series for the output block.
    Returns {'macro': {RATE,SLOPE,OIL,GOLD,COPPER,NATGAS,SILVER,...weekly series},
             'series': {'treasury': <curve>, 'commodities': {label:{'wr','last','source'}}},
             'source': 'FMP Ultimate'} — or None if no key / total failure."""
    key = _key()
    if not key:
        return None
    import requests
    s = sess or requests.Session()
    macro = {}
    series = {}

    cur = treasury_curve(sess=s)
    if cur:
        series["treasury"] = cur
        # RATE driver = weekly pct-change of the 10Y yield level (matches FRED DGS10 convention)
        ten = cur["series"].get("10Y") or []
        if len(ten) > 6:
            macro["RATE"] = _weekly_pct([[d, v, 0] for d, v in ten])
        if len(cur["slope2s10s"]) > 6:
            macro["SLOPE"] = _weekly_diff(cur["slope2s10s"])

    # FULL commodity universe from real FMP history (all ~30 FMP tracks), plus the named
    # subset that the per-name attribution actually conditions on.
    comm_full = commodities_history(sess=s, cap=35) or {}
    # make sure the named macro drivers are present even if outside the (capped) list pull
    for sym in _DRIVER_SYMS.values():
        if sym not in comm_full:
            rows = eod_history(sym, sess=s, min_rows=20)
            if rows:
                comm_full[sym] = {"name": sym, "rows": rows, "source": SOURCE_LABEL}
    sym2wr = {}
    for sym, rec in comm_full.items():
        wr = _weekly_pct(rec.get("rows") or [])
        if wr:
            sym2wr[sym] = wr
    # named drivers -> macro factor series (GOLD/OIL/COPPER/... used in FACS + lineage)
    for label, sym in _DRIVER_SYMS.items():
        if sym in sym2wr:
            macro[label] = sym2wr[sym]
    # full commodity output block (all available), flagged which are drivers
    drv = set(_DRIVER_SYMS.values())
    comm_out = {}
    for sym, rec in comm_full.items():
        rows = rec.get("rows") or []
        if not rows:
            continue
        comm_out[sym] = {"name": rec.get("name", sym), "last": rows[-1][1],
                         "wr": sym2wr.get(sym, []), "driver": sym in drv, "source": SOURCE_LABEL}
    if comm_out:
        series["commodities"] = comm_out

    if not macro:
        return None
    return {"macro": macro, "series": series, "source": SOURCE_LABEL}


__all__ = ["eod_history", "treasury_curve", "commodities_list", "commodities_history",
           "macro_from_fmp", "have_key", "SOURCE_LABEL"]


if __name__ == "__main__":
    import sys, json
    if not have_key():
        sys.stderr.write("fmp_history: no FMP key in env (FMP_API_KEY / FMP_ULTIMATE_API_KEY)\n"); sys.exit(1)
    cur = treasury_curve()
    sys.stderr.write("treasury asof=%s 10Y=%s 2s10s=%s\n" % (
        (cur or {}).get("asof"), (cur or {}).get("tenors", {}).get("10Y"),
        ((cur or {}).get("slope2s10s") or [(None, None)])[-1][1]))
    mm = macro_from_fmp()
    if mm:
        sys.stderr.write("macro drivers: %s\n" % ", ".join(sorted(mm["macro"].keys())))
    sys.exit(0)
