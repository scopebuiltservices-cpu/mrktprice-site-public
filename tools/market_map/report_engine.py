#!/usr/bin/env python3
"""report_engine.py — composes the DAILY report MODELS (pure data) from a built marketmap.json:

  * macro_report(mm)            — market-wide: breadth, index tape, sector rotation (in/out), macro drivers,
                                  news tone, top tailwinds/headwinds, projection summary.
  * sector_report(mm, sector)   — one sector: breadth, factor profile, leaders/laggards, push-pull peers
                                  (sectorCorr), sector news tone, ranked names with projection + news.
  * company_report(mm, ticker)  — one name: price snapshot, role-in-sector, valuation, projection, macro
                                  tilt, crowding/regime, news headwinds/tailwinds, and a synthesized verdict.

Pure + defensive (missing fields never crash) so it is unit-tested offline; report_render turns these models
into HTML/PDF. The whole interconnected universe (S&P 500 + Nasdaq + Dow + Russell 2000) feeds the macro and
sector aggregates, so a single name's push-pull role in its sector and the market is explicit. Research only."""
GICS = ["Technology", "Financials", "Health Care", "Consumer Disc.", "Communication", "Industrials",
        "Consumer Staples", "Energy", "Utilities", "Materials", "Real Estate"]
ZCOLS = [("ema", "EMA21 σ"), ("mom", "Momentum"), ("val", "Value"), ("size", "Size"), ("fcf", "FCF yld"),
         ("flow", "Money flow"), ("disloc", "Dislocation"), ("mfi", "MFI"), ("contra", "Contradiction")]


def _num(x, d=0.0):
    try:
        f = float(x); return f if f == f else d
    except (TypeError, ValueError):
        return d


def _ret(n, h="3m"):
    r = n.get("ret")
    if isinstance(r, dict):
        return _num(r.get(h))
    return _num(n.get("ret%s" % h, n.get("r%s" % h)))


def _equities(mm):
    return [n for n in (mm.get("names") or []) if n.get("sec") in GICS and "FACTOR" not in (n.get("idx") or [])]


def _tot(n):
    return _num(n.get("tot"), _num(n.get("exp")))


def _breadth(names, key=lambda n: _tot(n) > 0):
    ns = [n for n in names if isinstance(n, dict)]
    return round(100.0 * sum(1 for n in ns if key(n)) / max(1, len(ns)), 1)


