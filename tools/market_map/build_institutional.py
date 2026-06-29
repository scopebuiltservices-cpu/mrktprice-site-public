#!/usr/bin/env python3
"""Free 13F institutional engine — quarterly batch.

Downloads the SEC bulk Form 13F data sets for the two most recent available quarters,
aggregates the INFOTABLE by issuer (holders / shares / value), matches them to the
MrktPrice universe (by normalized issuer name), computes quarter-over-quarter
accumulation/distribution, and writes institutional.json (read by build_market_map.py).

Run quarterly (the zips are large) — see .github/workflows/refresh-13f.yml.
Self-contained: stdlib + requests. SEC data is free. Research only; not investment advice.

Usage:
  python build_institutional.py                          # auto: latest two quarters -> institutional.json
  python build_institutional.py --curr 2026q1 --prev 2025q4
  python build_institutional.py --local-curr CUR.tsv --local-prev PREV.tsv   # offline test
"""
from __future__ import annotations
import argparse, csv, io, json, os, re, sys, zipfile, datetime as dt

UA = {"User-Agent": "MrktPrice marketmap/1.0 (research; contact scopebuiltservices@gmail.com)"}
BASE = "https://www.sec.gov/files/structureddata/data/form-13f-data-sets"

_DROP = {"INC","INCORPORATED","CORP","CORPORATION","CO","COMPANY","LTD","LIMITED","PLC","LLC","LP",
         "THE","COM","CL","CLASS","HLDG","HLDGS","HOLDINGS","HOLDING","GROUP","GRP","NEW","SHS","ADR",
         "PAR","COMMON","STOCK","TR","TRUST","SA","NV","AG"}
def norm_name(s):
    s = re.sub(r"[^A-Z0-9 ]", " ", (s or "").upper())
    return " ".join(t for t in s.split() if t not in _DROP and not (len(t) == 1 and t.isalpha())).strip()

def aggregate_infotable(fh, only_sh=True):
    rdr = csv.reader(fh, delimiter="\t")
    try: header = next(rdr)
    except StopIteration: return {}
    idx = {h.strip().upper(): i for i, h in enumerate(header)}
    def col(row, name):
        i = idx.get(name); return row[i].strip() if (i is not None and i < len(row)) else ""
    agg = {}
    for row in rdr:
        if not row: continue
        cusip = col(row, "CUSIP").upper()
        if not cusip: continue
        if col(row, "PUTCALL"): continue                       # exclude options
        try: val = float(col(row, "VALUE") or 0)
        except Exception: val = 0.0
        try: sh = float(col(row, "SSHPRNAMT") or 0)
        except Exception: sh = 0.0
        sshtype = col(row, "SSHPRNAMTTYPE").upper(); acc = col(row, "ACCESSION_NUMBER")
        a = agg.get(cusip)
        if a is None: a = agg[cusip] = {"issuer": col(row, "NAMEOFISSUER"), "value": 0.0, "shares": 0.0, "_h": set()}
        a["value"] += val
        if (not only_sh) or sshtype == "SH": a["shares"] += sh
        if acc: a["_h"].add(acc)
    for c in agg: agg[c]["holders"] = len(agg[c].pop("_h"))
    return agg

def match_universe(agg, universe, cusip_map=None):
    """Match by CUSIP first (exact, from the fails-to-deliver map), then fall back to normalized issuer name."""
    by_norm = {}
    for c, a in agg.items(): by_norm.setdefault(norm_name(a["issuer"]), c)
    out = {}
    for tk, nm in universe:
        c = None
        if cusip_map and cusip_map.get(tk):
            cc = cusip_map[tk].upper()[:8]
            for k in agg:
                if k[:8] == cc: c = k; break
        if not c: c = by_norm.get(norm_name(nm))
        if c and c in agg:
            a = agg[c]; out[tk] = {"cusip": c, "issuer": a["issuer"], "value": a["value"], "shares": a["shares"], "holders": a["holders"]}
    return out

def institutional_flow(curr, prev):
    out = {}
    for tk, c in curr.items():
        p = (prev or {}).get(tk)
        d = {"cusip": c["cusip"], "issuer": c["issuer"], "value": round(c["value"]), "shares": round(c["shares"]), "holders": c["holders"]}
        if p and p.get("shares", 0) > 0:
            dsh = (c["shares"] - p["shares"]) / p["shares"]
            d["dShares"] = round(dsh * 100, 1); d["dHolders"] = c["holders"] - p.get("holders", 0)
            d["verdict"] = ("accumulation" if dsh >= 0.02 else "distribution" if dsh <= -0.02 else "stable")
        else:
            d["dShares"] = None; d["dHolders"] = None; d["verdict"] = "n/a"
        out[tk] = d
    return out

# ---------- period helpers ----------
# SEC switched 13F data-set filenames in MARCH 2024: from quarterly "YYYYqN_form13f.zip" (pre-2024) to
# ROLLING 3-month month-range files (e.g. "01mar2026-31may2026_form13f.zip"), published after the end of
# Feb/May/Aug/Nov. The old qN URLs 404 for current data — that was the silent-failure root cause.
def _feb_end(y): return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
def period_windows(today=None):
    """Published SEC 13F periods, NEWEST-FIRST, as (period_end_date, filename_label). Only periods whose
    end is >=20 days past (i.e. already published) are returned."""
    today = today or dt.date.today()
    out = []
    for y in (today.year + 1, today.year, today.year - 1, today.year - 2):
        fe = _feb_end(y)
        out.append((dt.date(y, 2, fe),  "01dec%d-%02dfeb%d" % (y - 1, fe, y)))
        out.append((dt.date(y, 5, 31),  "01mar%d-31may%d" % (y, y)))
        out.append((dt.date(y, 8, 31),  "01jun%d-31aug%d" % (y, y)))
        out.append((dt.date(y, 11, 30), "01sep%d-30nov%d" % (y, y)))
    avail = [(e, lab) for (e, lab) in out if (today - e).days >= 20]
    avail.sort(key=lambda x: x[0], reverse=True)
    return avail
