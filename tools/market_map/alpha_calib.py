#!/usr/bin/env python3
"""Realized-outcome calibration for the Bull/Bear α score (the dashboard's market-neutral edge).

WHAT IT DOES (accumulating feedback loop, keyless):
  1. Recompute α per stock from marketmap.json names — the SAME formula the terminal board uses
     (market-neutral: macro factor tilt ex-market + sector RS + short + opportunity + trend + flow,
      each z-scored across the universe).
  2. Append today's {date, ticker, alpha, px} to data/alpha_log.jsonl (px = last close from hist/).
  3. Attach the realized forward return to past log rows once HORIZON_DAYS have elapsed
     (fwd = px_now / px_then - 1).
  4. Fit OLS  fwd ~ a + b*alpha  over all resolved rows  -> coef b (return per 1 unit α), intercept a,
     Pearson IC and rank IC, n. Emit alpha_calib.json so the terminal reads α directly in expected
     1-month return % :  expRet = a + b*alpha  (falls back to α*dispersion until n is sufficient).

NO API KEY. Run nightly after the build writes marketmap.json + hist/. Fail-soft.
Usage: python3 alpha_calib.py [--mm marketmap.json] [--hist hist] [--log data/alpha_log.jsonl] [--out alpha_calib.json] [--horizon 21]
"""
import json, os, sys, argparse, datetime as dt

W = dict(tilt=0.35, sector=0.25, short=0.15, opp=0.15, trend=0.07, flow=0.03)


def _last_close(histdir, t):
    """Read the last close from hist/<T>.json, tolerant of trailing data."""
    p = os.path.join(histdir, t + ".json")
    if not os.path.exists(p):
        return None
    try:
        raw = open(p).read()
        obj, _ = json.JSONDecoder().raw_decode(raw.lstrip())
        rows = obj.get("rows") if isinstance(obj, dict) else (obj if isinstance(obj, list) else None)
        if not rows:
            return None
        last = rows[-1]
        if isinstance(last, (list, tuple)) and len(last) >= 2:
            return float(last[1])
        if isinstance(last, dict):
            for k in ("c", "close", "px"):
                if last.get(k) is not None:
                    return float(last[k])
    except Exception:
        return None
    return None


def _z(vals):
    n = len(vals)
    if n < 2:
        return [0.0] * n
    m = sum(vals) / n
    sd = (sum((v - m) ** 2 for v in vals) / (n - 1)) ** 0.5 or 1.0
    return [(v - m) / sd for v in vals]


def compute_alpha(names):
    """Mirror of the terminal board's α (market-neutral)."""
    def nm(t):
        for x in names:
            if (x.get("t") or "").upper() == t:
                return x
        return None

    def rw(t):
        x = nm(t)
        return (x.get("ret") or {}).get("1w") if x and x.get("ret") else 0.0
    dMKT = rw("SPY") or 0.0
    DIR = {"OIL": rw("USO") or 0.0, "DXY": rw("UUP") or 0.0, "RATE": -(rw("TLT") or 0.0), "VIX": (rw("USMV") or 0.0) - dMKT}
    rows = []
    for x in names:
        t = (x.get("t") or "").upper()
        if not t:
            continue
        mb = x.get("mb") or {}
        # ETFs have no fundamentals/short -> skip (board excludes them); detect by missing val+short
        if not (x.get("val") or x.get("short") or x.get("secRel") is not None):
            continue
        tilt = sum((mb.get(k, 0) or 0) * DIR[k] for k in DIR)
        sh = x.get("short") or {}
        lvl = {"low": 0, "moderate": 1, "high": 2, "extreme": 3}.get(sh.get("level"), 0)
        shp = lvl + (1 if sh.get("trend") == "rising" else (-0.5 if sh.get("trend") == "falling" else 0))
        rows.append(dict(t=t, tilt=tilt, short=-shp, sector=(x.get("secRel") or 0), opp=(x.get("opp") or 0),
                         ema=(x.get("ema21sig") or 0), r1m=((x.get("ret") or {}).get("1m") or 0),
                         flow=((x.get("flow") or {}).get("net1m") or 0)))
    if not rows:
        return {}, 0.0
    zt = _z([r["tilt"] for r in rows]); zse = _z([r["sector"] for r in rows]); zsh = _z([r["short"] for r in rows])
    zop = _z([r["opp"] for r in rows]); zem = _z([r["ema"] for r in rows]); zr = _z([r["r1m"] for r in rows]); zf = _z([r["flow"] for r in rows])
    out = {}
    for i, r in enumerate(rows):
        out[r["t"]] = (W["tilt"] * zt[i] + W["sector"] * zse[i] + W["short"] * zsh[i] + W["opp"] * zop[i]
                       + W["trend"] * ((zem[i] + zr[i]) / 2) + W["flow"] * zf[i])
    sigR = (sum(r["r1m"] ** 2 for r in rows) / len(rows)) ** 0.5
    return out, sigR


