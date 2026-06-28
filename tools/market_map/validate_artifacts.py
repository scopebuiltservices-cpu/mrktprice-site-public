#!/usr/bin/env python3
"""
validate_artifacts.py — contract gates for the secondary published JSON artifacts
(cik.json, alpha_calib.json, events.json, universe.json), matching the marketmap/xsection
schema-gate pattern. Pure stdlib (no jsonschema dep). Each validator returns (ok, errors[]).

CLI:  python3 validate_artifacts.py cik.json alpha_calib.json events.json universe.json
Exit non-zero if any named file fails its contract. Files passed but absent are skipped
(printed as a notice) so it is safe to call on a partial local build.
"""
import json, os, re, sys

_CIK = re.compile(r"^\d{10}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _isnum(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate_cik(d):
    e = []
    if not isinstance(d, dict):
        return False, ["cik: root must be an object {ticker: cik}"]
    if not d:
        e.append("cik: empty map")
    for k, v in list(d.items())[:100000]:
        if not isinstance(k, str) or not k.strip():
            e.append("cik: bad ticker key %r" % k)
        if not isinstance(v, str) or not _CIK.match(v):
            e.append("cik: %s -> %r is not a 10-digit zero-padded CIK" % (k, v))
            if len(e) > 20:
                break
    return (not e), e


def validate_alpha_calib(d):
    e = []
    if not isinstance(d, dict):
        return False, ["alpha_calib: root must be an object"]
    for k in ("asof", "horizonDays", "n", "mode"):
        if k not in d:
            e.append("alpha_calib: missing required key %r" % k)
    if "asof" in d and not (isinstance(d["asof"], str) and _DATE.match(d["asof"])):
        e.append("alpha_calib: asof not an ISO date: %r" % d.get("asof"))
    if "horizonDays" in d and not (isinstance(d["horizonDays"], int) and d["horizonDays"] > 0):
        e.append("alpha_calib: horizonDays must be a positive int")
    if "n" in d and not (isinstance(d["n"], int) and d["n"] >= 0):
        e.append("alpha_calib: n must be a non-negative int")
    if d.get("mode") not in ("fallback", "fitted"):
        e.append("alpha_calib: mode must be 'fallback' or 'fitted' (got %r)" % d.get("mode"))
    for k in ("coef", "intercept", "ic", "rankIC", "sigFallback"):
        if k in d and d[k] is not None and not _isnum(d[k]):
            e.append("alpha_calib: %s must be numeric or null" % k)
    if d.get("mode") == "fitted":
        for k in ("coef", "ic"):
            if d.get(k) is None:
                e.append("alpha_calib: mode=fitted requires non-null %s" % k)
    for k in ("ic", "rankIC"):
        v = d.get(k)
        if _isnum(v) and not (-1.0001 <= v <= 1.0001):
            e.append("alpha_calib: %s out of [-1,1]: %r" % (k, v))
    return (not e), e


def _validate_event(ev, where):
    e = []
    if not isinstance(ev, dict):
        return ["%s: event not an object" % where]
    if not (isinstance(ev.get("date"), str) and _DATE.match(ev.get("date") or "")):
        e.append("%s: event.date not an ISO date" % where)
    return e


def validate_events(d):
    e = []
    if not isinstance(d, dict):
        return False, ["events: root must be an object"]
    for k in ("asof", "schemaVersion", "nextHighImpact", "daysToNext", "upcoming", "recent"):
        if k not in d:
            e.append("events: missing required key %r" % k)
    if "asof" in d and not (isinstance(d["asof"], str) and _DATE.match(d["asof"])):
        e.append("events: asof not an ISO date")
    if d.get("daysToNext") is not None and not isinstance(d["daysToNext"], int):
        e.append("events: daysToNext must be int or null")
    for lk in ("upcoming", "recent"):
        if lk in d:
            if not isinstance(d[lk], list):
                e.append("events: %s must be a list" % lk)
            else:
                for i, ev in enumerate(d[lk][:50]):
                    e += _validate_event(ev, "events.%s[%d]" % (lk, i))
    nh = d.get("nextHighImpact")
    if nh is not None:
        e += _validate_event(nh, "events.nextHighImpact")
    # consistency: if there is an upcoming event, daysToNext should be >= 0
    if d.get("daysToNext") is not None and isinstance(d["daysToNext"], int) and d["daysToNext"] < -1:
        e.append("events: daysToNext negative (%r) — stale calendar" % d["daysToNext"])
    return (not e), e


def validate_universe(d):
    e = []
    if not isinstance(d, dict):
        return False, ["universe: root must be an object"]
    for k in ("asof", "schemaVersion", "count", "equities", "sectors", "indexMembership", "members"):
        if k not in d:
            e.append("universe: missing required key %r" % k)
    if "asof" in d and not (isinstance(d["asof"], str) and _DATE.match(d["asof"])):
        e.append("universe: asof not an ISO date")
    if "members" in d:
        if not isinstance(d["members"], list):
            e.append("universe: members must be a list")
        else:
            if "count" in d and isinstance(d["count"], int) and d["count"] != len(d["members"]):
                e.append("universe: count (%s) != len(members) (%s)" % (d["count"], len(d["members"])))
            seen = set()
            for i, m in enumerate(d["members"][:100000]):
                if not isinstance(m, dict) or not m.get("t"):
                    e.append("universe: members[%d] missing ticker" % i)
                    continue
                if m["t"] in seen:
                    e.append("universe: duplicate ticker %s" % m["t"])
                seen.add(m["t"])
                if "idx" in m and not isinstance(m["idx"], list):
                    e.append("universe: members[%d].idx must be a list" % i)
            if len(seen) == 0:
                e.append("universe: zero members")
    for dk in ("sectors", "indexMembership"):
        if dk in d and not isinstance(d[dk], dict):
            e.append("universe: %s must be an object" % dk)
    return (not e), e


_DISPATCH = {
    "cik.json": validate_cik,
    "alpha_calib.json": validate_alpha_calib,
    "events.json": validate_events,
    "universe.json": validate_universe,
}


def validate_file(path):
    base = os.path.basename(path)
    fn = _DISPATCH.get(base)
    if fn is None:
        return None, ["%s: no validator registered" % base]
    try:
        d = json.load(open(path))
    except Exception as ex:
        return False, ["%s: invalid JSON (%s)" % (base, ex)]
    return fn(d)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: validate_artifacts.py <file.json> [...]", file=sys.stderr)
        return 2
    rc = 0
    for p in argv:
        if not os.path.exists(p):
            print("  skip  %s (absent this run)" % os.path.basename(p))
            continue
        ok, errs = validate_file(p)
        if ok:
            print("  ok    %s" % os.path.basename(p))
        else:
            rc = 1
            print("  FAIL  %s" % os.path.basename(p))
            for er in errs[:25]:
                print("        " + er)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
