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
    for k in ("FMP_ULTIMATE_API_KEY", "FMP_API_KEY", "FMP_UTIMATE_API_KEY"):
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


def _rows_from_eod_full(j):
    """Normalize FMP EOD payload into ascending [[date, open, high, low, close, volume], ...].
    FMP's historical-price-eod/full returns OHLCV; this keeps all four prices (eod_history keeps
    only close+volume). Missing OHL fall back to close so downstream ATR/high-low stay aligned."""
    rows = j if isinstance(j, list) else (j.get("historical") if isinstance(j, dict) else None)
    if not isinstance(rows, list) or not rows:
        return None
    out = []
    for d in rows:
        if not isinstance(d, dict):
            continue
        dt_ = d.get("date"); c = d.get("close")
        if dt_ is None or c is None:
            continue
        try:
            c = round(float(c), 4)
            o = float(d.get("open") if d.get("open") is not None else c)
            h = float(d.get("high") if d.get("high") is not None else c)
            lw = float(d.get("low") if d.get("low") is not None else c)
            v = int(d.get("volume") or 0)
            out.append([str(dt_)[:10], round(o, 4), round(h, 4), round(lw, 4), c, v])
        except Exception:
            pass
    out.sort(key=lambda x: x[0])
    return out or None


def eod_ohlcv(symbol, sess=None, frm=None, to=None, min_rows=40):
    """Full daily OHLCV for a stock/ETF/commodity from FMP Ultimate (PRIMARY price source).
    Returns [[date, open, high, low, close, volume], ...] ascending, or None on failure so the
    caller can fall back to yfinance/Stooq (clearly labeled)."""
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
        rows = _rows_from_eod_full(r.json())
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


def _num(x):
    try:
        return float(x)
    except Exception:
        return None


def _fp_num(p):
    """'Q1'..'Q4'/'FY'/'Q4' -> 1..4 (annual treated as Q4). None if unparseable."""
    if not p:
        return None
    p = str(p).upper().strip()
    if p in ("FY", "ANNUAL"):
        return 4
    for n in ("1", "2", "3", "4"):
        if n in p:
            return int(n)
    return None


def quarterly_income(symbol, sess=None, limit=13):
    """AUTHORITATIVE fiscal periods from the FMP quarterly income statement -> ascending
       [{filed, periodEnd, fp(1..4), fy(int), eps, rev} ...] — or None.
       This is the ground truth that removes the calendar heuristic: each record carries the real
       fiscal quarter + fiscal year AND the actual SEC filing date (the report date)."""
    key = _key()
    if not key:
        return None
    import requests
    s = sess or requests.Session()
    url = "%s/income-statement?symbol=%s&period=quarter&limit=%d&apikey=%s" % (STABLE, symbol, int(limit), key)
    r = _get(s, url)
    if r is None or r.status_code != 200:
        return None
    try:
        j = r.json()
    except Exception:
        return None
    if not isinstance(j, list) or not j:
        return None
    out = []
    for d in j:
        if not isinstance(d, dict):
            continue
        pe = d.get("date")
        filed = d.get("filingDate") or d.get("fillingDate") or d.get("acceptedDate") or pe
        if not (pe and filed):
            continue
        try:
            fy = int(d.get("fiscalYear") or d.get("calendarYear") or str(pe)[:4]) or None
        except Exception:
            fy = None
        eps = d.get("epsDiluted")
        if eps is None:
            eps = d.get("eps")
        out.append({"filed": str(filed)[:10], "periodEnd": str(pe)[:10],
                    "fp": _fp_num(d.get("period")), "fy": fy, "eps": _num(eps), "rev": d.get("revenue")})
    out.sort(key=lambda x: x["periodEnd"])
    return out or None


