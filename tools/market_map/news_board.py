#!/usr/bin/env python3
"""news_board.py — POST-BUILD enrichment: attach per-name news headwind/tailwind to n["news"].

Reads the universe + data/news.json (from fmp_news), scores each name's headlines with the keyless
news_sentiment engine, and writes n["news"] = {net, label, tailwind, headwind, n, topPos, topNeg}. Also
emits market + per-sector aggregates into mm["newsTone"] so the daily report has the push-pull tone at
every level. Idempotent; pure beyond the file reads. Research only."""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import news_sentiment as NS


def enrich(mm, news, asof=None):
    asof = asof or mm.get("asof")
    names = mm.get("names") or []
    per = {}
    mcap = {}
    for n in names:
        t = n.get("t")
        if not t:
            continue
        heads = (news or {}).get(t) or (news or {}).get(t.upper()) or []
        s = NS.score_headlines(heads, asof=asof)
        n["news"] = s
        per[t] = s
        mcap[t] = float(n.get("mcap") or 0.0)
    # market + per-sector aggregates (cap-weighted)
    mm["newsTone"] = {"market": NS.aggregate(per, weights=mcap)}
    secs = {}
    for n in names:
        sec = n.get("sec")
        if not sec:
            continue
        secs.setdefault(sec, {})[n["t"]] = per.get(n["t"], {})
    mm["newsTone"]["sectors"] = {s: NS.aggregate(d, weights={k: mcap.get(k, 0.0) for k in d}) for s, d in secs.items()}
    return sum(1 for v in per.values() if v.get("n", 0) > 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="marketmap.json")
    ap.add_argument("--news", default="data/news.json")
    a = ap.parse_args()
    try:
        mm = json.load(open(a.map))
    except Exception as e:
        sys.stderr.write("news_board: cannot read %s (%s)\n" % (a.map, str(e)[:80])); return 1
    news = {}
    if os.path.exists(a.news):
        try:
            nd = json.load(open(a.news)); news = nd.get("news", nd) if isinstance(nd, dict) else {}
        except Exception:
            news = {}
    done = enrich(mm, news)
    tmp = a.map + ".tmp"
    json.dump(mm, open(tmp, "w"), separators=(",", ":"))
    os.replace(tmp, a.map)
    sys.stderr.write("news_board: scored news for %d names -> %s\n" % (done, a.map))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
