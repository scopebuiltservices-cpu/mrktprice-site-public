#!/usr/bin/env python3
"""
flow_keyless.py — REAL institutional flow from the KEYLESS SEC 13F aggregates (institutional.json).

The flow tile previously showed only a price x volume money-flow PROXY. The nightly 13F engine
(build_institutional.py, free SEC 13F datasets) already produces per-issuer QoQ positioning:
  dShares  = % quarter-over-quarter change in institutional shares held (net accumulation/distribution)
  dHolders = change in the number of 13F holders (breadth)
This maps that into the flow shape so the tile reflects genuine institutional positioning, keylessly:
  net3m = dShares/100   (the 13F quarter ~ 3 months of net institutional flow)
  net1m = net3m / 3      (monthly proxy of the quarterly flow; 13F is quarterly)
Returns None when no 13F record (caller keeps the money-flow proxy). Pure-stdlib; unit-tested.
"""
__all__ = ["flow_from_13f"]


def flow_from_13f(inst):
    """institutional.json record -> {net3m, net1m, dHolders, holders, src} or None."""
    if not inst or inst.get("dShares") is None:
        return None
    try:
        ds = float(inst["dShares"]) / 100.0
    except Exception:
        return None
    if ds != ds:
        return None
    ds = max(-1.0, min(1.0, ds))                 # clamp absurd QoQ swings (brand-new / fully-exited positions)
    return {"net3m": round(ds, 4), "net1m": round(ds / 3.0, 4),
            "dHolders": inst.get("dHolders"), "holders": inst.get("holders"), "src": "SEC 13F"}
