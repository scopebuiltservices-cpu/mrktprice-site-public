#!/usr/bin/env python3
"""make_seeds.py — regenerate the keyless fallback seeds from a HEALTHY build, so the safety net never
goes stale. After each good nightly build, this rewrites:

  * data/universe_seed.json  — equities with their GICS sector + index-membership code (the universe
    universe_fetch falls back to when the live index fetch collapses), and
  * data/profile.json        — {ticker: {sector, sectorRaw, industry, exchange}} (the sector seed that
    sector_seed applies at the start of every build).

It REFUSES to write when the input build is itself broken (fails the shared sector-integrity gate), so a
collapsed build can never poison the fallback that exists to rescue it. Pure stdlib; offline-tested."""
import argparse, datetime as dt, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sector_integrity as SI

_TAG = {"NDX": "ND", "DOW": "D", "SPX": "S", "RUT": "R"}


def build_seeds(mm):
    """Pure: (universe_rows, profile_map) from a marketmap dict. Only equities with a real GICS sector."""
    names = (mm or {}).get("names") or []
    uni, prof = [], {}
    for n in names:
        sec = n.get("sec")
        if sec not in SI.GICS:
            continue
        t = (n.get("t") or "").upper()
        if not t:
            continue
        code = " ".join(_TAG[x] for x in (n.get("idx") or []) if x in _TAG) or "S"
        uni.append([t, (n.get("n") or t)[:48], sec, code])
        prof[t] = {"sector": sec, "sectorRaw": sec, "industry": "", "exchange": ""}
    uni.sort(key=lambda r: r[0])
    return uni, prof


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="marketmap.json", help="a freshly-built, healthy marketmap.json")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--min-universe", type=int, default=80)
    a = ap.parse_args()
    try:
        mm = json.load(open(a.map))
    except Exception as e:
        sys.stderr.write("make_seeds: cannot read %s (%s) — seeds NOT refreshed\n" % (a.map, str(e)[:80]))
        return 0   # non-fatal: keep the existing committed seeds

    viol = SI.sector_violations(mm, min_universe=a.min_universe)
    uni, prof = build_seeds(mm)
    if viol or len(uni) < SI.SECTORED_FLOOR:
        sys.stderr.write("make_seeds: REFUSING to refresh seeds from an unhealthy build (%s; sectored=%d)\n"
                         % ("; ".join(viol) or "too few sectored", len(uni)))
        return 0   # never overwrite good seeds with a broken build

    os.makedirs(a.data_dir, exist_ok=True)
    today = dt.date.today().isoformat()
    # universe_seed.json: full overwrite — it is the dedicated fallback artifact, no other writer.
    u_out = {"_meta": {"source": "auto-refreshed from a healthy build", "asof": today, "n": len(uni)},
             "universe": uni}
    _atomic_write(os.path.join(a.data_dir, "universe_seed.json"), u_out)
    # profile.json: MERGE — preserve any richer FMP-authored entries (industry/exchange), only fill gaps,
    # so refreshing the fallback never downgrades the authoritative profile.
    ppath = os.path.join(a.data_dir, "profile.json")
    existing = {}
    if os.path.exists(ppath):
        try: existing = json.load(open(ppath))
        except Exception: existing = {}
    added = 0
    for t, rec in prof.items():
        cur = existing.get(t)
        if not isinstance(cur, dict) or cur.get("sector") not in SI.GICS:
            existing[t] = rec; added += 1
    existing["_meta"] = {"names": sum(1 for k in existing if not k.startswith("_")),
                         "source": "FMP profile + auto-refresh gap-fill", "asof": today, "pit": False}
    _atomic_write(ppath, existing)
    sys.stderr.write("make_seeds: refreshed universe_seed.json (%d); profile.json gap-filled +%d (total %d) from %s\n"
                     % (len(uni), added, sum(1 for k in existing if not k.startswith("_")), a.map))
    return 0


def _atomic_write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, path)


if __name__ == "__main__":
    raise SystemExit(main())
