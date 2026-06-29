#!/usr/bin/env python3
"""regime_board.py — POST-BUILD enrichment: per-name VOLATILITY REGIME via a 2-state Gaussian HMM (#5).

External-enrichment pattern (like crowding_board.py / event_board.py): for each name, fit the verified
2-state Gaussian HMM (regime_ic.gaussian_hmm_2state, states ordered calm=0/stress=1) on its committed
daily log-returns, run Viterbi, and read the CURRENT state + posterior. Writes:
    n["reg"] = {state:"calm"|"stress", sep, pStress, muCalmAnn, muStressAnn, n}
STRESS is only declared with GENUINE variance separation (a single-regime series produces a degenerate
HMM split whose labels are arbitrary). A name in a real high-variance stress regime should be sized down
and its bands widened. Pure stdlib; verified against planted structure. Research only, not advice."""
import argparse, json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regime_ic as RG

ANN = 252.0


def _logrets(closes):
    r = []
    for i in range(1, len(closes)):
        if closes[i] > 0 and closes[i - 1] > 0:
            r.append(math.log(closes[i] / closes[i - 1]))
    return r


def regime_for(closes, iters=40, tail=400):
    """Return n['reg'] from the last `tail` log-returns, or None if too short."""
    r = _logrets(closes)
    if len(r) < 80:
        return None
    x = r[-tail:]
    hmm = RG.gaussian_hmm_2state(x, iters=iters)
    path = RG.viterbi_path(x, hmm)
    state = path[-1]
    gamma = hmm.get("gamma") or []
    p_stress = gamma[-1][1] if gamma else (1.0 if state == 1 else 0.0)
    var = hmm["var"]; mu = hmm["mu"]
    vr = (var[1] / var[0]) if var[0] > 0 else None
    # STRESS requires the current Viterbi state = stress, GENUINE variance separation (>=1.8x), and a
    # confident posterior. Without separation the two-state split is degenerate -> report calm.
    sep_ok = (vr is not None and vr >= 1.8)
    is_stress = bool(state == 1 and sep_ok and p_stress >= 0.55)
    return {
        "state": "stress" if is_stress else "calm",
        "sep": round(vr, 2) if vr is not None else None,
        "pStress": round(p_stress, 3),
        "muCalmAnn": round(mu[0] * ANN * 100.0, 1),
        "muStressAnn": round(mu[1] * ANN * 100.0, 1),
        "n": len(x),
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
            reg = regime_for(closes)
        except Exception:
            reg = None
        if reg:
            n["reg"] = reg
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
        sys.stderr.write("regime_board: cannot read %s (%s)\n" % (a.map, str(e)[:80]))
        return 1
    done = enrich(mm, a.hist)
    tmp = a.map + ".tmp"
    with open(tmp, "w") as f:
        json.dump(mm, f, separators=(",", ":"))
    os.replace(tmp, a.map)
    sys.stderr.write("regime_board: enriched %d names with per-name HMM regime -> %s\n" % (done, a.map))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