def latest_quarters(today=None):
    """Back-compat shim: the two newest published period labels."""
    p = period_windows(today)
    return p[0][1], p[1][1]

def load_infotable_from_zip(content):
    zf = zipfile.ZipFile(io.BytesIO(content))
    name = next((n for n in zf.namelist() if n.upper().endswith("INFOTABLE.TSV")), None)
    if not name: raise RuntimeError("INFOTABLE.tsv not found in zip")
    return aggregate_infotable(io.TextIOWrapper(zf.open(name), encoding="utf-8", errors="replace"))

def download_quarter(q):
    import requests
    url = f"{BASE}/{q}_form13f.zip"
    r = requests.get(url, headers=UA, timeout=180)
    if r.status_code != 200 or len(r.content) < 1000:
        raise RuntimeError(f"download failed {url} ({r.status_code})")
    return load_infotable_from_zip(r.content)

FTD_BASE = "https://www.sec.gov/files/data/fails-deliver-data"
def parse_ftd_line(line):
    """SEC fails-to-deliver row is pipe-delimited: DATE|CUSIP|SYMBOL|QTY|DESCRIPTION|PRICE -> (ticker, cusip)."""
    p = line.split("|")
    if len(p) < 3: return None, None
    sym = p[2].strip().upper(); cusip = p[1].strip()
    if not sym or not cusip or sym == "SYMBOL": return None, None
    return sym, cusip

def build_cusip_map(tickers, sess=None):
    """ticker -> CUSIP from the SEC fails-to-deliver files (free, official). Tries the most recent half-months."""
    import requests
    s = sess or requests.Session()
    want = {t.upper() for t in tickers}; out = {}
    today = dt.date.today()
    for back in range(0, 4):
        y, m = today.year, today.month - back
        while m <= 0: m += 12; y -= 1
        for half in ("b", "a"):
            url = f"{FTD_BASE}/cnsfails{y}{m:02d}{half}.zip"
            try:
                r = s.get(url, headers=UA, timeout=120)
                if r.status_code != 200 or len(r.content) < 500: continue
                zf = zipfile.ZipFile(io.BytesIO(r.content)); nm = zf.namelist()[0]
                for line in io.TextIOWrapper(zf.open(nm), encoding="latin-1", errors="replace"):
                    sym, cusip = parse_ftd_line(line)
                    if sym and sym in want and sym not in out: out[sym] = cusip
                if out: sys.stderr.write(f"cusip map: {len(out)}/{len(want)} from cnsfails{y}{m:02d}{half}\n"); return out
            except Exception: continue
    return out

def universe_from_marketmap(path):
    with open(path) as f: d = json.load(f)
    return [(n["t"], n.get("n", n["t"])) for n in d.get("names", [])]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--curr"); ap.add_argument("--prev")
    ap.add_argument("--local-curr"); ap.add_argument("--local-prev")
    ap.add_argument("--universe", default="marketmap.json")
    ap.add_argument("--out", default="institutional.json")
    a = ap.parse_args()

    if a.local_curr and a.local_prev:
        with open(a.local_curr) as f: ac = aggregate_infotable(f)
        with open(a.local_prev) as f: ap_ = aggregate_infotable(f)
        cq, pq = "local-curr", "local-prev"
    elif a.curr and a.prev:
        cq, pq = a.curr, a.prev
        sys.stderr.write(f"13F periods (explicit): curr={cq} prev={pq}\n")
        ac = download_quarter(cq); ap_ = download_quarter(pq)
    else:
        # AUTO: try published periods newest-first; keep the two that actually download. Resilient to
        # publication timing AND the Mar-2024 filename change (the old qN URLs 404 -> silent empty file).
        got = []
        for _e, lab in period_windows():
            try:
                agg = download_quarter(lab); got.append((lab, agg))
                sys.stderr.write(f"13F period ok: {lab}\n")
                if len(got) == 2:
                    break
            except Exception as ex:
                sys.stderr.write(f"13F period miss: {lab} ({str(ex)[:90]})\n")
        if len(got) < 2:
            sys.stderr.write("13F: could not download two published periods — institutional.json NOT updated\n")
            return 2
        (cq, ac), (pq, ap_) = got[0], got[1]

    uni = universe_from_marketmap(a.universe)
    cmap = {} if (a.local_curr and a.local_prev) else build_cusip_map([t for t, _ in uni])
    flow = institutional_flow(match_universe(ac, uni, cmap), match_universe(ap_, uni, cmap))
    flow["_meta"] = {"curr_q": cq, "prev_q": pq, "asof": dt.date.today().isoformat(),
                     "matched": len([k for k in flow if not k.startswith("_")]), "universe": len(uni), "cusip_mapped": len(cmap),
                     "source": "SEC Form 13F data sets (free)"}
    with open(a.out, "w") as f: json.dump(flow, f, allow_nan=False)
    sys.stderr.write(f"wrote {a.out}: {flow['_meta']['matched']}/{len(uni)} names matched\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
