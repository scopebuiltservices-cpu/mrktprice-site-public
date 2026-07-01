#!/usr/bin/env python3
"""coneeval_board.py — POST-BUILD enrichment: per-name walk-forward cone-coverage backtest (Solution A).

Runs cone_eval.backtest on each name's committed price history (hist/{T}.json) and writes:

    n["coneEval"] = {recommend, reason, H, level, n,
                     sources: {name: {cov, iS, calErr, hw}}}

This turns the eventual cone-sigma upgrade (champion sqrt(H*VR) -> arbiter blend) into an EVIDENCE-
BACKED, per-name flip: the payload now carries which sigma source actually covers best out-of-sample,
so a swap is a one-line, auditable decision instead of a leap of faith. NON-DESTRUCTIVE: adds a field,
does not change the live cone sigma or any golden-tested path. Keyless, idempotent, verified.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cone_eval as CE


def coneeval_for(closes, H=21, level=0.90, min_train=60, stride=5, cap=360):
    """Pure: closes -> the n['coneEval'] block (or None if too little history). Network-free."""
    c = [float(x) for x in (closes or []) if x is not None and float(x) > 0]
    if len(c) < min_train + H + 10:
        return None
    c = c[-cap:]                              # bound walk-forward cost per name
    r = CE.backtest(c, H=H, level=level, min_train=min_train, stride=stride)
    if not r.get("recommend"):
        return None
    src = {k: {"cov": v.get("coverage"), "iS": v.get("intervalScore"),
               "calErr": v.get("calErr"), "hw": v.get("meanHalfWidth")}
           for k, v in r["sources"].items() if v.get("n")}
    return {"recommend": r["recommend"], "reason": r["reason"], "H": r["H"],
            "level": r["level"], "n": r["n"], "sources": src}


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
    ap.add_argument("--horizon", type=int, default=21)
    ap.add_argument("--level", type=float, default=0.90)
    ap.add_argument("--stride", type=int, default=5)
    a = ap.parse_args()
    mm = json.load(open(a.map))
    names = mm.get("names") or mm.get("nodes") or []
    done = 0
    for n in names:
        if not _is_equity(n):
            continue
        closes = _load_hist(a.hist, n.get("t", ""))
        if not closes:
            continue
        block = coneeval_for(closes, H=a.horizon, level=a.level, stride=a.stride)
        if block:
            n["coneEval"] = block; done += 1
    tmp = a.map + ".tmp"
    json.dump(mm, open(tmp, "w"))
    os.replace(tmp, a.map)
    sys.stderr.write("coneeval_board: enriched %d names with cone-coverage backtest -> %s\n" % (done, a.map))


if __name__ == "__main__":
    main()
