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
                       "fmpKeyPresent": key, "yfTripped": False}
        # yfinance CIRCUIT BREAKER: on GitHub-Actions runners Yahoo frequently blocks/throttles the IP, so a
        # per-ticker .history() call hangs ~10s (curl 28, 0 bytes). Across a ~700-name universe that alone
        # blows the ~20-min job budget and trips the "refusing to publish synthetic data" guard. After
        # `_yf_break` consecutive yfinance failures we DISABLE yfinance for the rest of the run (FMP-only),
        # bounding total wasted time to ~_yf_break x 10s instead of N x 10s.
        self._yf_fail = 0
        self._yf_break = 5
        self._cache = {}                          # {sym: result} warmed by prefetch(); serves get_cached()

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
                    self._yf_fail = 0                      # success resets the breaker
                    return {"cl": cl, "hi": hi, "lo": lo, "vo": vo, "src": "yfinance"}
                self._yf_fail += 1                          # returned but too few rows counts as a failure
            except Exception:
                self._yf_fail += 1                          # timeout / blocked IP (curl 28) etc.
            if self._yf_fail >= self._yf_break:             # trip: stop hammering a dead provider this run
                self.yf = None
                self.health["yfTripped"] = True
        self.health["miss"] += 1
        return None

    def prefetch(self, symbols, workers=6):
        """Warm the price cache CONCURRENTLY so the serial per-name build loop hits cache instead of making
        ~700 sequential network calls (the root cause of the ~20-min timeout that froze publishes). Each
        symbol still runs the normal FMP-primary -> yfinance path incl. the circuit breaker; a bounded worker
        pool keeps request bursts modest. Health counters are diagnostic (not lock-guarded) so under
        concurrency they may be off by a few — acceptable. Returns cache size."""
        import concurrent.futures as _cf
        syms = [s for s in dict.fromkeys(symbols or []) if s]     # dedup, preserve order
        if not syms:
            return len(self._cache)
        w = max(1, min(int(workers or 1), 12))
        def _one(sym):
            try:
                return sym, self.get(sym)
            except Exception:
                return sym, None
        with _cf.ThreadPoolExecutor(max_workers=w) as ex:
            for sym, r in ex.map(_one, syms):
                self._cache[sym] = r
        return len(self._cache)

    def get_cached(self, sym, min_rows=10):
        """Cache-first accessor (build loop uses this). Serves a warmed result when it satisfies min_rows;
        a cached None (known failure) is returned as-is to avoid re-hammering; otherwise a live get()."""
        c = self._cache.get(sym, "\x00MISS")
        if c != "\x00MISS":
            if c is None or len((c.get("cl") if isinstance(c, dict) else None) or []) >= min_rows:
                return c
        r = self.get(sym, min_rows)
        self._cache[sym] = r
        return r

    def price_share(self):
        h = self.health
        tot = h["fmp"] + h["yf"] + h["miss"]
        return round(100.0 * h["fmp"] / tot, 1) if tot else 0.0

    def degraded(self):
        return bool(self.health["fmpKeyPresent"] and self.health["fmp"] == 0)
