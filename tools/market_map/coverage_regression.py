#!/usr/bin/env python3
"""
coverage_regression.py — silent-breakage alarm over tools/.../health_log.jsonl.

Each nightly build appends one health record (build_integrity.health_log_record): data-quality
census, drift census, price source, rate source, sanitized-field count, fmpDegraded flag. A connector
that silently breaks usually shows up as a coverage domain that was non-zero the prior run dropping to
ZERO this run (e.g. dataQuality.clean 480 -> 0 because the price feed died). This compares the last two
records and flags those.

Severities:
  HARD  (exit 1): a numeric coverage metric was > 0 last run and is exactly 0 this run, OR fmpDegraded
                  flipped False -> True. These almost always mean a broken feed and should fail CI.
  WARN  (exit 0): a metric dropped by more than --warn-frac (default 0.5) but not to zero.

CLI:  python3 coverage_regression.py health_log.jsonl [--warn-frac 0.5] [--soft]
      --soft downgrades HARD to a warning (exit 0) for environments that only want a notice.
First-ever run (a single record) passes (nothing to compare).
"""
import argparse, json, sys


def flatten(rec):
    """Pull the numeric coverage metrics out of a health record into a flat {name: number}."""
    out = {}
    dq = rec.get("dataQuality") or {}
    for k in ("clean", "degraded", "reject"):
        if isinstance(dq.get(k), (int, float)) and not isinstance(dq.get(k), bool):
            out["dataQuality." + k] = dq[k]
    dc = rec.get("driftCensus") or {}
    for k in ("stable", "moderate", "significant", "baseline"):
        if isinstance(dc.get(k), (int, float)) and not isinstance(dc.get(k), bool):
            out["driftCensus." + k] = dc[k]
    if isinstance(rec.get("sanitizedFields"), (int, float)) and not isinstance(rec.get("sanitizedFields"), bool):
        out["sanitizedFields"] = rec["sanitizedFields"]
    return out


def compare(prev, curr, warn_frac=0.5):
    """Return list of (severity, metric, prev, curr, msg)."""
    alerts = []
    pf = flatten(prev); cf = flatten(curr)
    for k, pv in pf.items():
        cv = cf.get(k)
        if cv is None:
            continue
        # sanitizedFields RISING is bad-data-ish but not a coverage drop; skip its zero check.
        if pv > 0 and cv == 0 and k != "sanitizedFields":
            alerts.append(("HARD", k, pv, cv, "%s dropped to ZERO (was %s) — likely a broken feed" % (k, pv)))
        elif pv > 0 and cv < pv * (1.0 - warn_frac) and k != "sanitizedFields":
            alerts.append(("WARN", k, pv, cv, "%s fell %.0f%% (%s -> %s)" % (k, 100 * (1 - cv / pv), pv, cv)))
    # fmpDegraded flip False -> True
    if (not prev.get("fmpDegraded")) and curr.get("fmpDegraded"):
        alerts.append(("HARD", "fmpDegraded", False, True, "FMP went degraded (key present but 0 successful pulls)"))
    return alerts


def _read_records(path):
    recs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                pass
    return recs


def check_log(path, warn_frac=0.5):
    recs = _read_records(path)
    if len(recs) < 2:
        return 0, [], "only %d record(s) — nothing to compare" % len(recs)
    alerts = compare(recs[-2], recs[-1], warn_frac=warn_frac)
    rc = 1 if any(a[0] == "HARD" for a in alerts) else 0
    return rc, alerts, "compared %s -> %s" % (recs[-2].get("asof"), recs[-1].get("asof"))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--warn-frac", type=float, default=0.5)
    ap.add_argument("--soft", action="store_true", help="downgrade HARD to warning (always exit 0)")
    a = ap.parse_args(argv)
    try:
        rc, alerts, note = check_log(a.log, warn_frac=a.warn_frac)
    except FileNotFoundError:
        print("  skip  %s (absent)" % a.log)
        return 0
    print("coverage_regression: " + note)
    for sev, k, pv, cv, msg in alerts:
        print("  %-4s %s" % (sev, msg))
    if not alerts:
        print("  ok    no coverage regressions")
    if a.soft:
        return 0
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
