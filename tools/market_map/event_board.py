#!/usr/bin/env python3
"""event_board.py — POST-BUILD enrichment: fold SEC-filing events into a per-name NUMBER (eventTilt).

External-enrichment pattern (no surgery in build_market_map.py): reads sec_events.json (8-K/13D/13G/3-4-5
event stream + decayed intensity, from sec_forms.py) and the per-name insider block already in
marketmap.json, then computes the event tilt via event_engine and writes:
    n["ev"] = {intensity, n8k, n13d, n13g, nins, last, stake, netIns, tilt}
where  tilt = event_tilt(CAR=0, intensity, stake, netIns)   (CAR is added CLIENT-side from price history).
The board nets `tilt` into the displayed alpha; the terminal draws the dated events as timeline verticals
and lists them under Considerations. Idempotent; verified against a planted fixture. Research only."""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import event_engine as EV


def _stake_from_counts(ev):
    """Keyless stake proxy: a recent 13D (activist) is a stronger ownership signal than a 13G (passive).
    We lack Δ% keyless, so use presence/recency via the decayed counts the summary already carries."""
    n13d = ev.get("n13d", 0) or 0
    n13g = ev.get("n13g", 0) or 0
    last = ev.get("last") or {}
    new_d = str(last.get("form", "")).upper() == "SC 13D"     # newest filing is an activist 13D
    s = EV.stake_signal("13D", 0.0, new_d) * min(1.0, 0.5 * n13d) + EV.stake_signal("13G", 0.0, False) * min(1.0, 0.3 * n13g)
    return max(-1.0, min(1.0, s))


def enrich(mm, sec):
    names = mm.get("names") or []
    done = 0
    for n in names:
        tk = n.get("t") or n.get("sym")
        ev = sec.get(tk) if tk else None
        if not ev:
            continue
        ins = n.get("insider") or {}
        buy = float(ins.get("buy") or 0.0)
        disc = float(ins.get("discSell") or 0.0)
        plan = float(ins.get("planSell") or 0.0)
        netins = EV.insider_net(buy, disc, plan) if (buy or disc or plan) else 0.0
        stake = _stake_from_counts(ev)
        intensity = float(ev.get("intensity") or 0.0)
        tilt = EV.event_tilt(0.0, intensity, stake, netins)     # CAR filled client-side
        n["ev"] = {
            "intensity": round(intensity, 4), "n8k": ev.get("n8k", 0), "n13d": ev.get("n13d", 0),
            "n13g": ev.get("n13g", 0), "nins": ev.get("nins", 0), "last": ev.get("last"),
            "stake": round(stake, 3), "netIns": round(netins, 3), "tilt": round(tilt, 3),
            "events": (ev.get("events") or [])[:12],            # dated stream for the timeline/considerations
        }
        done += 1
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="marketmap.json")
    ap.add_argument("--sec", default="sec_events.json")
    a = ap.parse_args()
    if not os.path.exists(a.sec):
        sys.stderr.write("event_board: no %s — skipped (run sec_forms.py first)\n" % a.sec)
        return 0
    sec = json.load(open(a.sec))
    sec = {k: v for k, v in sec.items() if not k.startswith("_")}
    try:
        mm = json.load(open(a.map))
    except Exception as e:
        sys.stderr.write("event_board: cannot read %s (%s)\n" % (a.map, str(e)[:80]))
        return 1
    done = enrich(mm, sec)
    tmp = a.map + ".tmp"
    with open(tmp, "w") as f:
        json.dump(mm, f, separators=(",", ":"))
    os.replace(tmp, a.map)
    sys.stderr.write("event_board: enriched %d names with SEC event tilt -> %s\n" % (done, a.map))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
