#!/usr/bin/env python3
"""fmp_profile.py — GATED FMP BULK profile -> authoritative sector / industry / exchange.

Pulls FMP's profile-bulk CSV (served in 4 parts: part=0..3) for the WHOLE market in 4 calls, parses
defensively, normalizes FMP's sector naming to our canonical GICS labels, filters to the universe, and
emits data/profile.json {ticker: {sector, sectorRaw, industry, exchange}}. Used by sector_reconcile.py to
make the board's sector authoritative (it drives EB-shrinkage groups + FF residualization). Network in CI
only; parser + normalizer pure + offline-tested. Research only."""
import argparse, csv, io, json, os, sys

STABLE = "https://financialmodelingprep.com/stable"
PARTS = 4

# FMP sector naming -> our canonical GICS-style labels (matches build_market_map's sector set)
GICS = {
    "technology": "Technology", "information technology": "Technology",
    "financial services": "Financials", "financials": "Financials", "financial": "Financials",
    "healthcare": "Health Care", "health care": "Health Care",
    "industrials": "Industrials", "industrial": "Industrials",
    "consumer cyclical": "Consumer Disc.", "consumer discretionary": "Consumer Disc.",
    "consumer defensive": "Consumer Staples", "consumer staples": "Consumer Staples",
    "communication services": "Communication", "communication": "Communication",
    "energy": "Energy", "utilities": "Utilities",
    "basic materials": "Materials", "materials": "Materials",
    "real estate": "Real Estate",
}


def normalize_sector(raw):
    if not raw:
        return None
    return GICS.get(str(raw).strip().lower())


def _key():
    for k in ("FMP_API_KEY", "FMP_ULTIMATE_API_KEY", "FMP_UTIMATE_API_KEY"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return ""


def parse_profile_csv(text):
    s = (text or "").lstrip()
    if s[:1] == "[":
        try:
            d = json.loads(s); return d if isinstance(d, list) else []
        except Exception:
            return []
    return list(csv.DictReader(io.StringIO(text)))


def _pick(r, *names):
    for n in names:
        if n in r and r[n] not in (None, ""):
            return r[n]
    low = {k.lower(): v for k, v in r.items()}
    for n in names:
        v = low.get(n.lower())
        if v not in (None, ""):
            return v
    return None


def rows_to_map(rows, universe=None):
    out = {}
    for r in rows or []:
        t = (_pick(r, "symbol", "Symbol", "ticker") or "").upper()
        if not t or (universe and t not in universe):
            continue
        raw = _pick(r, "sector", "Sector")
        out[t] = {"sector": normalize_sector(raw), "sectorRaw": raw,
                  "industry": _pick(r, "industry", "Industry"),
                  "exchange": _pick(r, "exchangeShortName", "exchange", "Exchange")}
    return out


def build(universe=None, key=None):
    import requests
    key = key or _key()
    if not key:
        sys.stderr.write("fmp_profile: no FMP key — skipped\n")
        return {}
    s = requests.Session()
    out = {}
    for part in range(PARTS):
        try:
            r = s.get("%s/profile-bulk?part=%d&apikey=%s" % (STABLE, part, key), timeout=90)
            if r.status_code == 200:
                out.update(rows_to_map(parse_profile_csv(r.text), universe))
        except Exception as ex:
            sys.stderr.write("fmp_profile: part %d failed: %s\n" % (part, str(ex)[:60]))
    return out


def _universe(marketmap):
    try:
        mm = json.load(open(marketmap))
        return set(n["t"].upper() for n in mm.get("names", []) if n.get("t"))
    except Exception:
        return set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--marketmap", default="marketmap.json")
    ap.add_argument("--out", default="data/profile.json")
    a = ap.parse_args()
    uni = _universe(a.marketmap)
    res = build(universe=uni or None)
    if not res:
        return 0
    res["_meta"] = {"names": len(res), "source": "FMP profile-bulk (4 parts)"}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    tmp = a.out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(res, f, separators=(",", ":"))
    os.replace(tmp, a.out)
    sys.stderr.write("fmp_profile: wrote %s for %d names\n" % (a.out, len(res) - 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
