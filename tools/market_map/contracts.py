#!/usr/bin/env python3
"""contracts.py — typed forecast CONTRACTS that stop the silent mixing of incompatible horizons and
target spaces (the #1 integrity gap in the Anti-Deviation / Conformalized-Volatility spec).

Every forecast in MrktPrice answers a question of the form "over horizon H, what is the TARGET (a
log-return? a raw price? a price delta?) measured on WHICH price basis (raw close? split-adjusted?
total-return?)". Mixing a 1-bar next-bar hit-rate with a 21-day total-return band, or scoring a
log-return forecast against a raw-price realization, silently corrupts calibration. These frozen
dataclasses make the horizon and target explicit and raise on ill-formed or mismatched combinations.

Pure stdlib, no I/O, deterministic — safe to import anywhere (volterm/lineage/projledger/anti_deviation)."""
from dataclasses import dataclass, field
import math

# ---- allowed vocabularies (kept small + explicit so a typo is a hard error, not a silent drift) ----
UNITS = ("day", "bar", "minute")
LABEL_TYPES = ("close", "total_return", "high", "low", "touch", "vwap", "settle")
TARGET_SPACES = ("log_return", "simple_return", "log_price", "price_delta", "raw_price")
PRICE_BASES = ("raw_close", "split_adj", "total_return", "vwap")


@dataclass(frozen=True)
class HorizonSpec:
    """A forecast horizon, self-describing and self-validating.

    h              : horizon length in `unit`s (must be > 0)
    unit           : 'day' | 'bar' | 'minute'
    label_type     : what the terminal label is ('close', 'total_return', 'touch', ...)
    bar_minutes    : minutes per bar (REQUIRED when unit == 'bar')
    session_minutes: minutes in a trading session (REQUIRED when unit in {'bar','minute'})
    includes_overnight : whether the horizon spans overnight gaps (affects variance scaling)
    calendar_id    : trading-calendar id (e.g. 'XNYS') so day counts are unambiguous
    """
    h: int
    unit: str = "day"
    label_type: str = "close"
    bar_minutes: int = 0
    session_minutes: int = 0
    includes_overnight: bool = True
    calendar_id: str = "XNYS"

    def __post_init__(self):
        if not (isinstance(self.h, (int, float)) and self.h > 0):
            raise ValueError("HorizonSpec.h must be > 0 (got %r)" % (self.h,))
        if self.unit not in UNITS:
            raise ValueError("HorizonSpec.unit must be one of %s (got %r)" % (UNITS, self.unit))
        if self.label_type not in LABEL_TYPES:
            raise ValueError("HorizonSpec.label_type must be one of %s (got %r)" % (LABEL_TYPES, self.label_type))
        if self.unit == "bar" and not (self.bar_minutes and self.bar_minutes > 0):
            raise ValueError("HorizonSpec: unit='bar' requires bar_minutes > 0")
        if self.unit in ("bar", "minute") and not (self.session_minutes and self.session_minutes > 0):
            raise ValueError("HorizonSpec: unit=%r requires session_minutes > 0" % (self.unit,))

    def bars(self):
        """Horizon length expressed in its native sampling bars (h for bar/day; h minute-bars for minute)."""
        return self.h

    def session_bars(self):
        """Number of bars in one session (only defined for intraday bar horizons)."""
        if self.unit == "bar" and self.bar_minutes:
            return self.session_minutes / self.bar_minutes
        return None

    def horizon_minutes(self):
        """Approx wall-clock trading minutes the horizon spans (None if not derivable)."""
        if self.unit == "bar":
            return self.h * self.bar_minutes
        if self.unit == "minute":
            return self.h
        if self.unit == "day" and self.session_minutes:
            return self.h * self.session_minutes
        return None

    def key(self):
        """Stable string key for bucketing calibration records by horizon."""
        return "%s%s/%s" % (self.h, self.unit[0], self.label_type)


@dataclass(frozen=True)
class TargetBasis:
    """What quantity a forecast targets and on which price series it is measured.

    target_space : 'log_return' | 'simple_return' | 'log_price' | 'price_delta' | 'raw_price'
    price_basis  : 'raw_close' | 'split_adj' | 'total_return' | 'vwap'
    """
    target_space: str = "log_return"
    price_basis: str = "total_return"

    def __post_init__(self):
        if self.target_space not in TARGET_SPACES:
            raise ValueError("TargetBasis.target_space must be one of %s (got %r)" % (TARGET_SPACES, self.target_space))
        if self.price_basis not in PRICE_BASES:
            raise ValueError("TargetBasis.price_basis must be one of %s (got %r)" % (PRICE_BASES, self.price_basis))

    def transform_terminal(self, p0, p1):
        """Map an anchor price p0 and terminal price p1 into the target space. This is the ONE place
        the target transform lives, so a forecast and its realization are always compared in the same
        space. Raises for TOUCH labels (a touch is a probability event, not a point transform)."""
        if not (p0 and p0 > 0) or not (p1 and p1 > 0):
            raise ValueError("transform_terminal needs positive prices (p0=%r, p1=%r)" % (p0, p1))
        ts = self.target_space
        if ts == "log_return":
            return math.log(p1 / p0)
        if ts == "simple_return":
            return p1 / p0 - 1.0
        if ts == "log_price":
            return math.log(p1)
        if ts == "price_delta":
            return p1 - p0
        if ts == "raw_price":
            return p1
        raise ValueError("transform_terminal: unsupported target_space %r" % (ts,))

    def is_return_space(self):
        return self.target_space in ("log_return", "simple_return")


def compatible(a_h, a_t, b_h, b_t):
    """True iff two (HorizonSpec, TargetBasis) pairs may be pooled/compared: same horizon key, same
    target space, same price basis. Use before combining calibration residuals across records."""
    return (a_h.key() == b_h.key()
            and a_t.target_space == b_t.target_space
            and a_t.price_basis == b_t.price_basis)


# convenient canonical defaults matching the daily total-return series MrktPrice forecasts against
DAILY_21 = HorizonSpec(h=21, unit="day", label_type="close", session_minutes=390)
TOTAL_RETURN = TargetBasis(target_space="log_return", price_basis="total_return")
