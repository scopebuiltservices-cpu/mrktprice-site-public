"""Analyst-estimate consensus snapshot store (stdlib only).

WHY: FMP's analyst-estimates endpoint returns the consensus BY FISCAL PERIOD as of *now* — it does
NOT expose a timestamped revision history (how the consensus for a quarter moved over calendar time).
To answer "how did consensus move after the print?" we must SNAPSHOT the current forward consensus on
every build and accumulate it, then diff over time. This mirrors the BS-calibration snapshot pattern.

Store: append-only JSONL, one record per (ticker, asof-date, fiscal-period):
    {"sym":"AAPL","asof":"2026-06-26","period":"2026-09-30","eps":7.21,"n":34,"rev":4.2e11}
Atomic writes via verify_artifact when available. Research only.
"""
import json, os
try:
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # tools/ for verify_artifact
    import verify_artifact as _va
except Exception:
    _va = None


def _write(path, data):
    if _va:
        _va.write_atomic(path, data)
    else:
        d = os.path.dirname(os.path.abspath(path)) or "."
        os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)


def _read_rows(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue
    return rows


def record(path, sym, asof, period, eps, n=None, rev=None):
    """Append one consensus snapshot. Idempotent on (sym, asof, period) — a re-run the same day
    for the same fiscal period does not duplicate. Returns True if a new record was written."""
    if eps is None or not sym or not asof:
        return False
    sym = str(sym).upper(); period = str(period or "")
    for r in _read_rows(path):
        if r.get("sym") == sym and r.get("asof") == asof and str(r.get("period") or "") == period:
            return False
    rec = {"sym": sym, "asof": asof, "period": period, "eps": eps}
    if n is not None:
        rec["n"] = n
    if rev is not None:
        rec["rev"] = rev
    prev = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            prev = f.read()
        if prev and not prev.endswith("\n"):
            prev += "\n"
    _write(path, prev + json.dumps(rec, separators=(",", ":")) + "\n")
    return True


def revision(path, sym, since_iso, period=None):
    """Consensus drift for `sym` since `since_iso` (e.g. the last report date), for a SINGLE fiscal
    period so the comparison is apples-to-apples. Uses the earliest snapshot on/after since_iso vs the
    latest. Returns {eps0,d0,eps1,d1,dPct,n} or None when <2 comparable snapshots exist yet."""
    if not sym or not since_iso:
        return None
    sym = str(sym).upper(); period = None if period is None else str(period)
    rows = [r for r in _read_rows(path)
            if str(r.get("sym") or "").upper() == sym and r.get("eps") is not None
            and (period is None or str(r.get("period") or "") == period)]
    if not rows:
        return None
    rows.sort(key=lambda r: r.get("asof") or "")
    after = [r for r in rows if (r.get("asof") or "") >= since_iso]
    if len(after) < 2:
        return None
    a, b = after[0], after[-1]
    if a.get("eps") in (None, 0):
        return None
    return {"eps0": a["eps"], "d0": a["asof"], "eps1": b["eps"], "d1": b["asof"],
            "dPct": round(100.0 * (b["eps"] - a["eps"]) / abs(a["eps"]), 2), "n": b.get("n")}


def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Analyst-estimate consensus snapshot store.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record"); r.add_argument("path"); r.add_argument("sym"); r.add_argument("asof"); r.add_argument("period"); r.add_argument("eps", type=float); r.add_argument("--n", type=int, default=None)
    v = sub.add_parser("revision"); v.add_argument("path"); v.add_argument("sym"); v.add_argument("since"); v.add_argument("--period", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "record":
        print("wrote" if record(a.path, a.sym, a.asof, a.period, a.eps, a.n) else "duplicate (skipped)")
        return 0
    if a.cmd == "revision":
        import json as _j; print(_j.dumps(revision(a.path, a.sym, a.since, a.period), indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(_main())
