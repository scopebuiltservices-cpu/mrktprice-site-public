#!/usr/bin/env python3
"""state_persistence.py — consecutive-window state confirmation + hysteresis gate (pure stdlib).

The Frontier Econometrics synthesis is explicit: don't fire on a single abnormal reading — "confirm that
the state persists over consecutive 15-minute windows" before acting. A raw threshold crossing whipsaws
on noise; the fix is (a) require K_on consecutive windows in-state to ENTER, (b) require K_off consecutive
windows out-of-state to EXIT (hysteresis, so a single quiet bar doesn't drop a confirmed state), and
(c) expose the current run length / dwell so downstream sizing can scale with how established the state is.

This is a turnover/whipsaw control, not a predictor: it decides WHEN a detected state is trustworthy
enough to act on. Verified in test_state_persistence.py: a 1-bar flicker never confirms; a sustained run
confirms after exactly K_on; a single in-run dip does not un-confirm until K_off consecutive exits.
"""
from __future__ import annotations


def run_lengths(flags):
    """Trailing run length at each index: how many consecutive True's end here (0 when flags[i] False)."""
    out = []
    r = 0
    for f in flags:
        r = r + 1 if f else 0
        out.append(r)
    return out


class PersistenceGate:
    """Hysteresis state machine over a stream of boolean in-state observations.

    k_on : consecutive in-state windows required to CONFIRM (enter).
    k_off: consecutive out-of-state windows required to CLEAR (exit). Default = k_on.
    """

    def __init__(self, k_on: int = 2, k_off=None):
        self.k_on = max(1, int(k_on))
        self.k_off = max(1, int(k_off if k_off is not None else k_on))
        self.confirmed = False
        self._on_run = 0      # consecutive in-state
        self._off_run = 0     # consecutive out-of-state
        self.dwell = 0        # windows since the state was confirmed (0 when not confirmed)

    def update(self, in_state: bool) -> dict:
        """Feed one window's in-state boolean. Returns the gate state after this window."""
        if in_state:
            self._on_run += 1
            self._off_run = 0
        else:
            self._off_run += 1
            self._on_run = 0
        changed = False
        if not self.confirmed and self._on_run >= self.k_on:
            self.confirmed = True
            self.dwell = 0
            changed = True
        elif self.confirmed and self._off_run >= self.k_off:
            self.confirmed = False
            self.dwell = 0
            changed = True
        if self.confirmed:
            self.dwell += 1
        return {"confirmed": self.confirmed, "dwell": self.dwell,
                "onRun": self._on_run, "offRun": self._off_run, "changed": changed}


def confirm_series(flags, k_on: int = 2, k_off=None) -> dict:
    """Run a PersistenceGate over a whole boolean series. Returns the per-window confirmed[] mask, the
    dwell[] series, the fraction of raw crossings that survived confirmation, and the count of distinct
    confirmed episodes (a turnover proxy: fewer, longer episodes = less whipsaw)."""
    g = PersistenceGate(k_on, k_off)
    confirmed, dwell, episodes, prev = [], [], 0, False
    for f in flags:
        s = g.update(bool(f))
        confirmed.append(s["confirmed"])
        dwell.append(s["dwell"])
        if s["confirmed"] and not prev:
            episodes += 1
        prev = s["confirmed"]
    raw_on = sum(1 for f in flags if f)
    conf_on = sum(1 for c in confirmed if c)
    return {"confirmed": confirmed, "dwell": dwell, "episodes": episodes,
            "rawOnFrac": round(raw_on / len(flags), 4) if flags else 0.0,
            "confirmedOnFrac": round(conf_on / len(flags), 4) if flags else 0.0,
            "kOn": g.k_on, "kOff": g.k_off}
