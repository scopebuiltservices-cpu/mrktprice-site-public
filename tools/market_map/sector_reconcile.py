#!/usr/bin/env python3
"""sector_reconcile.py — POST-BUILD enrichment: make the per-name SECTOR authoritative (GICS via FMP).

Sector drives the EB-shrinkage peer groups, sector-relative valuation, and FF residualization, so a wrong
self-assigned label mis-specifies those. Reads data/profile.json (fmp_profile: FMP profile-bulk, normalized
to our canonical labels) and, for each EQUITY name that has an authoritative sector:
    n["secOrig"] = the old self-assigned label (kept)
    n["secAuth"] = authoritative GICS sector
    n["secMismatch"] = True when they differ (a data-quality flag)
    n["sec"]     = authoritative sector (so all CLIENT grouping/display use it)
ETF/macro buckets (Commodity/FX/Rate/Style/Broad/Global/Sector) have no company sector in the profile, so
they are left untouched. NOTE: server-side EB/residualization in THIS build used the prior label; the
authoritative sector takes effect for client grouping now and for server grouping on the next build (feed
profile.json into the seed). Idempotent; verified. Research only."""
import argparse, json, os, sys

NON_EQUITY = {"Commodity", "FX", "Rate", "Style", "Broad", "Global", "Sector", ""}


def enrich(mm, prof):
    names = mm.get("names") or []
    done = 0; mism = 0
    for n in names:
        tk = (n.get("t") or n.get("sym") or "").upper()
        rec = prof.get(tk) if tk else None
        auth = (rec or {}).get("sector")
        if not auth:                                       # no authoritative equity sector -> leave as-is
            continue
        seed = n.get("secSeed") if n.get("secSeed") is not None else n.get("sec")   # prefer the build-preserved seed
        n["secOrig"] = seed
        n["secAuth"] = auth
        n["secMismatch"] = bool(seed and seed not in NON_EQUITY and seed != auth)
        if n["secMismatch"]:
            mism += 1
        n["sec"] = auth                                    # client grouping/display now authoritative
        done += 1
    return done, mism


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="marketmap.json")
    ap.add_argument("--profile", default="data/profile.json")
    a = ap.parse_args()
    if not os.path.exists(a.profile):
        sys.stderr.write("sector_reconcile: no %s — skipped (run fmp_profile.py first)\n" % a.profile)
        return 0
    try:
        prof = json.load(open(a.profile))
        prof = {k: v for k, v in prof.items() if not k.startswith("_")}
        mm = json.load(open(a.map))
    except Exception as e:
        sys.stderr.write("sector_reconcile: read error (%s)\n" % str(e)[:80])
        return 1
    done, mism = enrich(mm, prof)
    tmp = a.map + ".tmp"
    with open(tmp, "w") as f:
        json.dump(mm, f, separators=(",", ":"))
    os.replace(tmp, a.map)
    sys.stderr.write("sector_reconcile: authoritative sector on %d names (%d mismatches corrected) -> %s\n" % (done, mism, a.map))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