def _ols_ic(xs, ys):
    n = len(xs)
    mx = sum(xs) / n; my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs) or 1e-12
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    syy = sum((y - my) ** 2 for y in ys) or 1e-12
    b = sxy / sxx; a = my - b * mx
    ic = sxy / ((sxx ** 0.5) * (syy ** 0.5))
    # rank IC (Spearman)
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i]); rk = [0] * len(v)
        for pos, idx in enumerate(order):
            rk[idx] = pos
        return rk
    rx, ry = ranks(xs), ranks(ys)
    mrx = sum(rx) / n; mry = sum(ry) / n
    srxy = sum((rx[i] - mrx) * (ry[i] - mry) for i in range(n))
    srxx = sum((x - mrx) ** 2 for x in rx) or 1e-12; sryy = sum((y - mry) ** 2 for y in ry) or 1e-12
    ric = srxy / ((srxx ** 0.5) * (sryy ** 0.5))
    return a, b, ic, ric


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mm", default="marketmap.json")
    ap.add_argument("--hist", default="hist")
    ap.add_argument("--log", default="data/alpha_log.jsonl")
    ap.add_argument("--out", default="alpha_calib.json")
    ap.add_argument("--horizon", type=int, default=21)
    a = ap.parse_args()
    try:
        mm = json.load(open(a.mm))
    except Exception as e:
        sys.stderr.write("alpha_calib: cannot read %s (%s)\n" % (a.mm, str(e)[:80])); return 1
    names = mm.get("names") or []
    asof = (mm.get("asof") or dt.date.today().isoformat())[:10]
    alpha, sigR = compute_alpha(names)
    if not alpha:
        sys.stderr.write("alpha_calib: no alphas computed\n"); return 1

    os.makedirs(os.path.dirname(a.log) or ".", exist_ok=True)
    rows = []
    if os.path.exists(a.log):
        for line in open(a.log):
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    # 1) attach realized forward returns to matured, unresolved rows
    today = dt.date.fromisoformat(asof)
    px_now = {t: _last_close(a.hist, t) for t in alpha}
    for r in rows:
        if r.get("fwd") is not None:
            continue
        try:
            age = (today - dt.date.fromisoformat(r["d"][:10])).days
        except Exception:
            age = 0
        if age >= a.horizon and r.get("px") and px_now.get(r["t"]):
            try:
                r["fwd"] = round(px_now[r["t"]] / float(r["px"]) - 1.0, 6); r["resolvedAsof"] = asof
            except Exception:
                pass
    # 2) append today's snapshot (one row per ticker per asof; dedupe)
    have = set((r["d"][:10], r["t"]) for r in rows)
    for t, al in alpha.items():
        if (asof, t) in have:
            continue
        rows.append({"d": asof, "t": t, "alpha": round(al, 4), "px": (round(px_now[t], 4) if px_now.get(t) else None)})
    rows = rows[-20000:]
    tmp = a.log + ".tmp"
    with open(tmp, "w") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    os.replace(tmp, a.log)
    # 3) fit over resolved rows
    res = [r for r in rows if r.get("fwd") is not None and r.get("alpha") is not None]
    calib = {"asof": asof, "horizonDays": a.horizon, "n": len(res), "sigFallback": round(sigR, 4),
             "coef": None, "intercept": None, "ic": None, "rankIC": None, "mode": "fallback"}
    if len(res) >= 40:
        xs = [r["alpha"] for r in res][-5000:]; ys = [r["fwd"] * 100.0 for r in res][-5000:]   # fwd in %
        a0, b0, ic, ric = _ols_ic(xs, ys)
        calib.update(coef=round(b0, 4), intercept=round(a0, 4), ic=round(ic, 4), rankIC=round(ric, 4),
                     n=len(xs), mode="fitted")
    json.dump(calib, open(a.out, "w"), separators=(",", ":"))
    sys.stderr.write("alpha_calib: log=%d resolved=%d mode=%s%s\n" % (
        len(rows), len(res), calib["mode"], ("" if calib["mode"] == "fallback" else " coef=%s ic=%s" % (calib["coef"], calib["ic"]))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
