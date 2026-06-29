#!/usr/bin/env python3
"""sector_seed.py — make per-name SECTOR authoritative INSIDE the build, BEFORE the sector consumers run.

The build groups by n["sec"] for sector-relative valuation, secRel (opportunity rank), and sector
correlation/dependency. Those run with the seed label. This applies the authoritative GICS sector from the
PRIOR run's committed data/profile.json (sector is ~static, so one-build-stale is irrelevant) at the start
of build() so every in-build sector consumer uses it. The nightly fmp_profile refreshes profile.json and
post-build sector_reconcile applies the freshest pull. Preserves the original label in n["secSeed"].
Pure stdlib; offline-tested. Research only."""
import json, os

CANDIDATES = ("data/profile.json", "../../data/profile.json",
              os.path.join(os.environ.get("GITHUB_WORKSPACE", ""), "data", "profile.json"))


def load(path=None):
    """Load {ticker:{sector,...}} trying the explicit path then the standard repo locations."""
    paths = ([path] if path else []) + list(CANDIDATES)
    for p in paths:
        if p and os.path.exists(p):
            try:
                d = json.load(open(p))
                return {k: v for k, v in d.items() if not k.startswith("_")}
            except Exception:
                continue
    return {}


def apply_authoritative(names, prof):
    """Override each name's sector with the authoritative GICS one. Preserves the seed label in n['secSeed'].
    ETF/macro names (no equity sector in the profile) are left untouched. Returns count overridden."""
    if not prof:
        return 0
    done = 0
    for n in names:
        tk = (n.get("t") or n.get("sym") or "").upper()
        rec = prof.get(tk) if tk else None
        auth = rec.get("sector") if isinstance(rec, dict) else None
        if not auth:
            continue
        if n.get("secSeed") is None:
            n["secSeed"] = n.get("sec")                     # keep the original seed label for the mismatch flag
        if auth != n.get("sec"):
            n["sec"] = auth
            done += 1
    return done
