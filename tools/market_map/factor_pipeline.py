"""Factor orchestration for the Bull/Bear board (stdlib + tested factor_eval/ic_store/rate_real).

Per build it:
  1. assembles each non-ETF name's factor exposures, INCLUDING the calculus/accumulation factors
     (velocity, acceleration, 20/40/63-bar normalized accumulation) computed from closes+volume;
  2. snapshots them and matures past snapshots into a realized forward-IC history (ic_store);
  3. computes BH-FDR-gated, sign-aware, IC-weighted factor weights (factor_eval) once enough history
     has accrued, otherwise DEGRADES to labeled fixed priors;
  4. returns {factorWeights, factorMode, factorBreadth, factorIC, calc:{ticker:{...}}} to merge into
     marketmap.json. The board then ranks on realized predictive efficacy instead of folkloric weights.
Single entry point: run(names, store_dir). Research only.
"""
import os, math, datetime
_HERE = os.path.dirname(os.path.abspath(__file__))
import sys as _sys
_sys.path.insert(0, _HERE)
import factor_eval as fe, ic_store as ics

# fixed priors (match the board's documented weights) — used until forward-IC history is sufficient
PRIORS = {"macro": 0.28, "sector": 0.20, "short": 0.12, "opp": 0.12, "mom": 0.06,
          "velocity": 0.08, "flow3m": 0.05, "flow1m": 0.03, "ema": 0.06,
          "acc20": 0.0, "acc40": 0.0, "acc63": 0.0}
HORIZON = 20
MIN_HISTORY = 8          # matured IC points required before fitted weights go live


def _ema(a, N):
    if not a: return []
    k = 2.0 / (N + 1.0); e = a[0]; o = [e]
    for i in range(1, len(a)):
        e = k * a[i] + (1 - k) * e; o.append(e)
    return o


def _sd(a):
    n = len(a)
    if n < 2: return 0.0
    m = sum(a) / n
    return math.sqrt(sum((x - m) ** 2 for x in a) / (n - 1))


def velocity_accel(closes):
    """velocity=d(EMA21 log-price)/dt, acceleration=2nd diff, both normalized by return sigma so they are
    not hidden vol bets. Returns (vel, acc) or (None,None)."""
    c = [x for x in (closes or []) if x and x > 0]
    if len(c) < 26: return None, None
    lp = [math.log(x) for x in c]; e = _ema(lp, 21)
    rets = [lp[i] - lp[i - 1] for i in range(1, len(lp))]
    sig = _sd(rets[-60:]) or 1e-9
    v1 = e[-1] - e[-2]; v2 = e[-2] - e[-3]
    return v1 / sig, (v1 - v2) / sig


def accumulation(closes, vols, win):
    """Windowed normalized accumulation = sum(signed money-flow volume) / sum(volume) over last `win` bars.
    Money-flow multiplier uses close position vs the bar's high/low proxy (here close-to-close direction
    since only closes are available). In [-1,1]. Returns None if insufficient data."""
    c = [x for x in (closes or []) if x and x > 0]; v = vols or []
    n = min(len(c), len(v))
    if n < win + 1: return None
    num = den = 0.0
    for i in range(n - win, n):
        if i <= 0: continue
        sign = 1.0 if c[i] > c[i - 1] else (-1.0 if c[i] < c[i - 1] else 0.0)
        num += sign * v[i]; den += abs(v[i])
    return (num / den) if den > 0 else None


def factor_rows(names, is_etf=None):
    """Build [{t, px, F:{factor:val}}] for each non-ETF name with the fields the board uses."""
    rows = []
    for n in names:
        t = (n.get("t") or "").upper()
        if not t or (is_etf and is_etf(t)): continue
        cl = n.get("_cl") or []; px = cl[-1] if cl else None
        if not px: continue
        sh = n.get("short") or {}; lvl = {"low": 0, "moderate": 1, "high": 2, "extreme": 3}.get(sh.get("level"), 0)
        shp = lvl + (1 if sh.get("trend") == "rising" else (-0.5 if sh.get("trend") == "falling" else 0))
        ret = n.get("ret") or {}; flow = n.get("flow") or {}
        vel, acc = velocity_accel(cl); vols = n.get("_vol") or []
        F = {"macro": 0.0, "sector": (n.get("secRel") or 0), "short": -shp, "opp": (n.get("opp") or 0),
             "mom": (ret.get("1m") or 0), "ema": (n.get("ema21sig") or 0),
             "velocity": (vel if vel is not None else 0.0), "flow3m": (flow.get("net3m") or 0),
             "flow1m": (flow.get("net1m") or 0),
             "acc20": (accumulation(cl, vols, 20) or 0.0), "acc40": (accumulation(cl, vols, 40) or 0.0),
             "acc63": (accumulation(cl, vols, 63) or 0.0)}
        rows.append({"t": t, "px": px, "F": F, "_vel": vel, "_acc": acc})
    return rows


def run(names, store_dir, is_etf=None, horizon=HORIZON):
    """Orchestrate the factor stack; returns a dict to merge into the payload."""
    os.makedirs(store_dir, exist_ok=True)
    snap_path = os.path.join(store_dir, "factor_snapshots.jsonl")
    ic_path = os.path.join(store_dir, "factor_ic.jsonl")
    asof = datetime.date.today().isoformat()
    rows = factor_rows(names, is_etf)
    if not rows:
        return {"factorMode": "none", "factorWeights": {}, "factorBreadth": 0.0}
    ics.snapshot(snap_path, asof, [{"t": r["t"], "px": r["px"], "F": r["F"]} for r in rows])
    px_now = {r["t"]: r["px"] for r in rows}
    ics.mature(snap_path, ic_path, asof, horizon, px_now)
    hist = ics.read_history(ic_path, horizon)
    factors = list(PRIORS.keys())
    have = hist and all(len(hist.get(f, [])) >= MIN_HISTORY for f in hist) and len(hist) >= 3 \
        and min((len(hist.get(f, [])) for f in hist)) >= MIN_HISTORY
    if have:
        w = fe.factor_weights({f: hist[f] for f in hist}, maxlags=horizon - 1)
        breadth = w.pop("_breadth", 0.0)
        weights = {f: w[f]["weight"] for f in w}
        ic_means = {f: w[f]["mean"] for f in w}
        mode = "fitted"
    else:
        weights = dict(PRIORS); breadth = 0.0; ic_means = {}
        mode = "priors"
    calc = {r["t"]: {"vel": (round(r["_vel"], 4) if r["_vel"] is not None else None),
                     "acc": (round(r["_acc"], 4) if r["_acc"] is not None else None),
                     "acc20": round(r["F"]["acc20"], 4), "acc40": round(r["F"]["acc40"], 4),
                     "acc63": round(r["F"]["acc63"], 4)} for r in rows}
    return {"factorMode": mode, "factorWeights": {k: round(v, 4) for k, v in weights.items()},
            "factorBreadth": round(breadth, 3), "factorIC": ic_means,
            "factorHistoryN": (min((len(v) for v in hist.values())) if hist else 0), "calc": calc}
