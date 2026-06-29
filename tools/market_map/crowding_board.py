#!/usr/bin/env python3
"""crowding_board.py — POST-BUILD enrichment: fold short-side CROWDING into a per-name number (#7).

External-enrichment pattern (no surgery in build_market_map.py, like event_board.py): reads the SEC
fails-to-deliver block already in marketmap.json (n["short"].fails, from short_squeeze.py) plus the name's
committed price/volume history (hist/{T}.json rows [date,close,vol]) and market cap, then computes via the
verified crowding_engine:
    days_to_cover = fails / ADV(21)                         # SEC FTD shares / avg daily volume  (REAL)
    siPct         = fails / (mcap / last_close)             # FTD-based short-interest proxy (conservative)
    utilization   = clamp(dtc / 10)                         # borrow-tightness proxy until a lending feed exists
    penalty       = crowding_penalty(siPct, ownership=0, utilization)   # expected-return % to subtract from mu
and writes  n["cr"] = {dtc, siPct, util, borrowFee, pen, squeeze, src}.
FTD underestimates true short interest, so these are a CONSERVATIVE FLOOR — they go near-zero for liquid
mega-caps (correct: not crowded) and light up only genuinely shorted, thinly-traded names. Ownership HHI
stays 0 until per-holder 13F is wired (n["inst"] carries only a total). Idempotent; verified. Research only."""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crowding_engine as CR


def _adv(rows, k=21):
    """Average daily share volume over the last k sessions from hist rows [date, close, vol]."""
    vs = [r[2] for r in rows[-k:] if len(r) > 2 and r[2]]
    return (sum(vs) / len(vs)) if vs else None


def _last_close(rows):
    for r in reversed(rows):
        if len(r) > 1 and r[1]:
            try:
                return float(r[1])
            except Exception:
                continue
    return None


def crowding_for(short, rows, mcap):
    """Return the n['cr'] block, or None if there is no short/FTD signal to score."""
    if not short:
        return None
    fails = float(short.get("fails") or 0.0)
    if fails <= 0:
        return None
    adv = _adv(rows or [])
    dtc = CR.days_to_cover(fails, adv) if adv else None
    close = _last_close(rows or [])
    si = None
    if mcap and close and close > 0:
        shares_out = float(mcap) / close                    # mcap is raw USD; shares = cap / price
        if shares_out > 0:
            si = fails / shares_out                          # fraction of shares outstanding (FTD floor)
    util = max(0.0, min(0.95, (dtc / 10.0))) if dtc is not None else 0.0
    pen = CR.crowding_penalty(si or 0.0, 0.0, util)          # ownership HHI unavailable keyless -> 0
    fee = CR.utilization_proxy_fee(util)
    lvl = short.get("level"); trd = short.get("trend")
    # squeeze is a SINGLE-NAME concept: require a real equity short-interest % (si is None for ETFs, which
    # have no mcap-derived share count) so currency/bond/commodity ETFs don't false-trip on FTD alone.
    squeeze = bool(si is not None and ((dtc is not None and dtc >= 3.0) or (lvl == "elevated" and trd == "rising")))
    return {
        "dtc": round(dtc, 3) if dtc is not None else None,
        "siPct": round(si * 100.0, 4) if si is not None else None,
        "util": round(util, 3),
        "borrowFee": round(fee, 2),
        "pen": round(pen, 4),
        "squeeze": squeeze,
        "lvl": lvl, "trend": trd,
        "src": "SEC FTD + ADV(21)" + ("+mcap" if si is not None else ""),
    }


def enrich(mm, hist_dir):
    names = mm.get("names") or []
    done = 0
    for n in names:
        tk = n.get("t") or n.get("sym")
        short = n.get("short")
        if not (tk and short):
            continue
        rows = []
        p = os.path.join(hist_dir, "%s.json" % tk)
        if os.path.exists(p):
            try:
                h = json.load(open(p))
                rows = h.get("rows") if isinstance(h, dict) else h
            except Exception:
                rows = []
        cr = crowding_for(short, rows or [], n.get("mcap"))
        if cr:
            n["cr"] = cr
            done += 1
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="marketmap.json")
    ap.add_argument("--hist", default="hist")
    a = ap.parse_args()
    try:
        mm = json.load(open(a.map))
    except Exception as e:
        sys.stderr.write("crowding_board: cannot read %s (%s)\n" % (a.map, str(e)[:80]))
        return 1
    done = enrich(mm, a.hist)
    tmp = a.map + ".tmp"
    with open(tmp, "w") as f:
        json.dump(mm, f, separators=(",", ":"))
    os.replace(tmp, a.map)
    sys.stderr.write("crowding_board: enriched %d names with days-to-cover + crowding penalty -> %s\n" % (done, a.map))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
