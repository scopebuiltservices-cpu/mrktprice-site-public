"""Planted test: synth marketmap (with insider) + sec_events -> n.ev populated, tilt sign sensible."""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import event_board as B

def test_enrich_sets_ev_and_tilt():
    mm = {"names": [
        {"t": "BULL", "insider": {"buy": 100, "discSell": 0, "planSell": 0}},     # heavy insider buying
        {"t": "BEAR", "insider": {"buy": 0, "discSell": 200, "planSell": 0}},      # discretionary selling
        {"t": "NONE"},                                                            # no event coverage
    ]}
    sec = {
        "BULL": {"intensity": 1.5, "n8k": 1, "n13d": 1, "n13g": 0, "nins": 2,
                 "last": {"form": "SC 13D", "date": "2026-06-20"}, "events": [{"form": "8-K", "date": "2026-06-18", "sev": 0.6}]},
        "BEAR": {"intensity": 2.0, "n8k": 2, "n13d": 0, "n13g": 1, "nins": 1,
                 "last": {"form": "8-K", "date": "2026-06-22"}, "events": []},
    }
    done = B.enrich(mm, sec)
    assert done == 2, done
    bull = mm["names"][0]["ev"]; bear = mm["names"][1]["ev"]
    assert "ev" not in mm["names"][2]                                  # NONE untouched
    assert bull["netIns"] > 0.9 and bear["netIns"] < -0.9             # insider net sign
    assert bull["n13d"] == 1 and bull["stake"] > 0                    # activist stake positive
    assert bull["tilt"] > bear["tilt"]                                # buying+activist beats selling
    assert -3.0 <= bear["tilt"] <= 3.0                                # bounded
    print("  PASS  enrich: BULL tilt=%.2f (netIns=%.2f, stake=%.2f) > BEAR tilt=%.2f (netIns=%.2f); NONE skipped"
          % (bull["tilt"], bull["netIns"], bull["stake"], bear["tilt"], bear["netIns"]))

def test_no_insider_ok():
    mm = {"names": [{"t": "X"}]}
    sec = {"X": {"intensity": 0.5, "n8k": 1, "n13d": 0, "n13g": 0, "nins": 0, "last": None, "events": []}}
    B.enrich(mm, sec)
    assert mm["names"][0]["ev"]["netIns"] == 0.0
    print("  PASS  name without insider data -> netIns=0, still enriched")

if __name__ == "__main__":
    test_enrich_sets_ev_and_tilt(); test_no_insider_ok()
    print("\nALL EVENT_BOARD TESTS PASSED")
