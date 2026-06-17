#!/usr/bin/env python3
"""Validate a freshly-built Market Map snapshot, then publish it only if sane.
Usage: validate_publish.py <src.json> <dest.json>
Refuses to overwrite the destination unless the new snapshot has >=30 names and
every name carries its metric fields — so a partial/failed live fetch never wipes
the committed sample."""
import json, sys
src, dest = sys.argv[1], sys.argv[2]
d = json.load(open(src))
names = d.get("names", [])
assert len(names) >= 30, f"too few names ({len(names)}) - refusing to publish"
assert all(("z" in n and "ret" in n) for n in names), "missing metric fields"
json.dump(d, open(dest, "w"), separators=(",", ":"))
print(f"Market Map refreshed: {len(names)} names, asof {d.get('asof')}")
