"""Append-only history of Black-Scholes option valuations + a slot for realized
trading outcomes, so the mrktprice equation can be calibrated on what actually
happened (variance-risk-premium / option-richness signal). Pure stdlib JSONL."""
import json, os, datetime

DEFAULT = os.environ.get("BS_HISTORY",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "bs_history.jsonl"))

def _now(): return datetime.datetime.utcnow().isoformat() + "Z"
def _ensure(p): os.makedirs(os.path.dirname(p), exist_ok=True)

def record(ticker, summary, contracts=None, top=6, path=None):
    """Log a valuation snapshot (summary + a few most-liquid contracts for audit)."""
    p = path or DEFAULT; _ensure(p)
    rec = {"ts": _now(), "kind": "snapshot", "ticker": ticker, "summary": summary}
    if contracts:
        rec["contracts"] = sorted([c for c in contracts if c.get("oi")],
                                  key=lambda c: -(c.get("oi") or 0))[:top]
    with open(p, "a") as f: f.write(json.dumps(rec, separators=(",", ":")) + "\n")
    return rec

def attach_outcome(ticker, ref_ts, realized, path=None):
    """Record what actually happened after a snapshot (e.g. realized fwd return,
    realized vol over the option's life) keyed to that snapshot's ts."""
    p = path or DEFAULT; _ensure(p)
    row = {"ts": _now(), "kind": "outcome", "ticker": ticker, "refTs": ref_ts, "outcome": realized}
    with open(p, "a") as f: f.write(json.dumps(row, separators=(",", ":")) + "\n")
    return row

def load(path=None):
    p = path or DEFAULT
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []

def calibration_summary(path=None):
    """Feed for the mrktprice equation: pair snapshots with later outcomes and
    measure whether 'rich/cheap vs model' predicted realized moves. Until outcomes
    accrue it reports coverage + the standing IV-vs-RV premium."""
    rows = load(path)
    snaps = [r for r in rows if r.get("kind") == "snapshot" and r.get("summary")]
    outs  = [r for r in rows if r.get("kind") == "outcome"]
    riches = [s["summary"].get("avgRichnessPct") for s in snaps if s["summary"].get("avgRichnessPct") is not None]
    # join outcomes to nearest prior snapshot of same ticker; correlate richness vs realized
    pairs = []
    for o in outs:
        prior = [s for s in snaps if s["ticker"] == o["ticker"] and s["ts"] <= o.get("refTs", o["ts"])]
        if prior:
            s = max(prior, key=lambda r: r["ts"]); rr = o["outcome"].get("fwdRet") if isinstance(o["outcome"], dict) else None
            ap = s["summary"].get("avgRichnessPct")
            if rr is not None and ap is not None: pairs.append((ap, rr))
    hit = None
    if pairs:
        # 'rich' options (ap>0) should precede weaker fwd returns -> negative association
        good = sum(1 for ap, rr in pairs if (ap > 0) == (rr < 0))
        hit = round(good / len(pairs), 3)
    return {"snapshots": len(snaps), "outcomes": len(outs), "pairs": len(pairs),
            "avgRichnessPct": round(sum(riches) / len(riches), 3) if riches else None,
            "richness_predicts_downmove_hitrate": hit}