def earnings_calendar(symbol, sess=None, limit=24):
    """FMP Ultimate earnings with an AUTHORITATIVE fiscal mapping (no calendar guessing).

    Past quarters come from the quarterly income statement (true fiscal Q/Y + the real SEC filing
    date + actual EPS), joined to the analyst estimate from the earnings calendar (matched by date
    proximity) to compute the surprise. The upcoming quarter's date + estimate come from the earnings
    calendar; its fiscal label is rolled forward from the last reported quarter. Company fiscal
    cadence (fiscal-year-end month + report months) is emitted so the client's fallback for a missing
    'next' is company-correct (Apple FYE Sep, Nvidia Jan, ...). Calendar-heuristic is used ONLY if the
    income statement is unavailable, and is tagged src='cal'.

    -> {'q':[{d,a,e,q,y,s,src} ...<=8], 'next':{d,a,e,q,y,s,src}|absent, 'beat', 'fyEnd', 'qMonths',
        'source':'FMP Ultimate'}  — or None."""
    key = _key()
    if not key:
        return None
    import requests, datetime as dt
    s = sess or requests.Session()
    today = dt.date.today().isoformat()

    # 1) analyst estimates + announce dates (+ actuals) from the earnings calendar
    cal = []
    r = _get(s, "%s/earnings?symbol=%s&limit=%d&apikey=%s" % (STABLE, symbol, int(limit), key))
    if r is not None and r.status_code == 200:
        try:
            jj = r.json()
            if isinstance(jj, list):
                for d in jj:
                    if isinstance(d, dict) and d.get("date"):
                        cal.append({"d": str(d["date"])[:10],
                                    "a": _num(d.get("epsActual") if d.get("epsActual") is not None else d.get("eps")),
                                    "e": _num(d.get("epsEstimated") if d.get("epsEstimated") is not None else d.get("epsEstimate"))})
        except Exception:
            pass
    cal.sort(key=lambda x: x["d"])

    # 2) authoritative fiscal periods from the income statement
    inc = quarterly_income(symbol, sess=s) or []

    def _match_est(filed, pe):
        best, bd = None, 99
        for c in cal:
            for ref in (filed, pe):
                try:
                    dd = abs((dt.date.fromisoformat(c["d"]) - dt.date.fromisoformat(ref)).days)
                except Exception:
                    dd = 99
                if dd < bd:
                    bd, best = dd, c
        return best if bd <= 15 else None

    qrec = []
    for it in inc:
        est = _match_est(it["filed"], it["periodEnd"])
        a = it["eps"] if it["eps"] is not None else (est["a"] if est else None)
        e = est["e"] if est else None
        sp = None
        if a is not None and e not in (None, 0):
            try:
                sp = round(100.0 * (a - e) / abs(e), 1)
            except Exception:
                sp = None
        if it["filed"] <= today:
            # CONFIRMED report (real SEC filing date) with an AUTHORITATIVE fiscal label.
            qrec.append({"d": it["filed"], "a": a, "e": e, "q": it["fp"], "y": it["fy"], "s": sp,
                         "src": "is", "conf": True, "labelSrc": "is"})

    # 2b) heuristic fallback ONLY if the income statement gave nothing
    if not qrec and cal:
        for c in cal:
            if c["a"] is None or c["d"] > today:
                continue
            sp = None
            if c["e"] not in (None, 0):
                try:
                    sp = round(100.0 * (c["a"] - c["e"]) / abs(c["e"]), 1)
                except Exception:
                    sp = None
            q = y = None
            try:
                yy, mm, dd = (int(p) for p in c["d"].split("-"))
                pe = dt.date(yy, mm, min(max(dd, 1), 28)) - dt.timedelta(days=45)
                q, y = (pe.month - 1) // 3 + 1, pe.year
            except Exception:
                pass
            # date is a real announce date (confirmed) but the fiscal LABEL is calendar-derived (est).
            qrec.append({"d": c["d"], "a": c["a"], "e": c["e"], "q": q, "y": y, "s": sp,
                         "src": "cal", "conf": True, "labelSrc": "cal"})

    qrec.sort(key=lambda x: x["d"])
    out = {"q": qrec[-8:], "source": SOURCE_LABEL}

    # 3) NEXT quarter — an ESTIMATE, never a confirmed report. The date is FMP-listed (scheduled, not
    #    yet filed) and the fiscal label is rolled forward, so it is flagged conf=False / est=True and
    #    carries a WINDOW (it must never harden into a single confirmed point downstream).
    fut = [c for c in cal if c["a"] is None and c["d"] > today]
    if fut:
        nq = ny = None
        if out["q"] and out["q"][-1].get("q") and out["q"][-1].get("y"):
            nq, ny = out["q"][-1]["q"] + 1, out["q"][-1]["y"]
            if nq > 4:
                nq, ny = 1, ny + 1
        nd = fut[0]["d"]
        try:
            b = dt.date.fromisoformat(nd)
            win = [(b - dt.timedelta(days=3)).isoformat(), (b + dt.timedelta(days=3)).isoformat()]
        except Exception:
            win = [nd, nd]
        out["next"] = {"d": nd, "a": None, "e": fut[0]["e"], "q": nq, "y": ny, "s": None,
                       "src": "cal", "conf": False, "est": True, "status": "scheduled",
                       "labelEst": True, "window": win}

    # 4) Bayesian-shrunk beat rate
    tot = [r2 for r2 in out["q"] if r2["a"] is not None and r2["e"] not in (None, 0)]
    if tot:
        beats = [r2 for r2 in tot if (r2["a"] or 0) >= (r2["e"] or 0)]
        out["beat"] = round((len(beats) + 1.0) / (len(tot) + 2.0), 2)

    # 5) company fiscal cadence so the client's next-date fallback is company-correct
    if inc:
        try:
            fye = None
            for it in reversed(inc):
                if it.get("fp") == 4:
                    fye = int(it["periodEnd"][5:7]); break
            out["fyEnd"] = fye if fye is not None else int(inc[-1]["periodEnd"][5:7])
            mons = sorted({int(it["filed"][5:7]) for it in inc if it.get("filed")})
            if mons:
                out["qMonths"] = mons[:6]
        except Exception:
            pass

    if not out["q"] and not out.get("next"):
        return None
    return out


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

    # FULL commodity universe from real FMP history — EVERY commodity FMP tracks becomes a
    # per-name attribution driver (not just a named subset). Canonical symbols keep semantic
    # labels (OIL/GOLD/COPPER/...); all others are labeled from FMP's commodity name. The
    # label->name map (commodityKeys) lets the build wire all of them into FACS / Lasso / macro3.
    comm_full = commodities_history(sess=s, cap=45) or {}
    for sym in _DRIVER_SYMS.values():                  # guarantee canonical names are present
        if sym not in comm_full:
            rows = eod_history(sym, sess=s, min_rows=20)
            if rows:
                comm_full[sym] = {"name": sym, "rows": rows, "source": SOURCE_LABEL}
    _sym2lab = {v: k for k, v in _DRIVER_SYMS.items()}   # symbol -> semantic label
    comm_out = {}; comm_keys = {}
    for sym, rec in comm_full.items():
        rows = rec.get("rows") or []
        wr = _weekly_pct(rows)
        if not rows or not wr:
            continue
        label = _sym2lab.get(sym) or (rec.get("name") or sym).upper().replace(" ", "_").replace("/", "_")
        macro[label] = wr                              # <-- ALL commodities feed per-name attribution
        comm_keys[label] = rec.get("name", label)
        comm_out[sym] = {"name": rec.get("name", sym), "label": label, "last": rows[-1][1],
                         "wr": wr, "driver": True, "source": SOURCE_LABEL}
    if comm_out:
        series["commodities"] = comm_out
        series["commodityKeys"] = comm_keys            # label -> display name (drives build attribution)

    if not macro:
        return None
    return {"macro": macro, "series": series, "source": SOURCE_LABEL}


