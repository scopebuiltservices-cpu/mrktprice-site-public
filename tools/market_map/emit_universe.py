#!/usr/bin/env python3
"""
emit_universe.py — emit a data-driven universe.json from the built marketmap.json.

Decouples the analyzable universe (membership, sector census, data-quality/drift rollup) from the
hard-coded SEED in code: reproducible, easy to diff run-over-run, and a clean input for downstream
analysis. Keyless, stdlib-only.

Usage: python emit_universe.py --map marketmap.json --out universe.json
"""
import argparse, json, datetime


def build(mapobj):
    names = mapobj.get("names") or []
    dh = mapobj.get("dataHealth") or {}
    members, sectors, idxc = [], {}, {}
    for n in names:
        t = (n.get("t") or "").upper()
        if not t:
            continue
        sec = n.get("sec") or "—"
        idx = n.get("idx") or []
        members.append({"t": t, "sec": sec, "idx": idx,
                        "etf": ("ETF" in idx) or bool(n.get("etf")) or ("FACTOR" in idx),
                        "dq": n.get("dq"), "drift": (n.get("drift") or {}).get("level")})
        sectors[sec] = sectors.get(sec, 0) + 1
        for ix in idx:
            idxc[ix] = idxc.get(ix, 0) + 1
    members.sort(key=lambda m: (m["sec"], m["t"]))
    return {
        "asof": mapobj.get("asof") or datetime.date.today().isoformat(),
        "schemaVersion": "1.0",
        "source": mapobj.get("source"),
        "count": len(members),
        "equities": sum(1 for m in members if not m["etf"]),
        "sectors": dict(sorted(sectors.items())),
        "indexMembership": dict(sorted(idxc.items())),
        "dataQuality": dh.get("dataQuality"),
        "driftCensus": dh.get("driftCensus"),
        "members": members,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="marketmap.json")
    ap.add_argument("--out", default="universe.json")
    a = ap.parse_args(argv)
    with open(a.map, "r", encoding="utf-8") as f:
        mapobj = json.load(f)
    u = build(mapobj)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(u, f, separators=(",", ":"))
    print("wrote %s: %d members, %d sectors" % (a.out, u["count"], len(u["sectors"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
