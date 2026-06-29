#!/usr/bin/env python3
"""news_sentiment.py — KEYLESS finance-domain sentiment scoring for headlines (headwind vs tailwind).

Plain-English lexicon scorer in the Loughran-McDonald tradition: a curated finance positive/negative word
list with negation handling, scored per headline and aggregated per company/sector/market with recency
decay. No model download, no API, pure stdlib -> runs anywhere, deterministic, unit-tested. The output is a
net sentiment in [-1, +1] plus tailwind/headwind magnitudes and the driving headlines, so the daily report
can say WHY a name has a wind at its back or in its face. Research only; not investment advice."""
import math, re, datetime as dt

POS = set("""beat beats beating exceeded exceed exceeds outperform outperformed upgrade upgraded raise raised
raises strong strength growth grow grows gains gain profit profitable record surge surged rally rallied soar
soared jump jumped rose rise rises boost boosted bullish optimistic accelerate accelerated expansion expand
robust momentum recovery rebound rebounded breakthrough approval approved win won wins awarded partnership
buyback repurchase milestone leading leader innovative efficient improve improved improving opportunity
favorable positive success successful secured achieve achieved premium demand upside confident confidence
resilient durable tailwind tailwinds outpaced beat-and-raise expands surpass surpassed accretive""".split())

NEG = set("""miss missed misses missing downgrade downgraded cut cuts lowered lower weak weakness decline
declined declines drop dropped fall fell falls plunge plunged slump slumped loss losses lawsuit sued
investigation probe fraud recall recalled bankruptcy bankrupt default layoff layoffs restructuring warning
warned warns concern concerns risk risks risky bearish pessimistic slowdown slowing headwind headwinds
shortfall disappointing disappoint disappointed underperform underperformed fines penalty delay delayed halt
halted suspended downturn recession selloff sell-off crash struggle struggled struggling deteriorate
deteriorating impairment writedown write-down dilution dilutive breach hack outage disruption scandal resign
resigned ousted slash slashed plummet plummeted tumble tumbled subpoena litigation""".split())

NEGATORS = set("not no never without fails failed fail lack lacks lacking hardly barely n't cannot".split())
_TOK = re.compile(r"[a-z][a-z'\-]+")


def score_text(text):
    """One headline/snippet -> {pos, neg, polarity}. Negation within 3 prior tokens flips a hit's sign."""
    toks = _TOK.findall((text or "").lower())
    pos = neg = 0
    for i, w in enumerate(toks):
        neg_ctx = any(t in NEGATORS for t in toks[max(0, i - 3):i])
        if w in POS:
            (neg if neg_ctx else pos).__class__  # no-op for clarity
            if neg_ctx: neg += 1
            else: pos += 1
        elif w in NEG:
            if neg_ctx: pos += 1
            else: neg += 1
    tot = pos + neg
    pol = (pos - neg) / tot if tot else 0.0
    return {"pos": pos, "neg": neg, "polarity": round(pol, 4)}


def _age_days(d, asof):
    try:
        return max(0.0, (dt.date.fromisoformat(str(asof)[:10]) - dt.date.fromisoformat(str(d)[:10])).days)
    except Exception:
        return 0.0


def score_headlines(headlines, asof=None, halflife=3.0):
    """Aggregate a list of {title, (summary), date} -> recency-decayed net sentiment + drivers.
    Returns {n, net, tailwind, headwind, label, topPos, topNeg}. net in [-1,1]."""
    asof = asof or dt.date.today().isoformat()
    rows = []
    wsum = tw = hw = 0.0
    for h in (headlines or []):
        txt = ((h.get("title") or "") + ". " + (h.get("summary") or h.get("text") or "")).strip()
        s = score_text(txt)
        w = 0.5 ** (_age_days(h.get("date") or h.get("publishedDate"), asof) / max(halflife, 1e-6))
        rows.append((s["polarity"], w, h.get("title") or txt[:80], s))
        wsum += w
        if s["polarity"] > 0: tw += w * s["polarity"]
        elif s["polarity"] < 0: hw += w * (-s["polarity"])
    if not rows or wsum <= 0:
        return {"n": len(rows), "net": 0.0, "tailwind": 0.0, "headwind": 0.0, "label": "no-news", "topPos": [], "topNeg": []}
    net = sum(p * w for p, w, _, _ in rows) / wsum
    label = "tailwind" if net > 0.15 else ("headwind" if net < -0.15 else "mixed/neutral")
    pos_sorted = sorted([r for r in rows if r[0] > 0], key=lambda r: -r[0] * r[1])
    neg_sorted = sorted([r for r in rows if r[0] < 0], key=lambda r: r[0] * r[1])
    return {"n": len(rows), "net": round(net, 4), "tailwind": round(tw / wsum, 4), "headwind": round(hw / wsum, 4),
            "label": label, "topPos": [r[2] for r in pos_sorted[:3]], "topNeg": [r[2] for r in neg_sorted[:3]]}


def aggregate(per_name_scores, weights=None):
    """Roll per-company net sentiment up to a sector/market net (optionally market-cap weighted)."""
    items = [(k, v) for k, v in (per_name_scores or {}).items() if isinstance(v, dict) and v.get("n", 0) > 0]
    if not items:
        return {"net": 0.0, "n": 0, "label": "no-news"}
    if weights:
        ws = sum(max(0.0, weights.get(k, 0.0)) for k, _ in items) or 1.0
        net = sum(v["net"] * max(0.0, weights.get(k, 0.0)) for k, v in items) / ws
    else:
        net = sum(v["net"] for _, v in items) / len(items)
    label = "tailwind" if net > 0.10 else ("headwind" if net < -0.10 else "mixed/neutral")
    return {"net": round(net, 4), "n": len(items), "label": label}