def macro_report(mm):
    eq = _equities(mm)
    tone = (mm.get("newsTone") or {})
    # index tape
    idx_names = {"SPX": "S&P 500", "NDX": "Nasdaq-100", "DOW": "Dow 30", "RUT": "Russell 2000"}
    indices = []
    for code, label in idx_names.items():
        mem = [n for n in eq if code in (n.get("idx") or [])]
        if mem:
            indices.append({"index": label, "n": len(mem), "avgRet3m": round(sum(_ret(n) for n in mem) / len(mem), 2),
                            "breadthPct": _breadth(mem)})
    # sector rotation (rank by avg total-return tilt + breadth)
    rot = []
    for s in GICS:
        mem = [n for n in eq if n.get("sec") == s]
        if not mem:
            continue
        avg = sum(_tot(n) for n in mem) / len(mem)
        rot.append({"sector": s, "n": len(mem), "tilt": round(avg, 3), "breadthPct": _breadth(mem),
                    "secRel": round(sum(_num(n.get("secRel")) for n in mem) / len(mem), 2),
                    "newsNet": _num((tone.get("sectors", {}).get(s) or {}).get("net")),
                    "label": "rotating in" if avg > 0.1 else ("rotating out" if avg < -0.1 else "neutral")})
    rot.sort(key=lambda r: -r["tilt"])
    # macro drivers (avg |macro beta| dominant)
    drv = {}
    for n in eq:
        for k, v in (n.get("mb") or {}).items():
            drv[k] = drv.get(k, 0.0) + abs(_num(v))
    drivers = sorted(({"driver": k, "weight": round(v, 2)} for k, v in drv.items()), key=lambda d: -d["weight"])[:6]
    # tailwinds / headwinds by news
    withnews = [n for n in eq if (n.get("news") or {}).get("n", 0) > 0]
    tw = sorted(withnews, key=lambda n: -_num((n.get("news") or {}).get("net")))[:8]
    hw = sorted(withnews, key=lambda n: _num((n.get("news") or {}).get("net")))[:8]
    return {
        "asof": mm.get("asof"), "universe": len(eq),
        "breadthPct": _breadth(eq), "advancers": sum(1 for n in eq if _tot(n) > 0), "decliners": sum(1 for n in eq if _tot(n) <= 0),
        "indices": indices, "rotation": rot, "macroDrivers": drivers,
        "newsTone": tone.get("market", {"label": "no-news", "net": 0.0}),
        "projAvgPct": round(sum(_num((n.get("pj") or {}).get("projPct")) for n in eq) / max(1, len(eq)), 2),
        "topTailwinds": [{"t": n["t"], "sec": n.get("sec"), "net": _num((n.get("news") or {}).get("net")),
                          "why": ((n.get("news") or {}).get("topPos") or [None])[0]} for n in tw if _num((n.get("news") or {}).get("net")) > 0],
        "topHeadwinds": [{"t": n["t"], "sec": n.get("sec"), "net": _num((n.get("news") or {}).get("net")),
                          "why": ((n.get("news") or {}).get("topNeg") or [None])[0]} for n in hw if _num((n.get("news") or {}).get("net")) < 0],
        "treasuryCurve": _treasury_curve(mm),
        "macroComplex": _macro_complex(eq, _MM.compute(mm.get("macroSeries")) if isinstance(mm, dict) else None),
        "regimeMix": _regime_mix(eq),
        "earningsAhead": _earnings_density(eq),
    }


def sector_report(mm, sector):
    eq = [n for n in _equities(mm) if n.get("sec") == sector]
    if not eq:
        return {"sector": sector, "n": 0, "empty": True}
    factor = {}
    for key, lab in ZCOLS:
        vals = [_num((n.get("z") or {}).get(key)) for n in eq if isinstance(n.get("z"), dict) and key in n["z"]]
        factor[key] = {"label": lab, "z": round(sum(vals) / len(vals), 2) if vals else 0.0}
    ranked = sorted(eq, key=lambda n: -_tot(n))
    # push-pull peers from sectorCorr
    sc = mm.get("sectorCorr") or {}
    peers = []
    order, M = sc.get("order") or [], sc.get("m") or []
    if sector in order:
        i = order.index(sector)
        for j, s2 in enumerate(order):
            if j != i and i < len(M) and j < len(M[i]):
                peers.append({"sector": s2, "corr": round(_num(M[i][j]), 2)})
        peers.sort(key=lambda p: -p["corr"])
    return {
        "sector": sector, "asof": mm.get("asof"), "n": len(eq),
        "avgRet3m": round(sum(_ret(n) for n in eq) / len(eq), 2), "breadthPct": _breadth(eq),
        "avgTilt": round(sum(_tot(n) for n in eq) / len(eq), 3),
        "factorProfile": factor,
        "newsTone": (mm.get("newsTone", {}).get("sectors", {}) or {}).get(sector, {"label": "no-news", "net": 0.0}),
        "leaders": [_name_row(n) for n in ranked[:6]],
        "laggards": [_name_row(n) for n in ranked[-6:]][::-1],
        "pushPull": {"movesWith": peers[:3], "movesAgainst": peers[-2:][::-1] if len(peers) > 3 else []},
    }


