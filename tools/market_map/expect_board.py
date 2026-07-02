#!/usr/bin/env python3
"""expect_board.py — POST-BUILD enrichment: land per-name EXPECTED-vs-ACTUAL + projection accuracy.

Uses each name's committed hist/{T}.json (close + volume) and the champion cone sigma to write:

    n["expA"] = {
      band:     forward PREDICTION interval (labeled kind+level) from the current half-width,
      last:     most-recent COMPLETED-horizon reconciliation — expected vs actual price range,
                volatility, and volume, with per-metric ratio + verdict + containment,
      accuracy: walk-forward projection accuracy (containment ~ level, mean range/vol/volume ratios),
      H, level }

This makes "how accurate is the projection" a measured, per-name number and puts the half-width to
work as the yardstick for range/vol/volume surprises. Non-destructive (added field), keyless, verified.
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import expectations_engine as EE


def expect_for(closes, vols, H=21, level=0.90):
    c = [float(x) for x in (closes or []) if x is not None and float(x) > 0]
    if len(c) < 80:
        return None
    vols = [float(x) if x is not None else 0.0 for x in (vols or [])]
    sH = EE._champion_sigma(c, H)
    if not sH or sH <= 0:
        return None
    band = EE.expected_band(c[-1], sH, level)
    last = None
    if len(c) >= H + 40:
        t = len(c) - H - 1
        sHt = EE._champion_sigma(c[:t + 1], H)
        if sHt and sHt > 0:
            win = c[t:]
            rets = [math.log(win[i] / win[i - 1]) for i in range(1, len(win)) if win[i] > 0 and win[i - 1] > 0]
            base = EE.vol_baseline(vols[max(0, t - 60):t]) if len(vols) > t else None
            wv = vols[t:] if len(vols) > t else []
            last = EE.reconcile(c[t], sHt, level, win, rets, wv, base, c[-1])
    acc = EE.accuracy(c, vols, H=H, level=level)
    proj = EE.path_projection(c, vols, H=H)  # dispersion+persistence -> % on the expected path + top price/vol
    return {"band": band, "last": last, "accuracy": acc, "proj": proj, "H": H, "level": level}


def _load_hist(hist_dir, ticker):
    p = os.path.join(hist_dir, ticker + ".json")
    if not os.path.exists(p):
        return None, None
    try:
        rows = json.load(open(p))
        closes = [r[1] for r in rows if isinstance(r, (list, tuple)) and len(r) > 1 and r[1] is not None]
        vols = [(r[2] if len(r) > 2 and r[2] is not None else 0) for r in rows if isinstance(r, (list, tuple)) and len(r) > 1]
        return closes, vols
    except Exception:
        return None, None


def _is_equity(n):
    idx = n.get("idx") or []
    return bool(n.get("t")) and "FACTOR" not in idx and not n.get("etf")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--hist", default="hist")
    ap.add_argument("--horizon", type=int, default=21)
    ap.add_argument("--level", type=float, default=0.90)
    a = ap.parse_args()
    mm = json.load(open(a.map))
    names = mm.get("names") or mm.get("nodes") or []
    done = 0
    for n in names:
        if not _is_equity(n):
            continue
        closes, vols = _load_hist(a.hist, n.get("t", ""))
        if not closes:
            continue
        block = expect_for(closes, vols, H=a.horizon, level=a.level)
        if block:
            n["expA"] = block; done += 1
    tmp = a.map + ".tmp"
    json.dump(mm, open(tmp, "w"))
    os.replace(tmp, a.map)
    sys.stderr.write("expect_board: enriched %d names with expected-vs-actual + accuracy -> %s\n" % (done, a.map))


if __name__ == "__main__":
    main()
