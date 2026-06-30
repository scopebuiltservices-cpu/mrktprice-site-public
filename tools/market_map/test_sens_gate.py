#!/usr/bin/env python3
"""Regression test: the macro-sensitivity live-contribution must be SIGNIFICANCE-GATED.

report_engine.sensitivities_block builds each driver's live implied contribution (impliedPct = sens ×
driver's current σ-move) from the build's own n['macro3'] / n['deps'] (which already carry sig/p/stab/weak).
The DEFENSIBLE headline (liveContribPct) must sum ONLY statistically-significant, stable, non-weak drivers,
so insignificant macro betas are shown for transparency (grossContribPct) but never laundered into a
confident attribution. Auto-discovered by run-checks.sh / verify_all.sh.

_sens_row resolves a driver's current move via the module-level macro_moves (imported as report_engine._MM),
so we monkeypatch that with a deterministic stub (sigma per factor) to make impliedPct exact and testable."""
import report_engine as RE


class _StubMM:
    """Stand-in for macro_moves: lookup(factor, moves) -> {movePct, sigma}."""
    def __init__(self, m):
        self.m = m

    def lookup(self, f, moves):
        return self.m.get(f)


def _run(macro3, stub_map):
    n = {"t": "TST", "deps": [], "macro3": macro3, "macroR2": 39, "drv": "Copper"}
    orig = RE._MM
    try:
        RE._MM = _StubMM(stub_map)
        return RE.sensitivities_block(n, moves=True)   # truthy 'moves' activates the lookup branch
    finally:
        RE._MM = orig


def test_significance_gate():
    macro3 = {
        "rate": {"f": "10Y yield", "sens": -0.34, "sig": False, "weak": True, "stab": "stable", "dir": "against"},
        "top": [
            {"f": "Copper", "sens": 1.0, "sig": True,  "weak": False, "stab": "stable", "dir": "with"},
            {"f": "Gold",   "sens": 0.9, "sig": True,  "weak": False, "stab": "stable", "dir": "with"},
            {"f": "Crude",  "sens": 0.6, "sig": False, "weak": True,  "stab": "stable", "dir": "with"},
        ],
    }
    stub = {"Copper": {"movePct": 2.54, "sigma": 2.0}, "Gold": {"movePct": 1.02, "sigma": 1.0},
            "Crude": {"movePct": -1.66, "sigma": -1.5}, "10Y yield": {"movePct": 1.67, "sigma": 1.5}}
    b = _run(macro3, stub)
    # impliedPct: Copper 1.0*2.0=2.0, Gold 0.9*1.0=0.9 (both sig) ; Crude 0.6*-1.5=-0.9, rate -0.34*1.5=-0.51 (insig)
    assert b["nDrivers"] == 4 and b["nSigDrivers"] == 2, b
    assert abs(b["liveContribPct"] - 2.9) < 1e-6, b                      # ONLY the 2 significant drivers
    assert abs(b["grossContribPct"] - round(2.0 + 0.9 - 0.9 - 0.51, 2)) < 1e-6, b   # all 4
    assert b["liveContribPct"] != b["grossContribPct"]                   # the gate must change the headline
    assert b["macroExplainedShare"] == 0.39 and b["plausible"] is True


def test_unstable_excluded():
    macro3 = {"rate": None, "top": [
        {"f": "Copper", "sens": 1.0, "sig": True, "weak": False, "stab": "stable"},
        {"f": "OJ",     "sens": 2.0, "sig": True, "weak": False, "stab": "unstable"},   # significant but UNSTABLE
    ]}
    stub = {"Copper": {"sigma": 1.0}, "OJ": {"sigma": 1.0}}
    b = _run(macro3, stub)
    assert b["nSigDrivers"] == 1 and abs(b["liveContribPct"] - 1.0) < 1e-6, b   # unstable driver excluded


def test_all_insignificant_defensible_zero():
    macro3 = {"rate": None, "top": [{"f": "Crude", "sens": 0.6, "sig": False, "weak": True, "stab": "stable"}]}
    b = _run(macro3, {"Crude": {"sigma": -1.5}})
    assert b["nSigDrivers"] == 0 and b["liveContribPct"] == 0.0 and b["grossContribPct"] is not None


def test_no_moves_graceful():
    macro3 = {"rate": None, "top": [{"f": "Copper", "sens": 1.0, "sig": True, "weak": False, "stab": "stable"}]}
    n = {"t": "TST", "deps": [], "macro3": macro3, "macroR2": 39}
    b = RE.sensitivities_block(n, moves=None)            # no moves -> impliedPct None for all rows
    assert b["liveContribPct"] is None and b["grossContribPct"] is None and b["hasLive"] is False


if __name__ == "__main__":
    for name in sorted(k for k in dict(globals()) if k.startswith("test_")):
        globals()[name]()
        print("PASS", name)
    print("ALL test_sens_gate PASS")