def probe_eod(symbol="AAPL", sess=None):
    """ONE classified call to the PRIMARY price endpoint (/stable/historical-price-eod/full) so a run
    that pulls 0 FMP prices reports WHY instead of silently degrading to yfinance. Returns
    {ok, reason, message, status}; reason in:
       ok | missing | invalid_key | rate_limited | plan_or_endpoint | empty | http_error | network.
    The price path (eod_ohlcv) is fail-soft and never surfaced the HTTP status/body — this is the
    authoritative diagnosis of the PRICE path (the /quote probe in fmp_connector can pass on a plan
    that excludes the historical-EOD endpoint, so they must be probed separately)."""
    key = _key()
    if not key:
        return {"ok": False, "reason": "missing",
                "message": "no FMP key in env (FMP_API_KEY / FMP_ULTIMATE_API_KEY / FMP_UTIMATE_API_KEY)", "status": None}
    try:
        import requests
    except Exception as e:
        return {"ok": False, "reason": "no_requests", "message": str(e)[:120], "status": None}
    try:
        from fmp_connector import classify          # reuse the body-aware classifier (200-with-error etc.)
    except Exception:
        classify = None
    s = sess or requests.Session()
    url = "%s/historical-price-eod/full?symbol=%s&apikey=%s" % (STABLE, symbol, key)
    try:
        r = s.get(url, timeout=25)
    except Exception as e:
        return {"ok": False, "reason": "network", "message": str(e)[:160], "status": None}
    try:
        body = r.json()
    except Exception:
        body = r.text
    if classify:
        reason, msg = classify(r.status_code, body)
    else:
        ok = (r.status_code == 200 and bool(body))
        reason, msg = ("ok", "") if ok else ("http_error", "HTTP %s" % r.status_code)
    # EOD-specific: a 200 with no price rows is "empty", not "ok".
    if reason == "ok":
        rows = body if isinstance(body, list) else (body.get("historical") if isinstance(body, dict) else None)
        if not rows:
            reason, msg = "empty", "HTTP 200 but no price rows"
    return {"ok": reason == "ok", "reason": reason, "message": msg, "status": r.status_code}


__all__ = ["eod_history", "eod_ohlcv", "treasury_curve", "commodities_list", "commodities_history",
           "macro_from_fmp", "earnings_calendar", "probe_eod", "have_key", "SOURCE_LABEL"]


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
