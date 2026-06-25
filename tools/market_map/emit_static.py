#!/usr/bin/env python3
"""Static precompute — emit per-ticker decision-card + price-history JSON to the site so the
browser reads STATIC files (zero Render load) for the whole universe. Render is then only a thin
fallback for ad-hoc tickers outside the nightly set. Free: runs in GitHub Actions.

  python emit_static.py --universe _site/marketmap.json --out _site --hist --cap 250

Writes:  _site/cards/{T}.json  (full decision card)   ·  _site/hist/{T}.json  ([[date,close,vol],..])
         _site/cards_index.json (manifest the client checks before calling Render)
Research only; not investment advice.
"""
from __future__ import annotations
import argparse, json, os, sys
try:
    import lineage as _lineage   # Phase 4 volume-ahead + touch (same dir)
except Exception:
    _lineage = None

def _stooq(t):
    import requests
    for sym in (t.lower() + ".us", t.lower()):
        try:
            r = requests.get("https://stooq.com/q/d/l/?s=%s&i=d" % sym, timeout=20)
            if r.status_code != 200 or "Date" not in r.text[:60]:
                continue
            rows = []
            for ln in r.text.strip().splitlines()[1:]:
                p = ln.split(",")
                if len(p) >= 6 and p[4] not in ("", "N/D"):
                    try: rows.append([p[0], round(float(p[4]), 4), int(float(p[5])) if p[5] not in ("", "N/D") else 0])
                    except Exception: pass
            if len(rows) >= 40:
                return rows
        except Exception:
            continue
    return []

def history(t):
    try:
        import yfinance as yf
        h = yf.Ticker(t).history(period="max", interval="1d", auto_adjust=True)
        rows = []
        for idx, r in h.iterrows():
            c = r.get("Close")
            if c == c and c > 0:
                rows.append([str(idx.date()), round(float(c), 4), int(r.get("Volume") or 0)])
        if len(rows) >= 40:
            return rows
    except Exception:
        pass
    return _stooq(t)

def _load_hist(hist_dir, t):
    """Read committed daily rows [[date,close,vol],..] from <hist_dir>/<T>.json (no network)."""
    try:
        with open(os.path.join(hist_dir, t + ".json")) as f:
            return (json.load(f) or {}).get("rows") or None
    except Exception:
        return None

def emit(universe_path, out_dir, do_hist=False, cap=0, hist_dir=None):
    d = json.load(open(universe_path)); names = d.get("names", [])
    cdir = os.path.join(out_dir, "cards"); hdir = os.path.join(out_dir, "hist")
    os.makedirs(cdir, exist_ok=True); os.makedirs(hdir, exist_ok=True)
    nc = nh = 0
    for n in names:
        t = n.get("t")
        if not t: continue
        fetched = history(t) if (do_hist and (not cap or nh < cap)) else None
        rows = fetched if fetched else (_load_hist(hist_dir, t) if hist_dir else None)
        # Phase 4: augment the card with volume-ahead (sigma-volume matrix) + touch odds,
        # computed from daily history (the only place with per-name daily volume).
        if rows and _lineage is not None and "FACTOR" not in (n.get("idx") or []):
            try:
                va = _lineage.volume_ahead(rows)
                to = _lineage.touch_odds(rows)
                lin = n.get("lineage")
                if isinstance(lin, dict):
                    if va.get("sigvol"): lin["sigvol"] = va["sigvol"]
                    if va.get("base"):   lin["volBase"] = va["base"]
                    if to:               lin["touch"] = to
            except Exception:
                pass
        with open(os.path.join(cdir, t + ".json"), "w") as f:
            json.dump(n, f, allow_nan=False)
        nc += 1
        if fetched:
            with open(os.path.join(hdir, t + ".json"), "w") as f:
                json.dump({"ticker": t, "asof": fetched[-1][0], "count": len(fetched), "rows": fetched}, f, allow_nan=False)
            nh += 1
    with open(os.path.join(out_dir, "cards_index.json"), "w") as f:
        json.dump({"asof": d.get("asof"), "source": d.get("source"),
                   "cards": [n["t"] for n in names if n.get("t")], "count": nc, "hist": nh}, f)
    return nc, nh

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="marketmap.json")
    ap.add_argument("--out", default="_site")
    ap.add_argument("--hist", action="store_true", help="also emit price history (slower; needs network)")
    ap.add_argument("--cap", type=int, default=0, help="cap number of histories (0=all)")
    ap.add_argument("--hist-dir", default=None, help="read committed daily rows from here to augment cards (no network)")
    a = ap.parse_args()
    nc, nh = emit(a.universe, a.out, a.hist, a.cap, a.hist_dir)
    sys.stderr.write("emit_static: %d cards, %d histories -> %s\n" % (nc, nh, a.out))

if __name__ == "__main__":
    main()
