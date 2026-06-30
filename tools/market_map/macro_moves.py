#!/usr/bin/env python3
"""macro_moves.py — compute each dependent commodity's / interest-rate's CURRENT move and how many sigma
that move is, from the build's own macroSeries (commodities[*].wr weekly-return series + treasury.series
daily yield levels). Combined with a name's per-driver sensitivity (sens = % stock move per +1 sigma of the
driver), this yields the LIVE implied contribution: implied % = sens x driverSigma.

Pure stdlib, offline-tested. This is the data behind "the specific percentages and sigma deviations from the
dependent commodities and interest rates the company value is trading at." Research only."""
import math


def _stdev(xs):
    xs = [x for x in xs if isinstance(x, (int, float)) and x == x]
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5


def _norm(s):
    s = str(s or "").lower().strip()
    for suf in (" futures", "_futures", " future"):
        s = s.replace(suf, "")
    return s.replace("_", " ").replace("  ", " ").strip()


_VOL_FLOOR = 1e-6   # below this a driver series is effectively flat -> sigma is undefined, report 0
_SIGMA_CAP = 8.0    # clamp absurd sigma from thin/degenerate data (8 sigma is already an extreme move)


def _sig(move, vol):
    if not vol or vol < _VOL_FLOOR:
        return 0.0
    return max(-_SIGMA_CAP, min(_SIGMA_CAP, move / vol))


def _row(move, vol, last, name, label):
    return {"movePct": round(move * 100.0, 2), "sigma": round(_sig(move, vol), 2), "vol": round(vol, 4),
            "last": last, "name": name, "label": label}


def compute(macro_series, recent=1):
    """Return {key: {movePct, sigma, vol, last, name, label}} keyed by BOTH normalized name and label,
    so report rows (human names like 'Copper', '10Y yield') and n.mb labels both resolve. `recent` = how
    many trailing weekly returns to sum for the 'current move' (1 = last week)."""
    out = {}
    ms = macro_series or {}
    com = ms.get("commodities") or {}
    for sym, d in (com.items() if isinstance(com, dict) else []):
        wr = d.get("wr") or []
        if len(wr) < 4:
            continue
        move = sum(wr[-recent:]) if recent <= len(wr) else sum(wr)
        vol = _stdev(wr)
        name, label = d.get("name") or sym, d.get("label") or sym
        r = _row(move, vol, d.get("last"), name, label)
        out[_norm(name)] = r
        out[_norm(label)] = r
        out[label] = r
    # interest rates from the treasury daily levels
    tre = ms.get("treasury") or {}
    series = tre.get("series") or {}
    def _yield_move(tenor, lookback=5):
        ser = series.get(tenor) or []
        lv = [p[1] for p in ser if isinstance(p, (list, tuple)) and len(p) > 1 and isinstance(p[1], (int, float))]
        if len(lv) < lookback + 2:
            return None
        diffs = [lv[i] - lv[i - 1] for i in range(1, len(lv))]
        chg = lv[-1] - lv[-1 - lookback]
        vol = _stdev(diffs) * (lookback ** 0.5)
        sigma = _sig(chg, vol)
        return {"movePct": round(chg, 3), "moveBps": round(chg * 100, 1), "sigma": round(sigma, 2),
                "vol": round(vol, 4), "last": lv[-1], "name": "%s yield" % tenor, "label": "RATE"}
    rate = _yield_move("10Y")
    if rate:
        for k in ("10y yield", "rate", "interest rate", "10-year yield"):
            out[k] = rate
    slope = tre.get("slope2s10s")
    if isinstance(slope, list) and slope:
        lv = [p[1] for p in slope if isinstance(p, (list, tuple)) and len(p) > 1]
        if len(lv) >= 7:
            diffs = [lv[i] - lv[i - 1] for i in range(1, len(lv))]
            chg = lv[-1] - lv[-6]
            vol = _stdev(diffs) * (5 ** 0.5)
            out["2s10s slope"] = {"movePct": round(chg, 3), "sigma": round(_sig(chg, vol), 2),
                                  "vol": round(vol, 4), "last": lv[-1], "name": "2s10s slope", "label": "SLOPE"}
    return out


def lookup(factor_name, moves):
    """Resolve a sensitivity row's factor (human name or label) to its computed move, defensively."""
    if not moves:
        return None
    return moves.get(factor_name) or moves.get(_norm(factor_name)) or moves.get(str(factor_name))
