import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mastery_engine as M

def test_composite_weighting():
    c = {"concepts": 1.0, "procedure": 1.0, "reasoning": 1.0, "transfer": 1.0, "selfmon": 1.0}
    assert abs(M.composite(c) - 100.0) < 1e-9
    half = {k: 0.5 for k in c}; assert abs(M.composite(half) - 50.0) < 1e-9
    print("  PASS  composite: all-1 ->100, all-0.5 ->50 (analytic weights renormalize)")

def test_mastery_full_pass():
    comp = {"concepts": 0.95, "procedure": 0.9, "reasoning": 0.9, "transfer": 0.88, "selfmon": 0.9}
    crit = {"noLeak": 0.95, "coverage": 0.9, "dsr": 0.85, "drift": 0.9}
    r = M.classify(comp, crit, n=800, initial_pass=True, delayed_pass=True)
    assert r["tier"] == "mastery" and r["deployable"] and r["band"] == "strong", r
    print("  PASS  high composite + criticals + two-confirmation + n=800 -> MASTERY (strong)")

def test_critical_override_blocks_mastery():
    comp = {"concepts": 0.99, "procedure": 0.99, "reasoning": 0.99, "transfer": 0.99, "selfmon": 0.99}
    crit = {"noLeak": 0.5, "coverage": 0.95}     # leakage flag (critical) below floor
    r = M.classify(comp, crit, n=800)
    assert r["tier"] == "novice" and not r["deployable"] and any("noLeak" in b for b in r["blockedBy"]), r
    print("  PASS  critical-component override: composite ~99 but noLeak=0.50 -> NOVICE (blocked)")

def test_two_confirmation_required():
    comp = {"concepts": 0.9, "procedure": 0.9, "reasoning": 0.9, "transfer": 0.9, "selfmon": 0.9}
    crit = {"noLeak": 0.9, "coverage": 0.9, "dsr": 0.85}
    r1 = M.classify(comp, crit, n=800, initial_pass=True, delayed_pass=False)
    assert r1["tier"] == "proficient" and "needs delayed re-confirm" in r1["whyNotMastery"], r1
    r2 = M.classify(comp, crit, n=800, initial_pass=True, delayed_pass=True)
    assert r2["tier"] == "mastery"
    print("  PASS  two-confirmation: OOS-only -> proficient (needs delayed); OOS+delayed -> mastery")

def test_proficient_and_novice():
    comp = {"concepts": 0.8, "procedure": 0.78, "reasoning": 0.75, "transfer": 0.74, "selfmon": 0.8}  # ~77
    r = M.classify(comp, {"noLeak": 0.8, "coverage": 0.7}, n=300)
    assert r["tier"] == "proficient" and r["band"] == "moderate", r
    low = {k: 0.5 for k in comp}
    rn = M.classify(low, {"noLeak": 0.8}, n=300)
    assert rn["tier"] == "novice"
    print("  PASS  mid composite -> proficient(moderate); low composite -> novice")

def test_confidence_bands_and_downgrade():
    assert M.confidence_band(20) == "insufficient" and M.confidence_band(300) == "moderate" and M.confidence_band(800) == "strong"
    assert M.confidence_band(800, se=0.3) != "strong"        # wide SE downgrades
    assert M.reclassify([90, 78, 75]) is True and M.reclassify([90, 88, 75]) is False
    print("  PASS  bands (n + SE); downward reclassify on 2 consecutive sub-maintenance checks")

if __name__ == "__main__":
    test_composite_weighting(); test_mastery_full_pass(); test_critical_override_blocks_mastery()
    test_two_confirmation_required(); test_proficient_and_novice(); test_confidence_bands_and_downgrade()
    print("\nALL MASTERY ENGINE TESTS PASSED")
