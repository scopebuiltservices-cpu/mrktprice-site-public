#!/usr/bin/env python3
"""Tests for limitations.py — the per-artifact 'what this does not prove' block. Run: python3 test_limitations.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import limitations as lm

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

mm = {"schemaVersion": "2.1", "asof": "2026-06-30", "names": [{"t": "AAA"}]}
out = lm.enrich(dict(mm))
ok("limitations block added", "limitations" in out, list(out))
L = out["limitations"]
ok("whatThisDoesNotProve is a non-trivial list", isinstance(L["whatThisDoesNotProve"], list) and len(L["whatThisDoesNotProve"]) >= 5, L)
ok("claimStrength rubric has all 5 tiers", set(L["claimStrength"]) == {"proxy", "heuristic", "inferential", "valuation-grade", "audited-release"}, L["claimStrength"])
ok("not-advice note present", "not investment advice" in L["note"].lower(), L["note"])
ok("asof threaded from payload", L["asof"] == "2026-06-30", L["asof"])
ok("schema tag present", L["schema"] == "limitations/1", L)
ok("payload otherwise untouched", out["names"] == mm["names"] and out["schemaVersion"] == "2.1", out)

# honest content: survivorship + PIT + not-causal are explicitly called out (the audit's core caveats)
blob = " ".join(L["whatThisDoesNotProve"]).lower()
ok("survivorship caveat present", "survivorship" in blob, blob[:80])
ok("point-in-time caveat present", "point-in-time" in blob or "pit" in blob, blob[:80])
ok("associational/not-causal caveat present", "associational" in blob or "not causal" in blob or "causal" in blob, blob[:80])

# idempotent
out2 = lm.enrich(dict(out))
ok("idempotent re-stamp", out2["limitations"]["whatThisDoesNotProve"] == L["whatThisDoesNotProve"], "changed")

print("\n" + ("ALL LIMITATIONS TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
