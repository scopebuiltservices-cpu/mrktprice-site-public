"""Free-tier safety: per-source call BUDGET + min-interval THROTTLE + CIRCUIT BREAKER.

Goal: the nightly build NEVER breaks and NEVER blows a free-tier quota. Each source gets
a budget (max requests/run) and a minimum interval (respect per-minute limits). On the
first limit signal - HTTP 429 or a body containing 'limit'/'exceeded'/'quota' - the breaker
TRIPS and the source is skipped for the rest of the run, instead of hammering retries and
getting the key banned. A skipped layer just refills on the next nightly run.

Pure stdlib. The documented quotas below are conservative starting points; the breaker
(reacting to the live response) is the real safety net, since free limits change often.
"""
import time

# calls = max requests per run; interval = min seconds between requests.
LIMITS = {
    "finnhub":      {"calls": 55,  "interval": 1.1},   # ~60/min free
    "twelvedata":   {"calls": 40,  "interval": 8.0},   # 8/min, 800/day free
    "tiingo":       {"calls": 45,  "interval": 1.5},   # ~50 symbols/hr, 1000/day free
    "alphavantage": {"calls": 20,  "interval": 13.0},  # ~25/day, 5/min free - tiny
    "marketaux":    {"calls": 90,  "interval": 1.0},   # ~100/day free
    "fred":         {"calls": 120, "interval": 0.3},
    "fmp":          {"calls": 900, "interval": 0.0},   # paid Ultimate - high ceiling
    "eodhd":        {"calls": 200, "interval": 0.2},
}


class Limiter:
    """One per source per run. Bounds total calls, spaces them, and trips on a limit signal."""

    def __init__(self, name, calls=None, interval=None):
        cfg = LIMITS.get(name, {})
        self.name = name
        self.budget = calls if calls is not None else cfg.get("calls", 100)
        self.interval = interval if interval is not None else cfg.get("interval", 0.0)
        self.used = 0
        self.tripped = False
        self.reason = ""
        self._last = 0.0

    def ready(self):
        """True if a call is allowed (budget remaining AND breaker not tripped)."""
        return (not self.tripped) and self.used < self.budget

    def acquire(self):
        """Wait out the min interval, count the call, return True. Returns False (skip) if
        the budget is exhausted or the breaker has tripped."""
        if not self.ready():
            return False
        if self.interval > 0:
            wait = self.interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
        self._last = time.time()
        self.used += 1
        return True

    def trip(self, reason=""):
        """Limit hit -> disable this source for the rest of the run."""
        self.tripped = True
        self.reason = str(reason)[:120]

    def status(self):
        return {"source": self.name, "used": self.used, "budget": self.budget,
                "tripped": self.tripped, "reason": self.reason}

    @staticmethod
    def is_limit(status=0, body=""):
        """Detect a rate/quota limit from an HTTP status code or a response body."""
        try:
            if int(status) == 429:
                return True
        except Exception:
            pass
        low = str(body).lower()
        return any(s in low for s in ("limit reach", "rate limit", "exceeded",
                                      "too many requests", "quota", "bandwidth", "throttle"))


__all__ = ["Limiter", "LIMITS"]
