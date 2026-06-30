"""Per-maturity risk-free curve. Pulls US Treasury par yields from FRED (keyless CSV) and converts them
to a ZERO/discount curve before use, because the published CMT series are COUPON-bearing par yields, not
zero rates — discounting an option off log(1+par_yield) is only a front-end approximation that degrades on
a steep or kinked curve. We therefore:
  1. keep money-market maturities (< 0.5y) as single-payment zeros: z_cc = ln(1+y),
  2. bootstrap the coupon region (>= 0.5y) as a semiannual PAR-bond bootstrap to recover discount factors:
         DF_n = (1 - (c_n/2) * sum_{i<n} DF_i) / (1 + c_n/2),   c_n = par yield at T_n = 0.5n,
     then z_cc(T_n) = -ln(DF_n)/T_n,
  3. interpolate LOG-LINEARLY in discount-factor space (equivalently linearly in zero*T), not in par-yield
     space. rate_for(T) returns a continuously-compounded ZERO rate; df(T) returns the discount factor.
Falls back to a static recent curve so the pipeline never breaks offline. Research only."""
import math
from bisect import bisect_left

_FRED = {"DGS1MO": 1 / 12, "DGS3MO": 0.25, "DGS6MO": 0.5, "DGS1": 1, "DGS2": 2, "DGS3": 3, "DGS5": 5,
         "DGS7": 7, "DGS10": 10, "DGS20": 20, "DGS30": 30}
_FALLBACK = [(1 / 12, 0.0445), (0.25, 0.0440), (0.5, 0.0430), (1, 0.0410), (2, 0.0395), (3, 0.0390),
             (5, 0.0395), (7, 0.0405), (10, 0.0420)]


def fetch_curve(sess=None):
    pts = []
    try:
        import requests
        s = sess or requests.Session()
        for sid, yrs in _FRED.items():
            try:
                u = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
                txt = s.get(u, timeout=12).text.strip().splitlines()
                last = [r for r in txt[1:] if r.split(",")[-1] not in ("", ".")][-1]
                y = float(last.split(",")[-1]) / 100.0
                pts.append((yrs, y))
            except Exception:
                continue
    except Exception:
        pass
    pts = sorted(pts) if len(pts) >= 4 else list(_FALLBACK)
    return pts


def _interp_yield(pts, T):
    """Linear interpolation of PAR yield in maturity space (used only to fill the half-year coupon grid)."""
    if T <= pts[0][0]:
        return pts[0][1]
    if T >= pts[-1][0]:
        return pts[-1][1]
    for (t0, y0), (t1, y1) in zip(pts, pts[1:]):
        if t0 <= T <= t1:
            w = (T - t0) / (t1 - t0)
            return y0 + w * (y1 - y0)
    return pts[-1][1]


def bootstrap_zero(pts):
    """Par-yield pillars -> [(T, zero_cc)] zero curve. Money-market (<0.5y) kept as ln(1+y) single-payment
    zeros; coupon region bootstrapped on a semiannual grid out to the longest pillar. Returns sorted pillars."""
    pts = sorted(pts)
    if not pts:
        return [(t, math.log(1 + y)) for t, y in _FALLBACK]
    out = []
    # money-market front end: treat as a single payment (coupon-equivalent), zero ~ ln(1+y)
    for t, y in pts:
        if t < 0.5:
            out.append((t, math.log(1.0 + y)))
    # semiannual par-bond bootstrap for the coupon region
    Tmax = pts[-1][0]
    n_max = int(round(Tmax / 0.5))
    dfs = []  # DF at 0.5, 1.0, ... 0.5*n_max
    for n in range(1, n_max + 1):
        Tn = 0.5 * n
        c = _interp_yield(pts, Tn)            # par coupon rate at Tn (annual)
        coup = c / 2.0                        # semiannual coupon
        s = sum(dfs)                          # sum of prior discount factors
        df_n = (1.0 - coup * s) / (1.0 + coup)
        if df_n <= 0 or df_n > 1.5:           # numerical guard against degenerate inputs
            df_n = math.exp(-math.log(1.0 + c) * Tn)
        dfs.append(df_n)
        z = -math.log(df_n) / Tn if df_n > 0 else math.log(1.0 + c)
        out.append((Tn, z))
    # de-dup by maturity, prefer the coupon-bootstrapped value where both exist
    seen = {}
    for t, z in out:
        seen[round(t, 6)] = z
    return sorted((t, z) for t, z in seen.items())


class ZeroCurve:
    """Zero (continuously-compounded) curve with log-linear interpolation in discount-factor space."""

    def __init__(self, zero_pillars):
        zp = sorted(zero_pillars)
        self.T = [t for t, _ in zp]
        self.r = [r for _, r in zp]

    def df(self, T):
        T = max(float(T), 1e-9)
        if T <= self.T[0]:
            return math.exp(-self.r[0] * T)
        if T >= self.T[-1]:
            return math.exp(-self.r[-1] * T)
        j = bisect_left(self.T, T)
        t0, t1 = self.T[j - 1], self.T[j]
        ln0 = -self.r[j - 1] * t0
        ln1 = -self.r[j] * t1
        w = (T - t0) / (t1 - t0)
        return math.exp((1 - w) * ln0 + w * ln1)   # log-linear in DF space

    def rate_for(self, T):
        T = max(float(T), 1e-9)
        return -math.log(self.df(T)) / T


class Curve:
    """Backward-compatible wrapper: accepts PAR-yield points, bootstraps a zero curve internally, and
    exposes rate_for(T) (now a true zero rate) and df(T)."""

    def __init__(self, pts=None):
        self.pts = sorted(pts or _FALLBACK)
        self._zero = ZeroCurve(bootstrap_zero(self.pts))

    def rate_for(self, T):
        return self._zero.rate_for(T)

    def df(self, T):
        return self._zero.df(T)

    def par_rate_approx(self, T):
        """The OLD front-end approximation (log(1+par_yield)); kept only for comparison/diagnostics."""
        p = self.pts
        if T <= p[0][0]:
            y = p[0][1]
        elif T >= p[-1][0]:
            y = p[-1][1]
        else:
            y = _interp_yield(p, T)
        return math.log(1 + y)


def default_curve():
    return Curve(_FALLBACK)
