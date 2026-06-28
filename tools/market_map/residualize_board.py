#!/usr/bin/env python3
"""residualize_board.py — POST-BUILD enrichment: strip hidden factor bets from each name (Fama-French).

External-enrichment pattern (no surgery in build_market_map.py): reads marketmap.json + hist/<T>.json
closes + the keyless FF factor cache, time-series-regresses each name's EXCESS returns on the 6 FF
factors, and writes a compact `fac` block per name:
    n["fac"] = {"b":{MktRF,SMB,HML,RMW,CMA,Mom}, "r2", "expPct", "n"}
where expPct = H * sum_k beta_k * lambda_k * 100  (the factor-EXPLAINED expected return over the horizon,
as a percent). The board nets this out of its raw alpha:  factor-neutral alpha = alpha_raw - fac.expPct.
Idempotent; safe to re-run. Verified against a planted fixture.

CLI: python3 residualize_board.py --map marketmap.json --hist hist --factors data/ff_factors.csv --horizon 21"""
import argparse, json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import residualize_engine as RE
from factor_returns import load_factor_csv


def _ret_series(rows):
    """hist rows [[date 'YYYY-MM-DD', close, vol], ...] -> [(yyyymmdd:int, logret)] from close to close."""
    out = []
    prev = None
    for r in rows:
        try:
            d = int(str(r[0])[:10].replace("-", ""))
            c = float(r[1])
        except Exception:
            continue
        if c <= 0:
            prev = None
            continue
        if prev is not None and prev[1] > 0:
            out.append((d, math.log(c / prev[1])))
        prev = (d, c)
    return out


def enrich(mm, hist_dir, factor_rows, horizon=21, min_obs=60, premia_halflife=252):
    fac_by_date = {r["date"]: r for r in factor_rows}
    premia = RE.factor_premia(factor_rows, halflife=premia_halflife)
    names = mm.get("names") or mm.get("nodes") or []
    done = 0
    for n in names:
        tkr = n.get("t") or n.get("sym") or n.get("ticker")
        if not tkr:
            continue
        path = os.path.join(hist_dir, "%s.json" % tkr)
        if not os.path.exists(path):
            continue
        try:
            h = json.load(open(path))
        except Exception:
            continue
        series = _ret_series(h.get("rows") or [])
        excess, frows = [], []
        for d, lr in series:
            fr = fac_by_date.get(d)
            if not fr or fr.get("RF") is None:
                continue
            if any(fr.get(f) is None for f in RE.FACTORS):
                continue
            excess.append(lr - fr["RF"])
            frows.append(fr)
        if len(excess) < min_obs:
            continue
        fit = RE.factor_betas(excess, frows)
        exp = RE.residualize(0.0, fit["betas"], premia, horizon)   # factorExpected only (alpha_raw=0)
        n["fac"] = {
            "b": {f: round(fit["betas"][f], 4) for f in RE.FACTORS},
            "r2": round(fit["r2"], 4),
            "expPct": round(-exp["muResid"] * 100.0, 4),            # = factorExpected*100, as %
            "n": fit["n"],
        }
        done += 1
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="marketmap.json")
    ap.add_argument("--hist", default="hist")
    ap.add_argument("--factors", default="data/ff_factors.csv")
    ap.add_argument("--horizon", type=int, default=21)
    a = ap.parse_args()
    if not os.path.exists(a.factors):
        sys.stderr.write("residualize_board: no factor cache at %s — skipped (keyless FF not fetched)\n" % a.factors)
        return 0
    factor_rows = load_factor_csv(a.factors)
    if not factor_rows:
        sys.stderr.write("residualize_board: empty factor cache — skipped\n")
        return 0
    try:
        mm = json.load(open(a.map))
    except Exception as e:
        sys.stderr.write("residualize_board: cannot read %s (%s)\n" % (a.map, str(e)[:80]))
        return 1
    done = enrich(mm, a.hist, factor_rows, a.horizon)
    tmp = a.map + ".tmp"
    with open(tmp, "w") as f:
        json.dump(mm, f, separators=(",", ":"))
    os.replace(tmp, a.map)
    sys.stderr.write("residualize_board: enriched %d names with FF factor exposures -> %s\n" % (done, a.map))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
