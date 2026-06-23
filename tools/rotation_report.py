#!/usr/bin/env python3
"""Sector-Rotation Monitor — turn the Opportunity Tracker's cross-sectional data
(marketmap.json) into a public Opportunity News report that says WHAT ROTATION IS ABOUT
TO HAPPEN: which sectors capital is rotating INTO vs OUT OF, and the style tilt.

Signal (per sector, aggregated over its names), then z-scored ACROSS sectors so the parts
are comparable, and combined with leading-indicator weights:
  accel   = median(ret_1m - ret_3m/3)   recent pace vs 3-mo pace  (LEADING)
  flow1m  = median(flow.net1m)          money inflow/outflow      (LEADING)
  breadth = share of names above EMA21                            (LEADING)
  mom     = median(z.mom)               cross-sectional momentum
  rs      = median(secRel)              sector-relative strength
  rotationScore = .30 z(accel) + .25 z(flow) + .20 z(breadth) + .15 z(mom) + .10 z(rs)
Top sectors = rotating IN; bottom = rotating OUT. Style tilt from leaders' z.size / z.val.
Research only; model-implied, not advice.  Pure stdlib; writes reports/sector-rotation-monitor.html."""
import json, os, html, statistics, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAP  = os.path.join(ROOT, "marketmap.json")
OUT  = os.path.join(ROOT, "reports", "sector-rotation-monitor.html")

