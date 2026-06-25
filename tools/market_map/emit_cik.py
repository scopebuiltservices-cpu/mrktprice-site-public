#!/usr/bin/env python3
"""Emit cik.json (ticker -> 10-digit CIK) for the dashboard universe, from SEC's FREE company_tickers.json.

NO API KEY. This is what lets the terminal resolve a ticker's CIK in the browser and pull CONFIRMED
quarterly report dates straight from SEC EDGAR — so the 5 report-date verticals work without any paid
feed or secret. Run keylessly in CI; ETFs/funds simply don't match (they have no CIK) and are excluded.

Usage: python3 emit_cik.py [--out cik.json] [--marketmap marketmap.json] [--cards cards]
Fail-soft: on any error it leaves the existing cik.json untouched and exits non-zero (CI step is `|| true`).
"""
import json, os, sys, argparse, glob

UA = {"User-Agent": "MrktPrice research (scopebuiltservices@gmail.com)"}


def universe(mm_path, cards_dir):
    u = set()
    try:
        mm = json.load(open(mm_path))
        u |= {(n.get("t") or "").upper() for n in mm.get("names", []) if n.get("t")}
    except Exception:
        pass
    for f in glob.glob(os.path.join(cards_dir, "*.json")):
        u.add(os.path.basename(f)[:-5].upper())
    return u


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="cik.json")
    ap.add_argument("--marketmap", default="marketmap.json")
    ap.add_argument("--cards", default="cards")
    a = ap.parse_args()
    try:
        import requests
        r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=UA, timeout=30)
        r.raise_for_status()
        j = r.json()
    except Exception as e:
        sys.stderr.write("emit_cik: SEC fetch failed (%s); leaving %s as-is\n" % (str(e)[:120], a.out))
        return 1
    m = {}
    for v in (j.values() if isinstance(j, dict) else j):
        if not isinstance(v, dict):
            continue
        t = str(v.get("ticker", "")).upper().strip()
        c = str(v.get("cik_str", "")).zfill(10)
        if t:
            m[t] = c
    uni = universe(a.marketmap, a.cards)
    out = {t: m[t] for t in sorted(uni) if t in m} if uni else dict(m)
    # never regress: keep any prior entries SEC didn't return this run
    try:
        prev = json.load(open(a.out))
        for k, v in prev.items():
            out.setdefault(k, v)
    except Exception:
        pass
    if not out:
        sys.stderr.write("emit_cik: empty result; leaving %s as-is\n" % a.out)
        return 1
    tmp = a.out + ".tmp"
    json.dump(out, open(tmp, "w"), separators=(",", ":"), sort_keys=True)
    os.replace(tmp, a.out)
    sys.stderr.write("emit_cik: wrote %s (%d tickers from %d universe / %d SEC)\n" % (a.out, len(out), len(uni), len(m)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
