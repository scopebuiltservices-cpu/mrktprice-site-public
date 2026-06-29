#!/usr/bin/env python3
"""proj_board.py — POST-BUILD enrichment: per-name no-lookahead FORWARD PROJECTION (#4/#8).

External-enrichment pattern (like crowding_board.py / regime_board.py): for each name, form the SAME
server forecast the universe-wide learning ledger uses — proj_server.blend_drift (OU mean-reversion +
EMA-momentum blend) over the committed closes — then attach a horizon projClose, its % vs price-now, the
forecast sigma, and the calibrated P(price_H > price_now) from proj_engine. Writes:
    n["pj"] = {h, projClose, projPct, probUp, sigmaHPct}
This is the verified, reproducible projection (no lookahead) that the projClose-vs-priceNow learning is
trained on, so the board's forward read is consistent with what's being scored. Verified. Research only."""
import argparse, json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proj_server as PS
import proj_engine as PE

H = 21


def _logrets(closes):
    return [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
            if closes[i] > 0 and closes[i - 1] > 0]


def proj_for(closes, h=H, lookback=60):
    """Return n['pj'] from the committed closes, or None if too short."""
    if len(closes) < 80:
        return None
    price_now = closes[-1]
    if price_now <= 0:
        return None
    mu_H = PS.blend_drift(closes, h)                       # expected h-step log-return (OU/EMA blend)
    r = _logrets(closes)[-lookback:]
    if len(r) < 20:
        return None
    mean = sum(r) / len(r)
    sd_daily = math.sqrt(sum((x - mean) ** 2 for x in r) / (len(r) - 1)) or 1e-6
    sigma_H = sd_daily * math.sqrt(h)
    proj_close = price_now * math.exp(mu_H)
    return {
        "h": h,
        "projClose": round(proj_close, 4),
        "projPct": round((math.exp(mu_H) - 1.0) * 100.0, 2),
        "probUp": round(PE.prob_above_now(mu_H, sigma_H), 3),
        "sigmaHPct": round(sigma_H * 100.0, 2),
    }


def enrich(mm, hist_dir):
    names = mm.get("names") or []
    done = 0
    for n in names:
        tk = n.get("t") or n.get("sym")
        if not tk:
            continue
        p = os.path.join(hist_dir, "%s.json" % tk)
        if not os.path.exists(p):
            continue
        try:
            h = json.load(open(p))
            rows = h.get("rows") if isinstance(h, dict) else h
            closes = [float(x[1]) for x in rows if x and len(x) > 1 and x[1] is not None]
        except Exception:
            continue
        try:
            pj = proj_for(closes)
        except Exception:
            pj = None
        if pj:
            n["pj"] = pj
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
        sys.stderr.write("proj_board: cannot read %s (%s)\n" % (a.map, str(e)[:80]))
        return 1
    done = enrich(mm, a.hist)
    tmp = a.map + ".tmp"
    with open(tmp, "w") as f:
        json.dump(mm, f, separators=(",", ":"))
    os.replace(tmp, a.map)
    sys.stderr.write("proj_board: enriched %d names with server forward projection -> %s\n" % (done, a.map))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