def _name_row(n):
    nw = n.get("news") or {}
    pj = n.get("pj") or {}
    f = n.get("fund") or {}
    return {"t": n.get("t"), "name": n.get("n"), "tilt": round(_tot(n), 3), "ret3m": _ret(n),
            "secRel": _num(n.get("secRel")), "projPct": _num(pj.get("projPct")), "probUp": _num(pj.get("probUp")),
            "targetUpPct": _num(f.get("targetUpsidePct")), "rating": f.get("rating"),
            "newsNet": _num(nw.get("net")), "newsLabel": nw.get("label", "no-news")}


def company_report(mm, ticker):
    eq = _equities(mm)
    n = next((x for x in (mm.get("names") or []) if (x.get("t") or "").upper() == ticker.upper()), None)
    if not n:
        return {"ticker": ticker, "found": False}
    sec = n.get("sec")
    peers = [x for x in eq if x.get("sec") == sec]
    peers_sorted = sorted(peers, key=lambda x: -_tot(x))
    rank = next((i + 1 for i, x in enumerate(peers_sorted) if x.get("t") == n.get("t")), None)
    nw = n.get("news") or {}
    pj = n.get("pj") or {}
    f = n.get("fund") or {}
    macro = sorted(((k, _num(v)) for k, v in (n.get("mb") or {}).items()), key=lambda kv: -abs(kv[1]))[:5]
    winds = []
    if pj.get("projPct") is not None:
        winds.append(("Projection", "%+.1f%% over %sd (P-up %.0f%%)" % (_num(pj.get("projPct")), pj.get("h", 21), 100 * _num(pj.get("probUp")))))
    if f.get("targetUpsidePct") is not None:
        winds.append(("Analyst target", "%+.1f%% upside, rating %s" % (_num(f.get("targetUpsidePct")), f.get("rating") or "n/a")))
    if nw.get("n", 0) > 0:
        winds.append(("News", "%s (net %+.2f, %d headlines)" % (nw.get("label"), _num(nw.get("net")), nw.get("n"))))
    return {
        "ticker": n.get("t"), "name": n.get("n"), "sector": sec, "asof": mm.get("asof"), "found": True,
        "indices": n.get("idx") or [],
        "price": {"ret1m": _ret(n, "1m"), "ret3m": _ret(n, "3m"), "ret6m": _ret(n, "6m"), "ret12m": _ret(n, "12m"),
                  "beta": _num(n.get("beta")), "tot": round(_tot(n), 3)},
        "roleInSector": {"sector": sec, "rankInSector": rank, "ofN": len(peers), "secRel": _num(n.get("secRel"))},
        "valuation": {"pe": f.get("pe"), "targetUpsidePct": f.get("targetUpsidePct"), "rating": f.get("rating"), "roe": f.get("roe")},
        "projection": {"projPct": _num(pj.get("projPct")), "probUp": _num(pj.get("probUp")), "sigmaHPct": _num(pj.get("sigmaHPct")), "h": pj.get("h", 21)},
        "macroTilt": [{"driver": k, "beta": round(v, 2)} for k, v in macro],
        "crowding": n.get("cr") or {}, "regime": n.get("reg") or {},
        "news": {"net": _num(nw.get("net")), "label": nw.get("label", "no-news"), "n": nw.get("n", 0),
                 "tailwinds": nw.get("topPos") or [], "headwinds": nw.get("topNeg") or []},
        "winds": winds,
        "ebitda": ebitda_block(n),
        "calendar": calendar_block(n, mm.get("_macroEvents") if isinstance(mm, dict) else None),
        "sensitivities": sensitivities_block(n, _MM.compute(mm.get("macroSeries")) if isinstance(mm, dict) else None),
        "quarterly": quarterly_block(n),
        "multiples": multiples_block(n),
        "volRange": vol_range_block(n),
        "volumeTriggers": volume_triggers_block(n),
        "verdict": _verdict(n),
    }


