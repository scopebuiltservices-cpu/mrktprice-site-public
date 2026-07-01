#!/usr/bin/env python3
"""direction_vr_validate.py — does conditioning a directional PUSH on the variance-ratio regime
(persist if VR>1, fade if VR<1) actually beat following the push alone? Walk-forward, no-lookahead,
selection-adjusted. This is the honest test behind the terminal's Direction-Deck synthesis line.

We cannot backtest the LIVE 15-minute intraday confirm from daily history, so we test the SAME
mechanism at the scale VR operates on (daily): a trailing r-day momentum sign is the reconstructable
proxy for a "confirmed push", and we ask whether the VR-sign overlay separates pushes that continue
from pushes that reverse.

At each day t (using ONLY closes[:t+1]):
  push_t   = sign(sum of last r log-returns)                         # the reconstructable "confirmed direction"
  vr_t,z_t = metrics.variance_ratio_stat(closes[:t+1], q)            # Lo-MacKinlay robust VR test
  persist  = |z_t|>=zc and vr_t>1 ;  fade = |z_t|>=zc and vr_t<1     # significance-gated regime
Realized forward (known only after t+h):  fwd_t = log(P_{t+h}/P_t)
Strategies (position -> pnl = pos*fwd_t):
  A baseline    : pos = push_t                       (follow the push unconditionally = "direction alone")
  B persist-gate: pos = push_t if persist else 0     (trade the push ONLY when VR says it persists)
  C persist/fade: pos = push_t if persist; -push_t if fade; else 0   (follow in persist, contra in fade)
Non-overlapping windows (stride=h) keep the return samples ~independent for the Sharpe/DSR/PBO stats.

Gate: best overlay is VALIDATED over baseline iff  edgeSharpe>0  AND  the persist-vs-fade mechanism is
significant  AND  promotion_gate(DSR, PBO) is deployable (Deflated-Sharpe selection-adjusted for the
3-way strategy choice + low Probability of Backtest Overfitting via CSCV). Otherwise NOT VALIDATED —
the deck then softens to a directional-only read. Pure stdlib. Research only, not advice.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics
import rank_engine
import validation_engine as VE

ZC = 1.6449  # |z|>=ZC ~ 10% two-sided significance (matches the live deck gate)


def _logret(c):
    return [math.log(c[i] / c[i - 1]) for i in range(1, len(c)) if c[i] > 0 and c[i - 1] > 0]


def _moments(x):
    n = len(x)
    if n < 2:
        return (x[0] if x else 0.0), 0.0, 0.0, 3.0
    m = sum(x) / n
    s2 = sum((v - m) ** 2 for v in x) / n
    sd = math.sqrt(s2)
    if sd <= 0:
        return m, 0.0, 0.0, 3.0
    sk = sum(((v - m) / sd) ** 3 for v in x) / n
    ku = sum(((v - m) / sd) ** 4 for v in x) / n
    return m, sd, sk, ku


def _stats(pnl, h):
    m, sd, sk, ku = _moments(pnl)
    sr = (m / sd) if sd > 0 else 0.0
    ann = sr * math.sqrt(252.0 / h) if h > 0 else sr
    return {"n": len(pnl), "mean": round(m, 6), "sd": round(sd, 6),
            "sharpe": round(sr, 4), "sharpeAnn": round(ann, 3), "skew": round(sk, 3), "kurt": round(ku, 3)}


def _welch_t(a, b):
    """Welch two-sample t on mean(a) vs mean(b). Returns (t, significant@~|t|>=1.98)."""
    if len(a) < 3 or len(b) < 3:
        return None, False
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    va = sum((x - ma) ** 2 for x in a) / (len(a) - 1)
    vb = sum((x - mb) ** 2 for x in b) / (len(b) - 1)
    se = math.sqrt(va / len(a) + vb / len(b))
    if se <= 0:
        return None, False
    t = (ma - mb) / se
    return round(t, 3), bool(abs(t) >= 1.98)


def validate(closes, r=5, h=10, q=None, zc=ZC, min_samples=12, warm=60):
    c = [float(x) for x in closes if x is not None and float(x) > 0]
    q = int(q or h)
    if q < 2:
        q = 2
    warm = max(warm, r + 1, q * 4 + 1)
    N = len(c)
    if N < warm + h + min_samples:
        return {"verdict": "INSUFFICIENT", "reason": "need >= %d closes, have %d" % (warm + h + min_samples, N),
                "r": r, "h": h, "q": q, "n": 0}
    lr = _logret(c)  # len N-1; lr[i] is the return INTO day i+1
    pA = []
    pB = []
    pC = []
    persist_follow = []  # push-follow pnl in persist windows (mechanism test)
    fade_follow = []     # push-follow pnl in fade windows
    rows = []            # per-period [A,B,C] for CSCV
    nPersist = nFade = 0
    t = warm
    while t + h < N:
        # push = sign of trailing r-day return, using ONLY info up to day t
        base = c[t - r]
        push = 0.0
        if base > 0 and c[t] > 0:
            tr = math.log(c[t] / base)
            push = 1.0 if tr > 0 else (-1.0 if tr < 0 else 0.0)
        st = metrics.variance_ratio_stat(c[:t + 1], q)  # no lookahead
        persist = fade = False
        if st and st.get("z") is not None:
            sig = abs(st["z"]) >= zc
            persist = sig and st["vr"] > 1.0
            fade = sig and st["vr"] < 1.0
        fwd = math.log(c[t + h] / c[t]) if (c[t] > 0 and c[t + h] > 0) else 0.0
        a = push * fwd
        b = (push * fwd) if persist else 0.0
        cc = (push * fwd) if persist else ((-push * fwd) if fade else 0.0)
        pA.append(a); pB.append(b); pC.append(cc); rows.append([a, b, cc])
        if push != 0.0:
            if persist:
                persist_follow.append(a); nPersist += 1
            elif fade:
                fade_follow.append(a); nFade += 1
        t += h  # non-overlapping forward windows
    n = len(pA)
    if n < min_samples:
        return {"verdict": "INSUFFICIENT", "reason": "only %d non-overlapping windows" % n,
                "r": r, "h": h, "q": q, "n": n}
    A = _stats(pA, h); B = _stats(pB, h); C = _stats(pC, h)
    # mechanism test: does following the push do better in persist than in fade?
    tstat, mech_sig = _welch_t(persist_follow, fade_follow)
    mean_persist = round(sum(persist_follow) / len(persist_follow), 6) if persist_follow else None
    mean_fade = round(sum(fade_follow) / len(fade_follow), 6) if fade_follow else None
    # best overlay by risk-adjusted return
    best = "B" if B["sharpe"] >= C["sharpe"] else "C"
    bestS = B if best == "B" else C
    edge_sharpe = round(bestS["sharpe"] - A["sharpe"], 4)
    edge_mean = round(bestS["mean"] - A["mean"], 6)
    # selection-adjusted stats on the best overlay (3-way strategy selection => n_trials=3)
    dsr = rank_engine.deflated_sharpe(bestS["sharpe"], bestS["n"], skew=bestS["skew"], kurt=bestS["kurt"], n_trials=3)
    pbo = VE.pbo_cscv(rows, S=6) if n >= 6 else None
    gate = VE.promotion_gate(dsr if dsr is not None else 0.0, pbo if pbo is not None else 1.0)
    validated = bool(edge_sharpe > 0 and mech_sig and gate["deployable"])
    verdict = "VALIDATED" if validated else "NOT VALIDATED"
    note = ("VR overlay separates continuation from reversal and beats direction-alone after DSR+PBO."
            if validated else
            "No selection-adjusted edge from the VR overlay over following the push alone; treat the deck's "
            "persist/fade as descriptive, not a proven edge.")
    return {"verdict": verdict, "r": r, "h": h, "q": q, "n": n,
            "strategies": {"A_baseline": A, "B_persistGate": B, "C_persistFade": C},
            "best": best, "edgeSharpe": edge_sharpe, "edgeMean": edge_mean,
            "mechanism": {"meanPersistFollow": mean_persist, "meanFadeFollow": mean_fade,
                          "nPersist": nPersist, "nFade": nFade, "t": tstat, "significant": mech_sig},
            "dsr": (round(dsr, 4) if dsr is not None else None),
            "pbo": (round(pbo, 4) if pbo is not None else None),
            "gate": gate, "note": note}


if __name__ == "__main__":
    import json
    import random
    rng = random.Random(0)
    c = [100.0]
    for _ in range(700):
        c.append(c[-1] * math.exp(rng.gauss(0, 0.012)))
    print(json.dumps(validate(c), indent=2))
