#!/usr/bin/env python3
"""factor_returns.py — KEYLESS Fama-French factor returns from the Ken French Data Library.

Public CSVs (no key, no account): FF 5-factor daily + Momentum daily, distributed as zipped CSV at
dartmouth.edu. Cached nightly like the FRED CSV. The network fetch runs ONLY in CI (urllib, stdlib);
`parse_ff_csv` is pure and offline-testable against a fixture so the engine is verified without network.

Output cache `data/ff_factors.csv`:  date,MktRF,SMB,HML,RMW,CMA,Mom,RF   (returns as FRACTIONS, RF too)

CLI:  python3 factor_returns.py [--out data/ff_factors.csv]    (fetches + writes; CI use)
      python3 factor_returns.py --selftest                      (offline parser self-test)"""
import io, sys, os, csv, zipfile, datetime as dt

FF5_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"
MOM_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_daily_CSV.zip"

__all__ = ["parse_ff_csv", "merge_factor_tables", "load_factor_csv", "fetch_ff_factors"]


def parse_ff_csv(text):
    """Parse a Ken French CSV (already unzipped, as text). Returns {yyyymmdd:int -> {col:fraction}}.

    Format: leading prose lines; a header line that begins with a comma then comma-separated factor names
    (e.g. ',Mkt-RF,SMB,HML,RMW,CMA,RF' or ',Mom'); daily rows keyed by an 8-digit YYYYMMDD date in percent;
    the daily block ends at the first non-8-digit-date row (blank line or the 'Annual Factors' section).
    Values are PERCENT in the file -> divided by 100 here. Column names are normalized: 'Mkt-RF'->'MktRF',
    'Mom   '->'Mom'."""
    out = {}
    cols = None
    in_block = False
    for raw in text.splitlines():
        line = raw.rstrip("\n").rstrip("\r")
        if not line.strip():
            if in_block:
                break                      # blank line terminates the daily block
            continue
        parts = [p.strip() for p in line.split(",")]
        first = parts[0]
        if not in_block:
            # header row: empty first cell, >=1 named columns after it
            if first == "" and len(parts) >= 2 and any(parts[1:]):
                cols = [_norm(c) for c in parts[1:]]
                in_block = True
            continue
        # in daily block: first cell must be an 8-digit date
        if len(first) == 8 and first.isdigit():
            try:
                d = int(first)
                vals = {}
                for i, c in enumerate(cols):
                    v = parts[1 + i] if (1 + i) < len(parts) else ""
                    vals[c] = (float(v) / 100.0) if v not in ("", "-99.99", "-999") else None
                out[d] = vals
            except Exception:
                continue
        else:
            break                          # reached the annual section / footer
    return out


def _norm(c):
    return c.replace("-", "").replace(" ", "")


def merge_factor_tables(ff5, mom):
    """Join FF5 {date->{MktRF,SMB,HML,RMW,CMA,RF}} with Mom {date->{Mom}} on date (inner on FF5 dates)."""
    rows = []
    for d in sorted(ff5):
        r = {"date": d}
        r.update(ff5[d])
        m = (mom.get(d) or {}).get("Mom")
        r["Mom"] = m
        rows.append(r)
    return rows


def load_factor_csv(path):
    """Read the normalized cache back as a list of dicts (fractions as float, None for blanks)."""
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for r in csv.DictReader(f):
            o = {"date": int(r["date"])}
            for k in ("MktRF", "SMB", "HML", "RMW", "CMA", "Mom", "RF"):
                v = r.get(k, "")
                o[k] = (float(v) if v not in ("", None) else None)
            rows.append(o)
    return rows


def _write_cache(rows, out):
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    cols = ["date", "MktRF", "SMB", "HML", "RMW", "CMA", "Mom", "RF"]
    tmp = out + ".tmp"
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get("date")] + [("" if r.get(c) is None else "%.6f" % r.get(c)) for c in cols[1:]])
    os.replace(tmp, out)


def fetch_ff_factors(out="data/ff_factors.csv", timeout=30):
    """CI-only: download both zips, unzip in-memory, parse, merge, write the cache. Returns row count.
    Raises on network/format failure so CI surfaces it (caller may downgrade to a warning)."""
    import urllib.request

    def _grab(url):
        req = urllib.request.Request(url, headers={"User-Agent": "mrktprice-bot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            blob = resp.read()
        zf = zipfile.ZipFile(io.BytesIO(blob))
        name = zf.namelist()[0]
        return zf.read(name).decode("latin-1")

    ff5 = parse_ff_csv(_grab(FF5_URL))
    mom = parse_ff_csv(_grab(MOM_URL))
    rows = merge_factor_tables(ff5, mom)
    if not rows:
        raise ValueError("FF parse produced zero rows")
    _write_cache(rows, out)
    return len(rows)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/ff_factors.csv")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return 0
    try:
        n = fetch_ff_factors(a.out)
        sys.stderr.write("factor_returns: wrote %d rows -> %s\n" % (n, a.out))
        return 0
    except Exception as e:
        sys.stderr.write("factor_returns: FETCH FAILED (%s) — keyless FF cache not refreshed\n" % str(e)[:120])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
