#!/usr/bin/env python3
"""dirvr_board.py — POST-BUILD enrichment: land n["dirVR"], the selection-adjusted verdict on whether
the variance-ratio overlay (persist if VR>1 / fade if VR<1) actually BEATS following the directional
push alone. Walk-forward, no-lookahead, DSR+PBO gated (direction_vr_validate). The terminal reads this
to decide whether the Direction-Deck synthesis line may claim an edge or must soften to a directional
read. Non-destructive, keyless, verified. Research only."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import direction_vr_validate as DV


def dirvr_for(closes, r=5, h=10):
    c = [float(x) for x in (closes or []) if x is not None and float(x) > 0]
    if len(c) < 140:
        return None
    res = DV.validate(c, r=r, h=h)
    if res.get("verdict") == "INSUFFICIENT":
        return None
    m = res.get("mechanism", {})
    g = res.get("gate", {})
    return {"verdict": res["verdict"], "edgeSharpe": res.get("edgeSharpe"), "best": res.get("best"),
            "h": res.get("h"), "r": res.get("r"), "q": res.get("q"), "n": res.get("n"),
            "dsr": res.get("dsr"), "pbo": res.get("pbo"), "deployable": bool(g.get("deployable")),
            "persistPays": bool(m.get("persistPays")), "fadeReverses": bool(m.get("fadeReverses")),
            "note": res.get("note")}


def _load_hist(hist_dir, ticker):
    p = os.path.join(hist_dir, ticker + ".json")
    if not os.path.exists(p):
        return None
    try:
        rows = json.load(open(p))
        return [r[1] for r in rows if isinstance(r, (list, tuple)) and len(r) > 1 and r[1] is not None]
    except Exception:
        return None


def _is_equity(n):
    idx = n.get("idx") or []
    return bool(n.get("t")) and "FACTOR" not in idx and not n.get("etf")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--hist", default="hist")
    ap.add_argument("--r", type=int, default=5)
    ap.add_argument("--horizon", type=int, default=10)
    a = ap.parse_args()
    mm = json.load(open(a.map))
    names = mm.get("names") or mm.get("nodes") or []
    done = val = 0
    for n in names:
        if not _is_equity(n):
            continue
        closes = _load_hist(a.hist, n.get("t", ""))
        if not closes:
            continue
        block = dirvr_for(closes, r=a.r, h=a.horizon)
        if block:
            n["dirVR"] = block
            done += 1
            val += 1 if block["verdict"] == "VALIDATED" else 0
    tmp = a.map + ".tmp"
    json.dump(mm, open(tmp, "w"))
    os.replace(tmp, a.map)
    sys.stderr.write("dirvr_board: enriched %d names (%d VALIDATED) -> %s\n" % (done, val, a.map))


if __name__ == "__main__":
    main()