def _verdict(n):
    pj = n.get("pj") or {}; nw = n.get("news") or {}; f = n.get("fund") or {}
    score = _tot(n) + 2.0 * _num(pj.get("projPct")) / 100.0 + 0.5 * _num(nw.get("net")) + 0.01 * _num(f.get("targetUpsidePct"))
    tag = "constructive" if score > 0.3 else ("cautious" if score < -0.3 else "balanced")
    return {"score": round(score, 3), "tag": tag}


# ---------------- 100x enrichment: EBITDA, calendar, macro/commodity sensitivities ----------------
import datetime as _dt
import macro_moves as _MM


def _future_earnings(n):
    """Next + last earnings dates from n['earn']['q'] (real payload field)."""
    qs = ((n.get("earn") or {}).get("q")) or []
    today = _dt.date.today()
    fut, past = [], []
    for q in qs:
        d = str(q.get("d") or "")[:10]
        try:
            dd = _dt.date.fromisoformat(d)
        except Exception:
            continue
        (fut if dd >= today else past).append((dd, q))
    nextq = min(fut, key=lambda x: x[0]) if fut else None
    lastq = max(past, key=lambda x: x[0]) if past else None
    return nextq, lastq


def ebitda_block(n):
    """Adjusted EBITDA last quarter + expected EBITDA next quarter (defensive: populates once the
    fundamentals/estimates pull carries them; never crashes if absent)."""
    f = n.get("fund") or {}
    last = f.get("ebitdaLastQ", f.get("ebitdaAdjLastQ", f.get("ebitdaTtm")))
    nxt = f.get("ebitdaNextQ", f.get("ebitdaFwd", f.get("ebitdaEstNext")))
    g = None
    if _num(last, None) not in (None, 0) and _num(nxt, None) is not None:
        try:
            g = round((float(nxt) - float(last)) / abs(float(last)) * 100.0, 1)
        except Exception:
            g = None
    return {"lastQAdj": last, "nextQExp": nxt, "growthPct": g,
            "have": (last is not None or nxt is not None)}


def calendar_block(n, macro_events=None):
    nextq, lastq = _future_earnings(n)
    f = n.get("fund") or {}
    rows = []
    if nextq:
        rows.append({"event": "Next earnings", "date": nextq[0].isoformat(), "detail": "Q%s FY%s (est EPS %s)" % (nextq[1].get("q"), nextq[1].get("y"), nextq[1].get("e"))})
    if f.get("nextExDate"):
        rows.append({"event": "Ex-dividend", "date": str(f.get("nextExDate"))[:10], "detail": "div $%s (ttm)" % f.get("div12m", "—")})
    ls = f.get("lastSplit") or {}
    if isinstance(ls, dict) and ls.get("date"):
        rows.append({"event": "Last split", "date": str(ls.get("date"))[:10], "detail": str(ls.get("ratio") or "")})
    if lastq:
        rows.append({"event": "Last earnings", "date": lastq[0].isoformat(), "detail": "surprise %s%%" % lastq[1].get("s")})
    for e in (macro_events or [])[:4]:
        rows.append({"event": e.get("event", "Macro"), "date": str(e.get("date"))[:10], "detail": e.get("detail", "high impact")})
    rows.sort(key=lambda r: r["date"])
    return rows


def _sens_row(d, kind, moves=None):
    """Normalize a dependency dict (n.deps row or n.macro3 entry) into a report sensitivity row.
    sens = expected % stock move per +1 sigma of the factor (build-computed). When the factor's CURRENT
    move is available, also report driverSigma (how many sigma the driver moved) and the LIVE implied
    contribution impliedPct = sens x driverSigma, and set the wind by the contribution's sign."""
    sens = _num(d.get("sens"))
    mv = _MM.lookup(d.get("f"), moves) if moves else None
    driver_sigma = _num(mv.get("sigma")) if mv else None
    driver_move = _num(mv.get("movePct")) if mv else None
    implied = round(sens * driver_sigma, 2) if (mv and driver_sigma is not None) else None
    if implied is not None and abs(implied) > 1e-9:
        wind = "tailwind" if implied > 0 else "headwind"
    else:
        wind = "tailwind" if (sens > 0) else ("headwind" if sens < 0 else "neutral")
    return {"factor": d.get("f"), "kind": kind, "sensPct": round(sens, 2), "corr": _num(d.get("corr")),
            "pcorr": _num(d.get("pcorr")), "sig": bool(d.get("sig")), "weak": bool(d.get("weak")),
            "dir": d.get("dir") or ("with" if sens >= 0 else "against"), "stab": d.get("stab"),
            "wind": wind, "lag": d.get("lag"),
            "driverMovePct": driver_move, "driverSigma": driver_sigma, "impliedPct": implied}


