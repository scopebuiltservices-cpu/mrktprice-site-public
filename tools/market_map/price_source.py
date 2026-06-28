#!/usr/bin/env python3
"""
price_source.py — FMP-Ultimate-primary price hierarchy, extracted from build_market_map.py (stdlib + deps).

Single source of truth for daily OHLCV with credible failover:
    FMP Ultimate (paid, primary)  ->  yfinance (free backup, if enabled)  ->  miss
and a health tracker the build surfaces as dataHealth.priceSrc / fmpLastOk / fmpDegraded. Pulling this out
of the 1,900-line monolith makes the price path independently unit-testable and bash-verifiable, and stops
the monolith growing (see tools/MOUNT_VERIFICATION_PROTOCOL.md).

Dependency-injected so it tests without network: pass a `fmp` module exposing eod_ohlcv()/have_key(), and a
`yf` module exposing Ticker().history(). Returns dict(cl,hi,lo,vo,src) or None.
"""
import time


def _now_utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class PriceSource:
    def __init__(self, fmp=None, yf=None, session=None, now=None):
        self.fmp = fmp
        self.yf = yf
        self.sess = session
        self._now = now or _now_utc
        key = False
        try:
            key = bool(fmp and fmp.have_key())
        except Exception:
            key = False
        self.health = {"fmp": 0, "yf": 0, "miss": 0, "fmpLastOk": None,
                       "yfEnabled": bool(yf is not None), "yfImported": bool(yf is not None),
                       "fmpKeyPresent": key}

    def get(self, sym, min_rows=10):
        """FMP Ultimate first; yfinance fallback when enabled. dict(cl,hi,lo,vo,src) or None."""
        rows = None
        if self.fmp is not None:
            try:
                rows = self.fmp.eod_ohlcv(sym, sess=self.sess, min_rows=min_rows)
            except Exception:
                rows = None
        if rows:
            self.health["fmp"] += 1
            self.health["fmpLastOk"] = self._now()
            return {"cl": [r[4] for r in rows], "hi": [r[2] for r in rows], "lo": [r[3] for r in rows],
                    "vo": [float(r[5]) for r in rows], "src": "fmp"}
        if self.yf is not None:
            try:
                h = self.yf.Ticker(sym).history(period="1y", interval="1d", auto_adjust=True)
                cl = []; vo = []; hi = []; lo = []
                for c, v, H, Lw in zip(h["Close"].tolist(), h["Volume"].tolist(), h["High"].tolist(), h["Low"].tolist()):
                    c = float(c)
                    if c == c and c > 0:
                        cl.append(c); vo.append(float(v) if v == v else 0.0)
                        H = float(H); Lw = float(Lw); hi.append(H if H == H else c); lo.append(Lw if Lw == Lw else c)
                if len(cl) >= min_rows:
                    self.health["yf"] += 1
                    return {"cl": cl, "hi": hi, "lo": lo, "vo": vo, "src": "yfinance"}
            except Exception:
                pass
        self.health["miss"] += 1
        return None

    def price_share(self):
        h = self.health
        tot = h["fmp"] + h["yf"] + h["miss"]
        return round(100.0 * h["fmp"] / tot, 1) if tot else 0.0

    def degraded(self):
        return bool(self.health["fmpKeyPresent"] and self.health["fmp"] == 0)
