#!/usr/bin/env python3
"""Post-build guard — confirm the FMP Ultimate history layer actually executed.

Problem it solves: new engine code can be committed to main and never run (or run but fail to
connect), so the published marketmap.json silently lacks the rate curve / commodities. This emits
a LOUD GitHub-Actions ::warning:: (visible in the run summary) whenever the FMP key is present but
marketmap.json carries no macroSeries — turning a silent gap into an obvious red flag.

Usage:  FMP_API_KEY=$FMP_API_KEY python verify_history.py marketmap.json
Exit code is always 0 (informational): enrichment degradation warns, it does not block the publish.
"""
import json, os, sys


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "marketmap.json"
    try:
        d = json.load(open(path))
    except Exception as e:
        print("::warning title=verify_history::could not read %s: %s" % (path, e))
        return 0

    ms = d.get("macroSeries") or {}
    tre = (ms.get("treasury") or {}).get("tenors") or {}
    comm = ms.get("commodities") or {}
    tenors = len([v for v in tre.values() if v is not None])
    ncomm = len(comm)
    has_key = bool(os.environ.get("FMP_API_KEY", "").strip())

    # per-name attribution coverage: how many names actually cite a commodity driver?
    names = d.get("names", [])
    cset = set()
    if isinstance(ms.get("commodityKeys"), dict):
        cset = {str(v).lower() for v in ms["commodityKeys"].values()} | {k.lower() for k in ms["commodityKeys"]}
    cited = 0
    for n in names:
        labs = [str(x.get("f", "")).lower() for x in (n.get("deps") or [])]
        if cset and any(l in cset for l in labs):
            cited += 1

    print("::notice title=FMP history::macroSeries=%s | curve tenors=%d | commodities=%d | "
          "names citing a commodity driver=%d/%d | source=%s"
          % (bool(ms), tenors, ncomm, cited, len(names), d.get("source")))

    if has_key and not ms:
        print("::warning title=FMP history MISSING::FMP key is set but marketmap.json has NO macroSeries "
              "(no Treasury curve / commodities). The history layer did not run or could not connect — "
              "check tools/market_map/fmp_history.py and FMP Ultimate connectivity.")
    elif has_key and ncomm < 10:
        print("::warning title=FMP commodities thin::only %d commodities in macroSeries (expected ~30). "
              "Check the FMP commodities-list pull." % ncomm)
    elif has_key and tenors < 6:
        print("::warning title=Treasury curve thin::only %d curve tenors present (expected up to 12). "
              "Check the FMP treasury-rates pull." % tenors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