def sensitivities_block(n, moves=None):
    """The detailed %/sigma exposures to the dependent commodities + interest rates the name trades on.
    Built from the build's own n['macro3'] (rate + top commodities) and n['deps'] (market/sector), enriched
    with each driver's CURRENT move/sigma and the live implied % contribution when macroSeries is present."""
    m3 = n.get("macro3") or {}
    rate = m3.get("rate")
    commodities = [_sens_row(d, "commodity", moves) for d in (m3.get("top") or [])]
    rate_row = _sens_row(rate, "rate", moves) if isinstance(rate, dict) else None
    market = [_sens_row(d, "market", moves) for d in (n.get("deps") or []) if isinstance(d, dict)]
    macro_rows = commodities + ([rate_row] if rate_row else [])
    _imp = lambda r: r.get("impliedPct")
    # SIGNIFICANCE GATE: only statistically SIGNIFICANT, STABLE, non-WEAK drivers earn an attributed live
    # contribution. The build already computes per-factor sig/p/stab/weak in n.deps & n.macro3; summing every
    # driver's impliedPct (the prior behavior) laundered insignificant betas into a confident macro
    # attribution. liveContribPct now reports the DEFENSIBLE sig-gated total; grossContribPct keeps the
    # unfiltered sum for transparency.
    gross = [_imp(r) for r in macro_rows if _imp(r) is not None]
    sig_rows = [r for r in macro_rows
                if _imp(r) is not None and r.get("sig") and not r.get("weak") and (r.get("stab") in (None, "stable"))]
    gross_total = round(sum(gross), 2) if gross else None
    sig_total = (round(sum(_imp(r) for r in sig_rows), 2) if gross else None)
    if sig_total is None and gross:
        sig_total = 0.0
    r2 = _num(n.get("macroR2"))
    plausible = (sig_total is None) or (abs(sig_total) <= 50.0)   # absurdity bound: >50% single-period macro move = distrust
    return {"macroR2": r2, "macroExplainedShare": (round(r2 / 100.0, 3) if r2 is not None else None),
            "dominantDriver": n.get("drv"),
            "rate": rate_row, "commodities": commodities, "market": market,
            "liveContribPct": sig_total, "grossContribPct": gross_total,
            "nSigDrivers": len(sig_rows), "nDrivers": len(gross), "plausible": plausible,
            "hasLive": sig_total is not None,
            "note": "liveContribPct = sum of impliedPct (sens \u00d7 driver\u2019s current \u03c3-move) over ONLY "
                    "statistically-significant, stable, non-weak drivers; grossContribPct includes all."}


def _treasury_curve(mm):
    ms = (mm.get("macroSeries") or {}).get("treasury") or {}
    ten = ms.get("tenors") or {}
    order = ["1M", "3M", "6M", "1Y", "2Y", "5Y", "10Y", "30Y"]
    pts = [{"tenor": t, "yield": _num(ten[t])} for t in order if t in ten]
    slope = None
    if "2Y" in ten and "10Y" in ten:
        slope = round(_num(ten["10Y"]) - _num(ten["2Y"]), 2)
    return {"points": pts, "slope2s10s": slope, "inverted": (slope is not None and slope < 0)}


