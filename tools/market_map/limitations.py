#!/usr/bin/env python3
"""limitations.py — stamp every published artifact with an honest "what this does NOT prove" block.

Audit ask (Docs P3 #98 + claim-strength rubric #95): "give each artifact a single paragraph called
'What this does not prove' to stop parity and validation from being oversold," and tag claims by
strength (proxy / heuristic / inferential / valuation-grade / audited-release).

This post-build enricher injects marketmap.json["limitations"] = {whatThisDoesNotProve:[...],
claimStrength:{...}, asof}. It is idempotent (re-running overwrites the same block) and additive
(touches nothing else). Pure stdlib. Verified. Research only — NOT investment advice.

CLI: python3 limitations.py --map marketmap.json
"""
import argparse, json, os, sys, datetime as dt

WHAT_THIS_DOES_NOT_PROVE = [
    "Forecasts are STATISTICAL, not advice. Calibrated intervals state how often outcomes have landed "
    "inside the band historically; they do not promise the next move. This is research/education only.",
    "Coverage is MARGINAL at the horizon level. Regime-conditioned conformal pools are reported where "
    "sample permits, but the headline guarantee is pooled marginal coverage, not regime-conditional validity.",
    "Pooled skill is UPWARD-BIASED by survivorship: the universe is CURRENT constituents; delisted names "
    "are absent, so historical hit-rates overstate what a live, point-in-time strategy would have achieved.",
    "Fundamentals (P/E, P/B, tangible book, targets, estimates) are CURRENT-VINTAGE TTM/consensus, NOT "
    "point-in-time; they must not be fed into the no-lookahead ledger/IC without PIT gating.",
    "Macro/factor betas are ASSOCIATIONAL, not causal — they describe co-movement, not a mechanism, and "
    "can break in regime change. The real-rate L/S/C is a 5/10/30 proxy, NOT an estimated Nelson-Siegel model.",
    "Cross-language (Py↔JS) parity proves the two implementations AGREE; it does not prove the shared "
    "model is correct. Tests pin behavior on planted structure, not real-world predictive power.",
    "Backtested or deflated-Sharpe edge is IN-SAMPLE evidence after multiple testing; it is not a "
    "guarantee of future edge. Deflation flagged 'provisional' when the trial-dispersion was not measured.",
    "Numbers can be STALE or DEGRADED. Check dataHealth + the per-source timestamps before trusting a row; "
    "a build can publish the last good artifact if a live feed failed.",
]

CLAIM_STRENGTH = {
    "proxy": "a hand-built stand-in for a quantity we did not estimate (e.g. the 5/10/30 real-rate L/S/C).",
    "heuristic": "a rule-of-thumb signal without a formal inferential guarantee.",
    "inferential": "backed by a stated test/interval with explicit assumptions (HAC t-stats, conformal coverage, DSR).",
    "valuation-grade": "priced under explicit conventions (zero-curve discount factors, day-count) — used for option/pricing math.",
    "audited-release": "passed the full gate ladder (schema + invariants + drift + calibration + multiple-testing) and is provenance-stamped in model_registry.jsonl.",
}


def block(asof=None):
    return {
        "whatThisDoesNotProve": WHAT_THIS_DOES_NOT_PROVE,
        "claimStrength": CLAIM_STRENGTH,
        "asof": asof or dt.date.today().isoformat(),
        "note": "Research/education only — not investment advice.",
        "schema": "limitations/1",
    }


def enrich(mm, asof=None):
    mm["limitations"] = block(asof or mm.get("asof"))
    return mm


def main():
    ap = argparse.ArgumentParser(description="Stamp marketmap.json with a 'what this does not prove' block.")
    ap.add_argument("--map", default="marketmap.json")
    a = ap.parse_args()
    if not os.path.exists(a.map):
        sys.stderr.write("limitations: %s not found — skipped\n" % a.map)
        return 0
    try:
        mm = json.load(open(a.map))
    except Exception as e:
        sys.stderr.write("limitations: cannot read %s (%s)\n" % (a.map, str(e)[:80]))
        return 1
    enrich(mm)
    tmp = a.map + ".tmp"
    with open(tmp, "w") as f:
        json.dump(mm, f, separators=(",", ":"))
    os.replace(tmp, a.map)
    sys.stderr.write("limitations: stamped %d 'what this does not prove' points -> %s\n" % (
        len(WHAT_THIS_DOES_NOT_PROVE), a.map))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
