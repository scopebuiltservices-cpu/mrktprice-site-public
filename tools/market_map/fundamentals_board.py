#!/usr/bin/env python3
"""fundamentals_board.py — POST-BUILD enrichment: merge FMP fundamentals + analyst data into n.fund.

External-enrichment pattern (event_board.py). Merges, when present:
  - data/fundamentals.json (fmp_bulk: ratios/key-metrics/price-target-summary/rating)
  - data/estimates.json    (fmp_estimates: forward consensus EPS/revenue + last earnings surprise %)
  - data/actions.json      (fmp_actions: trailing-12m dividend, next ex-date, last split)
into a compact per-name block:
    n["fund"] = {pe,pb,roe,netMargin,debtEq,fcfYield,divYield,targetAvg,targetUpsidePct,rating,ratingScore,
                 epsFwd,revFwd,surprisePct,div12m,nextExDate,lastSplit}
targetUpsidePct uses the last committed close (hist). Absent files -> no-op. Idempotent; verified. Research only."""
import argparse, json, os, sys

KEEP = ("pe", "pb", "roe", "netMargin", "debtEq", "fcfYield", "divYield", "targetAvg", "rating", "ratingScore")


def _load(path):
    if path and os.path.exists(path):
        try:
            d = json.load(open(path))
            return {k: v for k, v in d.items() if not k.startswith("_")}
        except Exception:
            return {}
    return {}


def _last_close(hist_dir, tk):
    p = os.path.join(hist_dir, "%s.json" % tk)
    if not os.path.exists(p):
        return None
    try:
        h = json.load(open(p))
        rows = h.get("rows") if isinstance(h, dict) else h
        for r in reversed(rows or []):
            if len(r) > 1 and r[1]:
                return float(r[1])
    except Exception:
        return None
    return None


def fund_for(rec, est, act, close):
    out = {}
    if rec:
        out.update({k: rec.get(k) for k in KEEP if rec.get(k) is not None})
        ta = rec.get("targetAvg")
        if ta and close and close > 0:
            out["targetUpsidePct"] = round((ta / close - 1.0) * 100.0, 2)
        # --- TANGIBLE BOOK VALUE ----------------------------------------------------------------
        # TBVPS = tangible book value per share = (equity - goodwill - intangibles)/shares. We surface
        # the per-share book vs tangible-book gap (intangible "air"), and derive P/TBV + premium/discount
        # to TBV from OUR last committed close (fresher than the vendor ratio). A firm whose tangible
        # equity is NEGATIVE (goodwill/intangible-heavy, e.g. post-acquisition) is flagged honestly rather
        # than hidden; trading BELOW tangible book is flagged as an asset-backed margin of safety.
        tbvps = rec.get("tbvps"); bvps = rec.get("bvps")
        if tbvps is not None:
            out["tbvps"] = round(tbvps, 4)
            if bvps is not None:
                out["bvps"] = round(bvps, 4)
                out["intangPerSh"] = round(bvps - tbvps, 4)            # goodwill+intangibles carried in book
            if rec.get("pTbvFmp") is not None:
                out["pTbvFmp"] = round(rec["pTbvFmp"], 3)              # vendor P/TBV cross-check
            if close and close > 0:
                if tbvps > 0:
                    out["pTbv"] = round(close / tbvps, 3)             # price / tangible book per share
                    out["tbvDiscPct"] = round((close / tbvps - 1.0) * 100.0, 1)   # +premium / -discount to TBV
                    out["tbvFlag"] = "below_tbv" if close < tbvps else None
                else:
                    out["pTbv"] = None
                    out["tbvFlag"] = "negative_tbv"                   # tangible equity < 0
    if est:
        if est.get("epsAvg") is not None:
            out["epsFwd"] = est["epsAvg"]
        if est.get("revAvg") is not None:
            out["revFwd"] = est["revAvg"]
        if est.get("surprisePct") is not None:
            out["surprisePct"] = est["surprisePct"]
        if est.get("ebitdaNextQ") is not None:
            out["ebitdaNextQ"] = est["ebitdaNextQ"]
        if est.get("ebitdaLastQ") is not None:
            out["ebitdaLastQ"] = est["ebitdaLastQ"]
    if act:
        if act.get("div12m") is not None:
            out["div12m"] = act["div12m"]
        if act.get("nextExDate"):
            out["nextExDate"] = act["nextExDate"]
        if act.get("lastSplit"):
            out["lastSplit"] = act["lastSplit"]
    return out or None


def enrich(mm, fund_map, est_map, act_map, hist_dir):
    names = mm.get("names") or []
    done = 0
    for n in names:
        tk = (n.get("t") or n.get("sym") or "").upper()
        if not tk:
            continue
        rec = fund_map.get(tk); est = est_map.get(tk); act = act_map.get(tk)
        if not (rec or est or act):
            continue
        f = fund_for(rec, est, act, _last_close(hist_dir, tk))
        if f:
            n["fund"] = f
            done += 1
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="marketmap.json")
    ap.add_argument("--fund", default="data/fundamentals.json")
    ap.add_argument("--est", default="data/estimates.json")
    ap.add_argument("--actions", default="data/actions.json")
    ap.add_argument("--hist", default="hist")
    a = ap.parse_args()
    fm, em, am = _load(a.fund), _load(a.est), _load(a.actions)
    if not (fm or em or am):
        sys.stderr.write("fundamentals_board: no fundamentals/estimates/actions files — skipped\n")
        return 0
    try:
        mm = json.load(open(a.map))
    except Exception as e:
        sys.stderr.write("fundamentals_board: cannot read %s (%s)\n" % (a.map, str(e)[:80]))
        return 1
    done = enrich(mm, fm, em, am, a.hist)
    tmp = a.map + ".tmp"
    with open(tmp, "w") as f:
        json.dump(mm, f, separators=(",", ":"))
    os.replace(tmp, a.map)
    sys.stderr.write("fundamentals_board: enriched %d names (fund+est+actions) -> %s\n" % (done, a.map))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