def _macro_complex(eq, moves=None):
    """Which commodities/rates the WHOLE market is most exposed to (avg |sens| across names)."""
    agg = {}
    for n in eq:
        m3 = n.get("macro3") or {}
        rows = list(m3.get("top") or [])
        if isinstance(m3.get("rate"), dict):
            rows.append(m3["rate"])
        for d in rows:
            f = d.get("f")
            if not f:
                continue
            a = agg.setdefault(f, {"sum": 0.0, "n": 0, "net": 0.0})
            a["sum"] += abs(_num(d.get("sens"))); a["net"] += _num(d.get("sens")); a["n"] += 1
    out = [{"driver": f, "avgAbsSens": round(a["sum"] / a["n"], 2), "avgSens": round(a["net"] / a["n"], 2), "names": a["n"]}
           for f, a in agg.items() if a["n"] >= 2]
    if moves:
        for r in out:
            mv = _MM.lookup(r["driver"], moves)
            if mv:
                r["nowMovePct"] = _num(mv.get("movePct")); r["nowSigma"] = _num(mv.get("sigma"))
    out.sort(key=lambda x: -x["avgAbsSens"])
    return out[:8]


def _regime_mix(eq):
    calm = stress = 0
    for n in eq:
        st = (n.get("reg") or {}).get("state", n.get("regime"))
        if st in (1, "stress"):
            stress += 1
        else:
            calm += 1
    tot = calm + stress or 1
    return {"calm": calm, "stress": stress, "stressPct": round(100.0 * stress / tot, 1)}


def _earnings_density(eq):
    today = _dt.date.today(); horizon = today + _dt.timedelta(days=14)
    names = []
    for n in eq:
        nq, _ = _future_earnings(n)
        if nq and today <= nq[0] <= horizon:
            names.append({"t": n.get("t"), "date": nq[0].isoformat()})
    names.sort(key=lambda x: x["date"])
    return {"next14d": len(names), "names": names[:12]}


# ---------------- quarterly history, multiples, vol/range, volume triggers (real n.* fields) ----------------
def quarterly_block(n):
    """The full list of quarterly reports the history supports: expected (estimate) vs actual reported EPS +
    surprise %, plus the next (upcoming) expected quarter and forward consensus. From n['earn']."""
    e = n.get("earn") or {}
    qs = e.get("q") or []
    rows = []
    for q in qs:
        est, act = _num(q.get("e"), None), _num(q.get("a"), None)
        rows.append({"label": "Q%s %s" % (q.get("q"), q.get("y")), "date": str(q.get("d") or "")[:10],
                     "estEPS": est, "actualEPS": act, "surprisePct": _num(q.get("s"), None),
                     "beat": (act is not None and est is not None and act >= est)})
    rows.sort(key=lambda r: r["date"])
    nxt = e.get("next") or {}
    next_q = {"label": "Q%s %s" % (nxt.get("q"), nxt.get("y")), "date": str(nxt.get("d") or "")[:10],
              "estEPS": _num(nxt.get("e"), None)} if nxt.get("d") else None
    graded = [r for r in rows if r["actualEPS"] is not None and r["estEPS"] is not None]
    beats = sum(1 for r in graded if r["beat"])
    cons = e.get("estCons") or {}
    return {"history": rows, "nReports": len(graded),
            "beatRate": round(100.0 * beats / len(graded), 0) if graded else None,
            "avgSurprisePct": round(sum(r["surprisePct"] for r in graded if r["surprisePct"] is not None) / max(1, len(graded)), 1) if graded else None,
            "nextExpected": next_q,
            "fwdConsensus": {"eps": _num(cons.get("eps"), None), "period": cons.get("period"), "rev": _num(cons.get("rev"), None)} if cons else None}


