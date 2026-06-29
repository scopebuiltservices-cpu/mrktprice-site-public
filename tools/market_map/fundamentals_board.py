#!/usr/bin/env python3
"""fundamentals_board.py — POST-BUILD enrichment: merge FMP bulk fundamentals + analyst data into n.fund.

External-enrichment pattern (event_board.py): reads data/fundamentals.json (from fmp_bulk.py — ratios,
key-metrics, price-target-summary, rating, all via bulk CSV) and writes a compact per-name block:
    n["fund"] = {pe, pb, roe, netMargin, debtEq, fcfYield, divYield, targetAvg, targetUpsidePct, rating, ratingScore}
targetUpsidePct is computed vs the name's last committed close (hist) when available. Absent file -> no-op.
Idempotent; verified. Research only, not advice."""
import argparse, json, os, sys

KEEP = ("pe", "pb", "roe", "netMargin", "debtEq", "fcfYield", "divYield", "targetAvg", "rating", "ratingScore")


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


def fund_for(rec, close):
    if not rec:
        return None
    out = {k: rec.get(k) for k in KEEP if rec.get(k) is not None}
    if not out:
        return None
    ta = rec.get("targetAvg")
    if ta and close and close > 0:
        out["targetUpsidePct"] = round((ta / close - 1.0) * 100.0, 2)
    return out


def enrich(mm, fund_map, hist_dir):
    names = mm.get("names") or []
    done = 0
    for n in names:
        tk = (n.get("t") or n.get("sym") or "").upper()
        rec = fund_map.get(tk) if tk else None
        if not rec:
            continue
        f = fund_for(rec, _last_close(hist_dir, tk))
        if f:
            n["fund"] = f
            done += 1
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="marketmap.json")
    ap.add_argument("--fund", default="data/fundamentals.json")
    ap.add_argument("--hist", default="hist")
    a = ap.parse_args()
    if not os.path.exists(a.fund):
        sys.stderr.write("fundamentals_board: no %s — skipped (run fmp_bulk.py first)\n" % a.fund)
        return 0
    try:
        fm = json.load(open(a.fund))
        fm = {k: v for k, v in fm.items() if not k.startswith("_")}
        mm = json.load(open(a.map))
    except Exception as e:
        sys.stderr.write("fundamentals_board: read error (%s)\n" % str(e)[:80])
        return 1
    done = enrich(mm, fm, a.hist)
    tmp = a.map + ".tmp"
    with open(tmp, "w") as f:
        json.dump(mm, f, separators=(",", ":"))
    os.replace(tmp, a.map)
    sys.stderr.write("fundamentals_board: enriched %d names with FMP fundamentals -> %s\n" % (done, a.map))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
