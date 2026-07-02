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


def expect_for(closes, vols, H=21, level=0.90, highs=None, lows=None):
    c = [float(x) for x in (closes or []) if x is not None and float(x) > 0]
    if len(c) < 80:
        return None
    vols = [float(x) if x is not None else 0.0 for x in (vols or [])]
    sH = EE._champion_sigma(c, H, highs=highs, lows=lows)   # range-aware (Parkinson) when H/L present
    if not sH or sH <= 0:
        return None
    band = EE.expected_band(c[-1], sH, level)
    bandBoot = EE.expected_band_boot(c[-1], c, level=level, H=H)   # dependence-aware (stationary bootstrap) endpoint PI
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
    proj = EE.path_projection(c, vols, H=H, highs=highs, lows=lows)  # dispersion+persistence -> % on the expected path + top price/vol
    return {"band": band, "bandBoot": bandBoot, "last": last, "accuracy": acc, "proj": proj, "H": H, "level": level}


def _load_hist(hist_dir, ticker):
    p = os.path.join(hist_dir, ticker + ".json")
    if not os.path.exists(p):
        return None, None
    try:
        rows = json.load(open(p))
        closes = []; vols = []; highs = []; lows = []; hl = 0
        for r in rows:
            if not (isinstance(r, (list, tuple)) and len(r) > 1 and r[1] is not None):
                continue
            closes.append(r[1])
            vols.append(r[2] if len(r) > 2 and r[2] is not None else 0)
            h = r[3] if len(r) > 3 and r[3] is not None else None
            lw = r[4] if len(r) > 4 and r[4] is not None else None
            highs.append(h if h is not None else r[1]); lows.append(lw if lw is not None else r[1])
            if h is not None and lw is not None:
                hl += 1
        # only expose H/L when the series actually carries real intraday range (>=60% of rows)
        hv, lv = (highs, lows) if (closes and hl >= 0.6 * len(closes)) else (None, None)
        return closes, vols, hv, lv
    except Exception:
        return None, None, None, None


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
        closes, vols, highs, lows = _load_hist(a.hist, n.get("t", ""))
        if not closes:
            continue
        block = expect_for(closes, vols, H=a.horizon, level=a.level, highs=highs, lows=lows)
        if block:
            n["expA"] = block; done += 1
    tmp = a.map + ".tmp"
    json.dump(mm, open(tmp, "w"))
    os.replace(tmp, a.map)
    sys.stderr.write("expect_board: enriched %d names with expected-vs-actual + accuracy -> %s\n" % (done, a.map))


if __name__ == "__main__":
    main()
