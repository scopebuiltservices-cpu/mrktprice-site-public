#!/usr/bin/env python3
"""
engine_ref.py — pure-stdlib Python reference for the DETERMINISTIC estimators in engine.js
(EMA, rolling realized vol, OU AR(1) fit, Lo-MacKinlay variance ratio). Mirrors engine.js
line-for-line so the two languages can be locked to identical decimals via a committed golden
fixture (engine_golden.json), exactly like stats_ref.py/stats_golden.json does for ADF/KPSS and
pooled_rigor does for the bootstrap tests.

`gen_fixture()` builds inputs (committed in the fixture so neither language re-generates them) and
the Python-computed expected outputs. test_engine_ref.py locks Python to the fixture;
tools/test_engine_parity.mjs locks engine.js to the SAME fixture. (GARCH QMLE is intentionally
excluded — its iterative optimizer is not bit-reproducible across languages; it keeps its
planted-structure test in test_engine_estimators.mjs.)
"""
import json, math, os


# ---- estimators (mirror engine.js exactly) ----
def ema(c, N):
    a = 2.0 / (N + 1)
    e = c[0]; o = [e]
    for i in range(1, len(c)):
        e = a * c[i] + (1 - a) * e
        o.append(e)
    return o


def _vr(a):
    m = sum(a) / len(a)
    return sum((y - m) * (y - m) for y in a) / (len(a) - 1)


def _sd(a):
    return math.sqrt(_vr(a))


def hv_roll_series(r, w):
    o = []
    for i in range(w, len(r) + 1):
        o.append(_sd(r[i - w:i]) * math.sqrt(252))
    return o


def ou_fit(x):
    n = len(x)
    if n < 30:
        return None
    Y = x[1:]; Xl = x[:n - 1]; m = len(Y)
    mxl = sum(Xl) / m; myl = sum(Y) / m
    sxx = 0.0; sxy = 0.0
    for i in range(m):
        sxx += (Xl[i] - mxl) * (Xl[i] - mxl)
        sxy += (Xl[i] - mxl) * (Y[i] - myl)
    phi = sxy / sxx
    c = myl - phi * mxl
    sse = 0.0
    for i in range(m):
        e = Y[i] - (c + phi * Xl[i])
        sse += e * e
    s2 = sse / (m - 2)
    sePhi = math.sqrt(s2 / sxx)
    phi = min(max(phi, -0.9999), 0.9999)
    meanRev = (phi < 1) and ((1 - phi) > 1.96 * sePhi)
    theta = -math.log(phi) if (0 < phi < 1) else (math.inf if phi <= 0 else 0.0)
    mu = c / (1 - phi) if abs(1 - phi) > 1e-9 else sum(x) / n
    halfLife = (math.log(2) / theta) if (theta > 0 and math.isfinite(theta)) else math.inf
    sigmaX2 = s2 / (1 - phi * phi) if abs(phi) < 1 else math.inf
    last = x[n - 1]
    z = (last - mu) / math.sqrt(sigmaX2) if (sigmaX2 > 0 and math.isfinite(sigmaX2)) else 0.0
    return {"phi": phi, "sePhi": sePhi, "theta": theta, "mu": mu, "muPrice": math.exp(mu),
            "halfLife": halfLife, "sigmaX2": sigmaX2, "meanRev": bool(meanRev), "z": z, "last": last}


def variance_ratio(r, q):
    n = len(r)
    if n < 2 * q or q < 2:
        return {"vr": 1, "z": 0}
    mu = sum(r) / n
    va = sum((ri - mu) * (ri - mu) for ri in r) / (n - 1)
    if va <= 0:
        return {"vr": 1, "z": 0}
    mm = q * (n - q + 1) * (1 - q / n)
    if mm <= 0:
        return {"vr": 1, "z": 0}
    sc = 0.0
    for i in range(q - 1, n):
        s = 0.0
        for j in range(q):
            s += (r[i - j] - mu)
        sc += s * s
    vq = sc / mm
    vr = vq / va
    phi = 2 * (2 * q - 1) * (q - 1) / (3.0 * q * n)
    return {"vr": vr, "z": (vr - 1) / math.sqrt(phi) if phi > 0 else 0}


# ---- deterministic input generation (mulberry32 -> Box-Muller); arrays are committed ----
def _mul32(seed):
    a = seed & 0xFFFFFFFF
    def rnd():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = ((a ^ (a >> 15)) * (1 | a)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) ^ t) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0
    return rnd


def _gauss(rnd):
    u = 0.0; v = 0.0
    while u == 0.0:
        u = rnd()
    while v == 0.0:
        v = rnd()
    return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)


def gen_fixture():
    # EMA / HV inputs: a smooth-ish price series + its log returns
    closes = [round(100 + 8 * math.sin(i * 0.21) + 0.05 * i, 6) for i in range(60)]
    rets = [round(math.log(closes[i] / closes[i - 1]), 8) for i in range(1, len(closes))]
    # OU input: planted AR(1) phi=0.7 (finite, mean-reverting), deterministic noise
    r = _mul32(12345)
    x = [0.0]
    for _ in range(140):
        x.append(round(0.7 * x[-1] + _gauss(r), 6))
    inputs = {"ema_c": closes, "ema_N": 5, "hv_r": rets, "hv_w": 10, "ou_x": x, "vr_r": rets, "vr_q": 4}
    expected = {
        "ema": ema(closes, 5),
        "hv": hv_roll_series(rets, 10),
        "ou": ou_fit(x),
        "vr": variance_ratio(rets, 4),
    }
    return {"inputs": inputs, "expected": expected}


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine_golden.json")
    json.dump(gen_fixture(), open(out, "w"), separators=(",", ":"))
    print("wrote", os.path.normpath(out))


if __name__ == "__main__":
    main()
