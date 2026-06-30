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
        "verdict": _verdict(n),
    }


def _verdict(n):
    pj = n.get("pj") or {}; nw = n.get("news") or {}; f = n.get("fund") or {}
    score = _tot(n) + 2.0 * _num(pj.get("projPct")) / 100.0 + 0.5 * _num(nw.get("net")) + 0.01 * _num(f.get("targetUpsidePct"))
    tag = "constructive" if score > 0.3 else ("cautious" if score < -0.3 else "balanced")
    return {"score": round(score, 3), "tag": tag}