def multiples_block(n):
    """Valuation multiples for the unique company: trailing/forward P/E, PEG, EV/EBITDA vs sector, FCF yield,
    DCF fair value + gap, analyst target range + upside, and the build's own valuation verdict. From n['val'] etc."""
    v = n.get("val") or {}
    pt = n.get("ptgt") or {}
    return {
        "pe": _num(v.get("pe"), None), "fpe": _num(v.get("fpe"), None), "peg": _num(v.get("peg"), None),
        "evEbitda": _num(v.get("evb"), None), "peSector": _num(v.get("peSec"), None), "evSector": _num(v.get("evSec"), None),
        "epsGrowth": _num(v.get("epsg"), None), "revGrowth": _num(v.get("revg"), None), "fcfYieldPct": _num(n.get("fcfY"), None),
        "dcfFair": _num(n.get("dcf"), None), "dcfGapPct": (round(_num(n.get("dcfGap")) * 100.0, 1) if n.get("dcfGap") is not None else None),
        "target": {"low": _num(pt.get("low"), None), "mid": _num(pt.get("tgt"), None), "high": _num(pt.get("high"), None)},
        "targetUpsidePct": (round(_num(n.get("tgtUpside")) * 100.0, 1) if n.get("tgtUpside") is not None else None),
        "verdict": v.get("overall"), "verdictWhy": v.get("reason"),
    }


def vol_range_block(n):
    """Calculated volatility + trading range for the unique company + its history: realized / implied /
    Parkinson vol, ATR, variance-ratio regime, jump ratio, OU half-life, EMA21 displacement, and the trading
    range from options walls (support/resistance) + analyst target band. From n['vol','ivol','pvol','atr',...]."""
    opt = n.get("opt") or {}
    pt = n.get("ptgt") or {}
    vr = _num(n.get("vr"), None)
    regime = n.get("regime") or ("trending" if (vr is not None and vr >= 1.15) else ("mean-reverting" if (vr is not None and vr <= 0.85) else "random-walk"))
    return {
        "realizedVolPct": _num(n.get("vol"), None), "impliedVolPct": _num(n.get("ivol"), None),
        "parkinsonVolPct": _num(n.get("pvol"), None), "atr": _num(n.get("atr"), None),
        "varianceRatio": vr, "regime": regime, "jumpRatio": _num(n.get("jump"), None), "halfLifeDays": _num(n.get("hl"), None),
        "ema21DistPct": _num(n.get("ema21d"), None), "ema21Sigma": _num(n.get("ema21sig"), None), "ema21SlopePct": _num(n.get("ema21sl"), None),
        "rangeOptions": {"support": _num(opt.get("pw"), None), "flip": _num(opt.get("gex"), None), "resistance": _num(opt.get("cw"), None)},
        "rangeAnalyst": {"low": _num(pt.get("low"), None), "mid": _num(pt.get("tgt"), None), "high": _num(pt.get("high"), None)},
    }


def volume_triggers_block(n):
    """Trigger volumes / flow signals for the unique company: money-flow net (1m/3m) + in vs out, MFI,
    breakout trigger, beat probability, and the build's fired alert strings. From n['flow','mfi','brk','odds','alerts']."""
    fl = n.get("flow") or {}
    odds = n.get("odds") or {}
    inn, out = _num(fl.get("in")), _num(fl.get("out"))
    return {
        "flowNet1mPct": (round(_num(fl.get("net1m")) * 100.0, 1) if fl.get("net1m") is not None else None),
        "flowNet3mPct": (round(_num(fl.get("net3m")) * 100.0, 1) if fl.get("net3m") is not None else None),
        "inflow": inn, "outflow": out,
        "inflowSharePct": (round(100.0 * inn / (inn + out), 0) if (inn + out) > 0 else None),
        "mfi": _num(n.get("mfi"), None), "breakout": bool(n.get("brk")),
        "beatProb": (round(_num(odds.get("beat")) * 100.0, 0) if odds.get("beat") is not None else None),
        "alerts": [a for a in (n.get("alerts") or []) if isinstance(a, str)],
    }