def _med(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return statistics.median(xs) if xs else None

def _zmap(d):
    """z-score a {key:value} dict across its values (population). None-safe."""
    vals = [v for v in d.values() if isinstance(v, (int, float))]
    if len(vals) < 2: return {k: 0.0 for k in d}
    m = sum(vals)/len(vals)
    sd = (sum((v-m)**2 for v in vals)/len(vals))**0.5 or 1.0
    return {k: ((v-m)/sd if isinstance(v, (int, float)) else 0.0) for k, v in d.items()}

def sector_metrics(names):
    by = {}
    for n in names:
        s = n.get("sec")
        if not s: continue
        by.setdefault(s, []).append(n)
    out = {}
    for s, ns in by.items():
        r1 = [ (n.get("ret") or {}).get("1m") for n in ns ]
        r3 = [ (n.get("ret") or {}).get("3m") for n in ns ]
        accel = _med([ (a - b/3.0) for a, b in zip(r1, r3) if isinstance(a,(int,float)) and isinstance(b,(int,float)) ])
        flow1 = _med([ (n.get("flow") or {}).get("net1m") for n in ns ])
        above = [1 for n in ns if isinstance(n.get("ema21sig"),(int,float)) and n["ema21sig"]>0]
        breadth = (len(above)/len(ns)) if ns else None
        mom = _med([ (n.get("z") or {}).get("mom") for n in ns ])
        rs  = _med([ n.get("secRel") for n in ns ])
        out[s] = {"n":len(ns),"accel":accel,"flow1m":flow1,"breadth":breadth,"mom":mom,"rs":rs,
                  "r1m":_med(r1),"r3m":_med(r3)}
    return out

def rank_rotation(sm):
    keys = list(sm.keys())
    def col(f): return {k: sm[k][f] for k in keys}
    za, zf, zb, zm, zr = (_zmap(col("accel")), _zmap(col("flow1m")), _zmap(col("breadth")),
                          _zmap(col("mom")), _zmap(col("rs")))
    for k in keys:
        sm[k]["score"] = round(0.30*za[k] + 0.25*zf[k] + 0.20*zb[k] + 0.15*zm[k] + 0.10*zr[k], 3)
    return sorted(keys, key=lambda k: sm[k]["score"], reverse=True)

def style_tilt(names, ranked, sm):
    top = set(ranked[: max(1, len(ranked)//3)])
    lead = [n for n in names if n.get("sec") in top]
    if not lead: return None
    size = _med([ (n.get("z") or {}).get("size") for n in lead ])   # + = large-cap
    val  = _med([ (n.get("z") or {}).get("val")  for n in lead ])   # + = value/cheap
    return {"size": size, "val": val}

def top_names(names, ranked, sm, k=6):
    top = set(ranked[: max(1, len(ranked)//3)])
    pool = [n for n in names if n.get("sec") in top and isinstance(n.get("oppPct"),(int,float))]
    pool.sort(key=lambda n: n["oppPct"], reverse=True)
    return pool[:k]

def _pct(x): return ("%+.1f%%" % x) if isinstance(x,(int,float)) else "—"
def _num(x): return ("%+.2f" % x) if isinstance(x,(int,float)) else "—"

def render(d):
    names = d.get("names") or []
    asof = d.get("asof") or datetime.date.today().isoformat()
    synthetic = "SAMPLE" in str(d.get("source","")) or "synthetic" in str(d.get("source","")).lower()
    sm = sector_metrics(names)
    if len(sm) < 3:
        return None
    ranked = rank_rotation(sm)
    into, outof = ranked[:3], ranked[-3:][::-1]
    tilt = style_tilt(names, ranked, sm)
    leaders = top_names(names, ranked, sm)

    tilt_txt = ""
    if tilt:
        sz = ("large-cap" if (tilt["size"] or 0) > 0.15 else "small-cap" if (tilt["size"] or 0) < -0.15 else "size-neutral")
        st = ("value" if (tilt["val"] or 0) > 0.15 else "growth" if (tilt["val"] or 0) < -0.15 else "style-neutral")
        tilt_txt = "Leadership is tilting toward <strong>%s %s</strong>." % (sz, st)

    head = ("Capital is rotating <strong>into %s</strong> and <strong>out of %s</strong>."
            % (", ".join(into[:2]), ", ".join(outof[:2])))
    summary = ("Rotation signal: into %s; out of %s. %s" %
               (", ".join(into[:2]), ", ".join(outof[:2]),
                ("Leadership %s %s." % (
                    "large-cap" if (tilt and (tilt["size"] or 0)>0.15) else "small-cap" if (tilt and (tilt["size"] or 0)<-0.15) else "broad",
                    "value" if (tilt and (tilt["val"] or 0)>0.15) else "growth" if (tilt and (tilt["val"] or 0)<-0.15) else "mixed") if tilt else "")))

    rows = ""
    for i, s in enumerate(ranked):
        m = sm[s]
        if s in into[:2]: tag = '<span class="tag" style="color:var(--up);border-color:var(--up)">rotating in</span>'
        elif s in outof[:2]: tag = '<span class="tag" style="color:var(--down);border-color:var(--down)">rotating out</span>'
        else: tag = '<span class="tag" style="color:var(--muted)">neutral</span>'
        rows += ("<tr><td><strong>%s</strong> %s</td><td>%+.2f</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                 % (html.escape(s), tag, m["score"], _pct(m["accel"]),
                    (_num(m["flow1m"]) if isinstance(m["flow1m"],(int,float)) else "—"),
                    (("%.0f%%" % (m["breadth"]*100)) if isinstance(m["breadth"],(int,float)) else "—"),
                    _pct(m["r1m"])))

    lead_rows = ""
    for n in leaders:
        lead_rows += ("<tr><td><strong>%s</strong></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                      % (html.escape(n.get("t","")), html.escape(n.get("sec","")),
                         (("%d" % n["oppPct"]) if isinstance(n.get("oppPct"),(int,float)) else "—"),
                         _pct((n.get("ret") or {}).get("1m")),
                         (_num((n.get("z") or {}).get("mom")))))

    meta = {"title":"Sector Rotation Monitor","date":asof[:10],
            "summary":summary[:240],"tags":["rotation","sectors","macro","opportunity-tracker"],
            "author":"MrktPrice Research Engine"}
    fdate = datetime.date.fromisoformat(asof[:10]).strftime("%B %d, %Y").replace(" 0"," ")
    syn = ('<blockquote>Illustrative run on sample data — live readings populate once the nightly '
           'cross-sectional snapshot is published.</blockquote>' if synthetic else '')

    return ("""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<script type="application/json" id="report-meta">
%s
</script>
<title>Sector Rotation Monitor · Opportunity News</title>
<style>
 :root{--bg:#0a0d12;--panel:#111721;--line:#27313f;--ink:#eef3f8;--muted:#97a4b3;--faint:#646e7c;--accent:#16c79a;--brand:#16c79a;--gold:#f5c451;--up:#2ecc8f;--down:#ef5f4e;}
 *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
 .wrap{max-width:760px;margin:0 auto;padding:28px 22px 60px}
 .top{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:26px}
 .brand{font-weight:800}.brand b{color:var(--brand)}.brand span{color:var(--muted);font-weight:600}
 a.back{color:var(--muted);text-decoration:none;font-size:13px;border:1px solid var(--line);padding:5px 10px;border-radius:7px}a.back:hover{color:var(--ink);border-color:var(--accent)}
 h1{font-size:30px;line-height:1.2;margin:.2em 0 .15em}.meta{color:var(--faint);font-size:13px;margin-bottom:8px}
 .tags{display:flex;gap:6px;flex-wrap:wrap;margin:14px 0 24px}.tag{font-size:11px;color:var(--accent);border:1px solid var(--line);border-radius:20px;padding:3px 10px;text-transform:uppercase;letter-spacing:.5px}
 .lead{font-size:18px;color:var(--ink);margin:0 0 18px}
 .body h2{font-size:20px;margin:30px 0 10px}.body h3{font-size:15px;color:var(--muted);margin:20px 0 6px}.body p{margin:0 0 14px}
 .body blockquote{border-left:3px solid var(--gold);margin:16px 0;padding:4px 14px;color:var(--muted)}
 table{border-collapse:collapse;width:100%%;margin:14px 0;font-size:13.5px}th,td{border:1px solid var(--line);padding:6px 9px;text-align:left}th{background:var(--panel);color:var(--muted)}
 .disclaimer{margin-top:38px;padding:16px 18px;background:var(--panel);border:1px solid var(--line);border-radius:10px;font-size:12.5px;color:var(--muted);line-height:1.6}
 footer{margin-top:24px;color:var(--faint);font-size:12px;border-top:1px solid var(--line);padding-top:14px}
</style></head><body><div class="wrap">
 <div class="top"><div class="brand"><b>Mrkt</b><span>Price</span> · Opportunity&nbsp;News™</div><a class="back" href="./index.html">← All reports</a></div>
 <h1>Sector Rotation Monitor</h1>
 <div class="meta">%s · auto-generated from the Opportunity Tracker cross-section · updates each run</div>
 <div class="tags"><span class="tag">rotation</span><span class="tag">sectors</span><span class="tag">macro</span></div>
 <p class="lead">%s</p>
 %s
 <article class="body">
   <h2>Where capital is moving</h2>
   <p>Sectors ranked by a composite <em>rotation score</em> — recent return acceleration, money flow, breadth above trend, momentum, and relative strength, each measured across the whole universe so they are comparable. Positive = capital rotating in; negative = rotating out.</p>
   <table><tr><th>Sector</th><th>Rotation</th><th>Score</th><th>Accel (1m vs 3m pace)</th><th>Flow (1m)</th><th>Breadth &gt;EMA21</th><th>1m</th></tr>%s</table>
   <h2>Style tilt</h2>
   <p>%s</p>
   <h2>Names riding the leading sectors</h2>
   <p>Highest opportunity-score names inside the sectors rotating in (research screen, not a recommendation):</p>
   <table><tr><th>Ticker</th><th>Sector</th><th>Opp score</th><th>1m return</th><th>Momentum z</th></tr>%s</table>
   <h2>What it may mean</h2>
   <p>When acceleration, money flow and breadth line up in the same sectors, leadership tends to persist near-term — the signal flags <em>where</em> the rotation is heading, not a guaranteed move. Readings are model-implied and cross-sectional (relative to the universe), refreshed each run.</p>
 </article>
 <div class="disclaimer"><strong>Not investment advice.</strong> Opportunity News is a general, impersonal market-analysis publication for research and educational purposes only. Signals are model-implied, relative, and may be delayed, incomplete, or inaccurate. Do your own research.</div>
 <footer>© 2026 MrktPrice™ / Marc Jones. Generated by the MrktPrice Research Engine from the Opportunity Tracker cross-section.</footer>
</div></body></html>""" % (json.dumps(meta, indent=2), fdate, head, syn, rows, (tilt_txt or "Style leadership is mixed."), lead_rows))

def main():
    if not os.path.exists(MAP):
        print("no marketmap.json"); return 1
    d = json.load(open(MAP))
    out = render(d)
    if not out:
        print("too few sectors to build a rotation report"); return 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(out)
    print("wrote", os.path.relpath(OUT, ROOT), "(%d bytes)" % len(out))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
