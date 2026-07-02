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
try:                            # hardened writer: tools/verify_artifact.py (one dir up)
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    import verify_artifact as _va
except Exception:
    _va = None

def _write_json(path, obj):
    """Durable + self-verified write: atomic temp -> fsync -> os.replace -> re-read + sha256 check.
    Falls back to a plain write if the hardened writer is unavailable, so emit always succeeds."""
    data = json.dumps(obj, allow_nan=False)
    if _va is not None:
        _va.write_atomic(path, data)
    else:
        with open(path, "w") as f:
            f.write(data)

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
                    try: rows.append([p[0], round(float(p[4]), 4), int(float(p[5])) if p[5] not in ("", "N/D") else 0,
                                      round(float(p[2]), 4), round(float(p[3]), 4)])   # +high(p2) +low(p3)
                    except Exception: pass
            if len(rows) >= 40:
                return rows
        except Exception:
            continue
    return []

def history(t):
    """FMP Ultimate first (authoritative, split/div-adjusted), then yfinance, then Tiingo
    (official API, gated on TIINGO_API_KEY), then Stooq. Returns (rows, source_label) so
    per-ticker provenance can be stored + shown in the UI."""
    try:
        import fmp_history as _fh
        if _fh.have_key():
            ov = None
            try: ov = _fh.eod_ohlcv(t)   # [date,open,high,low,close,vol]
            except Exception: ov = None
            if ov:   # keep [date,close,vol,high,low] so the cone can use Parkinson range vol (additive)
                return [[r[0], r[4], r[5], r[2], r[3]] for r in ov], _fh.SOURCE_LABEL
            rows = _fh.eod_history(t)
            if rows:
                return rows, _fh.SOURCE_LABEL
    except Exception:
        pass
    try:
        import yfinance as yf
        h = yf.Ticker(t).history(period="max", interval="1d", auto_adjust=True)
        rows = []
        for idx, r in h.iterrows():
            c = r.get("Close")
            if c == c and c > 0:
                hh = r.get("High"); ll = r.get("Low")
                rows.append([str(idx.date()), round(float(c), 4), int(r.get("Volume") or 0),
                             round(float(hh), 4) if (hh == hh and hh) else round(float(c), 4),
                             round(float(ll), 4) if (ll == ll and ll) else round(float(c), 4)])
        if len(rows) >= 40:
            return rows, "yfinance"
    except Exception:
        pass
    try:
        import tiingo_connector as _tg          # official-API fallback (no-op unless TIINGO_API_KEY set)
        tr = _tg.fetch_rows(t)
        if tr and len(tr) >= 40:
            return tr, "Tiingo"
    except Exception:
        pass
    sr = _stooq(t)
    return (sr, "Stooq") if sr else (None, None)

def _load_hist(hist_dir, t):
    """Read committed daily rows [[date,close,vol],..] + source from <hist_dir>/<T>.json (no network)."""
    try:
        with open(os.path.join(hist_dir, t + ".json")) as f:
            j = json.load(f) or {}
            return (j.get("rows") or None), j.get("source")
    except Exception:
        return None, None

def emit(universe_path, out_dir, do_hist=False, cap=0, hist_dir=None):
    d = json.load(open(universe_path)); names = d.get("names", [])
    cdir = os.path.join(out_dir, "cards"); hdir = os.path.join(out_dir, "hist")
    os.makedirs(cdir, exist_ok=True); os.makedirs(hdir, exist_ok=True)
    nc = nh = 0; srccount = {}; linerr = 0
    for n in names:
        t = n.get("t")
        if not t: continue
        fetched, fsrc = history(t) if (do_hist and (not cap or nh < cap)) else (None, None)
        if fetched:
            rows, rsrc = fetched, fsrc
        elif hist_dir:
            rows, rsrc = _load_hist(hist_dir, t)
        else:
            rows, rsrc = None, None
        if rsrc:
            n["histSource"] = rsrc                       # per-ticker provenance for the UI
            srccount[rsrc] = srccount.get(rsrc, 0) + 1
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
                    # Second/Third Build: EVT POT/GPD tail on DAILY returns (250+ pts, robust)
                    _cl=[float(r[1]) for r in rows if r[1] is not None]
                    _dret=[]
                    for _i in range(1,len(_cl)):
                        if _cl[_i-1]>0 and _cl[_i]>0:
                            import math as _m; _dret.append(_m.log(_cl[_i]/_cl[_i-1]))
                    _ev=_lineage.evt_gpd_tail(_dret)
                    if _ev: lin["evt"]=_ev
                    # alert score A (spec): edge / tail / liquidity / modellable / governance
                    _g=lin.get("gov") or {}
                    _blh=((lin.get("bl") or {}).get("horizons") or {}).get(_g.get("horizon") or "20d") or {}
                    _edge=(_blh.get("postMu",0.0) or 0.0)-(_blh.get("priorMu",0.0) or 0.0)
                    _es=((_g.get("es975") or {}).get("es")) or 0.0
                    _pmax=max((lin.get("post") or [0]) or [0])
                    _vb=va.get("base") or {}
                    _G={"deployable":1.0,"research-only":0.5}.get(_g.get("releaseGate","blocked"),0.0)
                    _M=1 if ((lin.get("pq") or {}).get("modellable") or lin.get("factor")) else 0
                    lin["alert"]=_lineage.alert_score(_pmax,_edge,_es,_vb.get("avgVol20"),_vb.get("medVol"),_M,_G)
            except Exception as _le:
                # Fail soft (one bad ticker must not abort the whole emit) BUT make it visible:
                # a silent swallow here would drop sigvol/touch/EVT/alert-score for the name unnoticed.
                linerr += 1
                if linerr <= 8:
                    import sys as _s
                    _s.stderr.write("::warning:: emit_static: lineage augment failed for %s: %s\n" % (t, str(_le)[:120]))
        _write_json(os.path.join(cdir, t + ".json"), n)
        nc += 1
        if fetched:
            _write_json(os.path.join(hdir, t + ".json"),
                        {"ticker": t, "asof": fetched[-1][0], "count": len(fetched), "rows": fetched, "source": fsrc})
            nh += 1
    _write_json(os.path.join(out_dir, "cards_index.json"),
                {"asof": d.get("asof"), "source": d.get("source"), "histSources": srccount,
                 "cards": [n["t"] for n in names if n.get("t")], "count": nc, "hist": nh})
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
