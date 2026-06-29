#!/usr/bin/env python3
"""deploy_staleness.py — flag when the DEPLOYED Market Map lags the REPO.

The 2026-06-28 incident hid for days partly because the live site silently lagged the repo by several
commits: the data-age healthcheck was green (the live file wasn't *old*), yet it predated newer commits.
This guard compares the asof of the committed repo `marketmap.json` (what SHOULD be live) against the asof
of the actually-deployed file (fetched live). If the deployed file is >max_lag_days behind the repo, the
deploy is lagging -> alert. Comparison core is pure + offline-tested; the live fetch is injected.

Usage:
  python deploy_staleness.py --repo marketmap.json --live-file /tmp/live_mm.json [--max-lag-days 1] [--strict]
  python deploy_staleness.py --repo marketmap.json --live-url https://www.mrktprice.com/marketmap.json [--strict]
Exit 0 = in sync (or could not determine); exit 1 = lagging AND --strict.
"""
import argparse, json, sys, datetime as dt


def _date(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def lag_days(repo_asof, live_asof):
    """Days the deployed file is BEHIND the repo (repo_date - live_date), or None if either is unparseable."""
    r, l = _date(repo_asof), _date(live_asof)
    if r is None or l is None:
        return None
    return (r - l).days


def evaluate(repo_asof, live_asof, max_lag_days=1):
    """Pure decision. stale=True iff the deploy is more than max_lag_days behind the repo."""
    lag = lag_days(repo_asof, live_asof)
    out = {"repoAsof": str(repo_asof), "liveAsof": str(live_asof), "lagDays": lag,
           "stale": False, "reason": ""}
    if lag is None:
        out["reason"] = "indeterminate (unparseable asof on one side)"
        return out
    if lag > max_lag_days:
        out["stale"] = True
        out["reason"] = ("deployed Market Map is %d day(s) behind the repo (repo asof %s, live asof %s) "
                         "— a push did not deploy" % (lag, repo_asof, live_asof))
    else:
        out["reason"] = "in sync (lag %d <= %d days)" % (lag, max_lag_days)
    return out


def _asof_of(path_or_obj):
    if isinstance(path_or_obj, dict):
        return path_or_obj.get("asof")
    with open(path_or_obj, "r", encoding="utf-8") as f:
        return json.load(f).get("asof")


def _fetch_live_asof(url, timeout=40):
    import urllib.request
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8")).get("asof")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="marketmap.json")
    ap.add_argument("--live-file", default=None)
    ap.add_argument("--live-url", default=None)
    ap.add_argument("--max-lag-days", type=int, default=1)
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    try:
        repo_asof = _asof_of(a.repo)
    except Exception as e:
        sys.stderr.write("::warning::deploy_staleness: cannot read repo %s (%s)\n" % (a.repo, str(e)[:80]))
        return 0
    try:
        if a.live_file:
            live_asof = _asof_of(a.live_file)
        elif a.live_url:
            live_asof = _fetch_live_asof(a.live_url)
        else:
            sys.stderr.write("::warning::deploy_staleness: no --live-file/--live-url given; skipping\n")
            return 0
    except Exception as e:
        sys.stderr.write("::warning::deploy_staleness: could not read live file (%s); skipping\n" % str(e)[:80])
        return 0

    res = evaluate(repo_asof, live_asof, max_lag_days=a.max_lag_days)
    print(json.dumps(res))
    if res["stale"]:
        sys.stderr.write("::error::%s\n" % res["reason"])
        return 1 if a.strict else 0
    sys.stderr.write("deploy_staleness: %s\n" % res["reason"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
