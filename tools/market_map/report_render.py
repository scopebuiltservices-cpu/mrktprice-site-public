#!/usr/bin/env python3
"""report_render.py — turn report_engine models into self-contained, PRINT-STYLED HTML (the reviewable
file AND the PDF source via the browser/weasyprint print path). Every tile is rendered BOTH visually
(inline SVG gauges / sparklines / colored stat tiles) AND graphically (numeric tables), in the MrktPrice
dark theme, with @media print page breaks so a multi-page PDF falls out of 'Save as PDF'. Pure stdlib."""
import html as _h

CSS = """
:root{--bg:#0d121b;--panel:#141b27;--ink:#e8edf4;--mut:#8a93a0;--line:#222c3a;--up:#16c79a;--dn:#ef6a6a;--ac:#5b8cff}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:22px}
h1{font-size:24px;margin:0 0 2px} h2{font-size:17px;border-bottom:1px solid var(--line);padding-bottom:6px;margin:22px 0 12px;color:#cfe0ff}
h3{font-size:14px;margin:14px 0 6px;color:#cfd6e0} .sub{color:var(--mut);margin:0 0 14px}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin:8px 0}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.tile .k{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
.tile .v{font-size:20px;font-weight:600;margin-top:3px} .up{color:var(--up)} .dn{color:var(--dn)} .mut{color:var(--mut)}
table{width:100%;border-collapse:collapse;margin:8px 0;font-size:12px}
th,td{text-align:right;padding:5px 8px;border-bottom:1px solid var(--line)} th{color:var(--mut);font-weight:500}
td:first-child,th:first-child{text-align:left}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;font-weight:600}
.pill.t{background:rgba(22,199,154,.15);color:var(--up)} .pill.h{background:rgba(239,106,106,.15);color:var(--dn)} .pill.n{background:rgba(138,147,160,.15);color:var(--mut)}
.foot{color:var(--mut);font-size:11px;margin-top:26px;border-top:1px solid var(--line);padding-top:10px}
@media print{body{background:#fff;color:#111}.tile{background:#f6f8fb;border-color:#dde3ec}.page{page-break-after:always}h2{color:#1f4e79}}
"""


def _f(x, d=1, suf="", plus=False):
    try:
        v = float(x)
        s = ("%+." + str(d) + "f") % v if plus else ("%." + str(d) + "f") % v
        return s + suf
    except (TypeError, ValueError):
        return "—"


def _cls(x):
    try:
        return "up" if float(x) > 0 else ("dn" if float(x) < 0 else "mut")
    except (TypeError, ValueError):
        return "mut"


def _pill(label):
    c = "t" if label == "tailwind" else ("h" if label == "headwind" else "n")
    return '<span class="pill %s">%s</span>' % (c, _h.escape(str(label or "—")))


def tile(k, v, cls=""):
    return '<div class="tile"><div class="k">%s</div><div class="v %s">%s</div></div>' % (_h.escape(k), cls, v)


def sentiment_bar(net, w=150, h=12):
    """A -1..+1 gauge with a marker at net (visual)."""
    try:
        n = max(-1.0, min(1.0, float(net)))
    except (TypeError, ValueError):
        n = 0.0
    x = (n + 1) / 2 * w
    col = "#16c79a" if n > 0.05 else ("#ef6a6a" if n < -0.05 else "#8a93a0")
    return ('<svg width="%d" height="%d" viewBox="0 0 %d %d">'
            '<rect x="0" y="%d" width="%d" height="3" rx="1.5" fill="#222c3a"/>'
            '<line x1="%d" y1="0" x2="%d" y2="%d" stroke="#3a4456"/>'
            '<circle cx="%.1f" cy="%d" r="5" fill="%s"/></svg>'
            % (w, h, w, h, h // 2, w, w // 2, w // 2, h, x, h // 2, col))


def sparkline(vals, w=120, hgt=26):
    xs = [v for v in vals if isinstance(v, (int, float))]
    if len(xs) < 2:
        return ""
    lo, hi = min(xs), max(xs)
    rng = (hi - lo) or 1.0
    pts = " ".join("%.1f,%.1f" % (i * w / (len(xs) - 1), hgt - (v - lo) / rng * (hgt - 4) - 2) for i, v in enumerate(xs))
    col = "#16c79a" if xs[-1] >= xs[0] else "#ef6a6a"
    return '<svg width="%d" height="%d"><polyline points="%s" fill="none" stroke="%s" stroke-width="1.5"/></svg>' % (w, hgt, pts, col)


def _shell(title, body):
    return ("<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>%s</title><style>%s</style></head><body><div class='wrap'>%s"
            "<div class='foot'>MrktPrice daily report · research only, not investment advice · sentiment is keyless-lexicon scored</div>"
            "</div></body></html>" % (_h.escape(title), CSS, body))


def render_macro(m, shell=True):
    b = ["<h1>Market Report</h1><p class='sub'>as of %s · %d equities · breadth %s%% (%d up / %d down)</p>"
         % (_h.escape(str(m.get("asof"))), m.get("universe", 0), _f(m.get("breadthPct")), m.get("advancers", 0), m.get("decliners", 0))]
    nt = m.get("newsTone", {})
    b.append("<div class='tiles'>")
    b.append(tile("Market news tone", _pill(nt.get("label")) + " " + sentiment_bar(nt.get("net"))))
    b.append(tile("Avg projected move", _f(m.get("projAvgPct"), 2, "%", True), _cls(m.get("projAvgPct"))))
    for ix in m.get("indices", []):
        b.append(tile(ix["index"], _f(ix["avgRet3m"], 1, "%", True) + " <span class='mut' style='font-size:12px'>· breadth " + _f(ix["breadthPct"]) + "%</span>", _cls(ix["avgRet3m"])))
    b.append("</div>")
    b.append("<h2>Sector rotation (push / pull)</h2><table><tr><th>Sector</th><th>Tilt</th><th>Breadth</th><th>Sec-rel</th><th>News</th><th>Read</th></tr>")
    for r in m.get("rotation", []):
        b.append("<tr><td>%s</td><td class='%s'>%s</td><td>%s%%</td><td class='%s'>%s</td><td>%s</td><td>%s</td></tr>"
                 % (_h.escape(r["sector"]), _cls(r["tilt"]), _f(r["tilt"], 3, "", True), _f(r["breadthPct"]),
                    _cls(r["secRel"]), _f(r["secRel"], 2, "", True), sentiment_bar(r["newsNet"], 90, 12), _h.escape(r["label"])))
    b.append("</table>")
    b.append("<h2>Dominant macro drivers</h2><div class='tiles'>")
    for d in m.get("macroDrivers", []):
        b.append(tile(d["driver"], _f(d["weight"], 2)))
    b.append("</div>")
    b.append("<div style='display:grid;grid-template-columns:1fr 1fr;gap:18px'>")
    for ttl, key, cl in (("Top tailwinds", "topTailwinds", "t"), ("Top headwinds", "topHeadwinds", "h")):
        b.append("<div><h3>%s</h3><table>" % ttl)
        for x in m.get(key, [])[:6]:
            b.append("<tr><td><b>%s</b> <span class='mut'>%s</span></td><td>%s</td></tr><tr><td colspan='2' class='mut' style='font-size:11px;border:0'>%s</td></tr>"
                     % (_h.escape(str(x["t"])), _h.escape(str(x.get("sec") or "")), _f(x["net"], 2, "", True), _h.escape(str(x.get("why") or ""))))
        b.append("</table></div>")
    b.append("</div>")
    tc = m.get("treasuryCurve", {})
    if tc.get("points"):
        b.append("<h2>Treasury curve &amp; rate complex</h2><div class='tiles'>")
        for p in tc["points"]:
            b.append(tile(p["tenor"], _f(p["yield"], 2, "%")))
        b.append(tile("2s10s slope", _f(tc.get("slope2s10s"), 2, "%", True) + (" <span class='dn'>inverted</span>" if tc.get("inverted") else ""), _cls(tc.get("slope2s10s"))))
        b.append("</div>")
    mc = m.get("macroComplex", [])
    if mc:
        b.append("<h2>Market-wide commodity &amp; rate exposure</h2><table><tr><th>Driver</th><th>Avg sens (%/\u03c3)</th><th>Net</th><th>Now \u03c3</th><th>Names</th></tr>")
        for r in mc:
            b.append("<tr><td>%s</td><td>%s</td><td class='%s'>%s</td><td class='%s'>%s</td><td>%s</td></tr>" % (_h.escape(str(r["driver"])), _f(r["avgAbsSens"], 2), _cls(r["avgSens"]), _f(r["avgSens"], 2, "", True), _cls(r.get("nowSigma")), (_f(r.get("nowSigma"), 2, "\u03c3", True) if r.get("nowSigma") is not None else "\u2014"), r["names"]))
        b.append("</table>")
    rm = m.get("regimeMix", {}); ea = m.get("earningsAhead", {})
    b.append("<div class='tiles'>")
    b.append(tile("Vol regime", "%d calm / %d stress (%s%% stress)" % (rm.get("calm", 0), rm.get("stress", 0), _f(rm.get("stressPct"), 0))))
    b.append(tile("Earnings next 14d", str(ea.get("next14d", 0)) + " names"))
    b.append("</div>")
    body = "".join(b)
    return _shell("Market Report — %s" % m.get("asof"), body) if shell else body


def render_sector(s, shell=True):
    if s.get("empty"):
        return _shell("Sector", "<h1>%s</h1><p class='sub'>no constituents</p>" % _h.escape(s.get("sector", "")))
    b = ["<h1>%s — Sector Report</h1><p class='sub'>as of %s · %d names · avg 3m %s%% · breadth %s%%</p>"
         % (_h.escape(s["sector"]), _h.escape(str(s.get("asof"))), s["n"], _f(s.get("avgRet3m"), 1, "", True), _f(s.get("breadthPct")))]
    b.append("<div class='tiles'>")
    b.append(tile("Sector news tone", _pill(s.get("newsTone", {}).get("label")) + " " + sentiment_bar(s.get("newsTone", {}).get("net"))))
    b.append(tile("Avg tilt", _f(s.get("avgTilt"), 3, "", True), _cls(s.get("avgTilt"))))
    pp = s.get("pushPull", {})
    if pp.get("movesWith"):
        b.append(tile("Moves WITH", ", ".join("%s %s" % (p["sector"][:10], _f(p["corr"], 2)) for p in pp["movesWith"])))
    if pp.get("movesAgainst"):
        b.append(tile("Moves AGAINST", ", ".join("%s %s" % (p["sector"][:10], _f(p["corr"], 2)) for p in pp["movesAgainst"])))
    b.append("</div>")
    b.append("<h2>Factor profile (cross-sectional z)</h2><div class='tiles'>")
    for k, fp in s.get("factorProfile", {}).items():
        b.append(tile(fp["label"], _f(fp["z"], 2, "", True), _cls(fp["z"])))
    b.append("</div>")
    for ttl, key in (("Leaders", "leaders"), ("Laggards", "laggards")):
        b.append("<h2>%s</h2>%s" % (ttl, _name_table(s.get(key, []))))
    body = "".join(b)
    return _shell("%s — Sector Report" % s["sector"], body) if shell else body


def _name_table(rows):
    h = ["<table><tr><th>Ticker</th><th>3m</th><th>Tilt</th><th>Sec-rel</th><th>Proj</th><th>P-up</th><th>Tgt</th><th>News</th></tr>"]
    for r in rows:
        h.append("<tr><td><b>%s</b> <span class='mut'>%s</span></td><td class='%s'>%s</td><td class='%s'>%s</td><td>%s</td><td class='%s'>%s</td><td>%s%%</td><td>%s</td><td>%s</td></tr>"
                 % (_h.escape(str(r.get("t"))), _h.escape(str(r.get("name") or "")[:18]),
                    _cls(r.get("ret3m")), _f(r.get("ret3m"), 1, "%", True), _cls(r.get("tilt")), _f(r.get("tilt"), 3, "", True),
                    _f(r.get("secRel"), 2, "", True), _cls(r.get("projPct")), _f(r.get("projPct"), 1, "%", True),
                    _f(100 * (r.get("probUp") or 0), 0), _f(r.get("targetUpPct"), 0, "", True), _pill(r.get("newsLabel"))))
    h.append("</table>")
    return "".join(h)


def _sig_star(r):
    return "<span class='up'>\u2605</span>" if r.get("sig") else ("<span class='mut'>\u00b7</span>" if r.get("weak") else "")


def sens_table(s):
    rows = []
    if s.get("rate"):
        rows.append(("Interest rate", s["rate"]))
    for r in s.get("commodities", []):
        rows.append(("Commodity", r))
    for r in s.get("market", []):
        rows.append(("Market/sector", r))
    h = ["<table><tr><th>Driver</th><th>Type</th><th>Sens (%/\u03c3)</th><th>Now move</th><th>Now \u03c3</th><th>Implied %</th><th>Corr</th><th>Sig</th><th>Read</th></tr>"]
    for kind, r in rows:
        h.append("<tr><td><b>%s</b></td><td class='mut'>%s</td><td class='%s'>%s</td><td>%s</td><td class='%s'>%s</td><td class='%s'><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td></tr>"
                 % (_h.escape(str(r.get("factor"))), _h.escape(kind), _cls(r.get("sensPct")), _f(r.get("sensPct"), 2, "", True),
                    (_f(r.get("driverMovePct"), 2, "%", True) if r.get("driverMovePct") is not None else "\u2014"),
                    _cls(r.get("driverSigma")), (_f(r.get("driverSigma"), 2, "\u03c3", True) if r.get("driverSigma") is not None else "\u2014"),
                    _cls(r.get("impliedPct")), (_f(r.get("impliedPct"), 2, "%", True) if r.get("impliedPct") is not None else "\u2014"),
                    _f(r.get("corr"), 2, "", True), _sig_star(r), _pill(r.get("wind")) if r.get("wind") else ""))
    h.append("</table>")
    return "".join(h)


def cal_table(rows):
    h = ["<table><tr><th>Date</th><th>Event</th><th>Detail</th></tr>"]
    for r in rows:
        h.append("<tr><td>%s</td><td><b>%s</b></td><td class='mut'>%s</td></tr>" % (_h.escape(str(r.get("date"))), _h.escape(str(r.get("event"))), _h.escape(str(r.get("detail") or ""))))
    h.append("</table>")
    return "".join(h)


def render_company(c, shell=True):
    if not c.get("found"):
        return _shell("Company", "<h1>%s</h1><p class='sub'>not in universe</p>" % _h.escape(c.get("ticker", "")))
    p = c["price"]; r = c["roleInSector"]; v = c["valuation"]; pj = c["projection"]; nw = c["news"]
    b = ["<h1>%s — %s</h1><p class='sub'>%s · %s · as of %s · verdict: <b>%s</b></p>"
         % (_h.escape(str(c["ticker"])), _h.escape(str(c.get("name") or "")), _h.escape(str(c.get("sector"))),
            " ".join(c.get("indices", [])), _h.escape(str(c.get("asof"))), _h.escape(c["verdict"]["tag"]))]
    b.append("<div class='tiles'>")
    b.append(tile("Return 1m/3m/12m", "%s / %s / %s" % (_f(p["ret1m"], 1, "%", True), _f(p["ret3m"], 1, "%", True), _f(p["ret12m"], 1, "%", True))
                  + "<br>" + sparkline([0, p.get("ret1m"), p.get("ret3m"), p.get("ret6m"), p.get("ret12m")])))
    b.append(tile("Projection %sd" % pj.get("h", 21), _f(pj["projPct"], 1, "%", True) + " <span class='mut'>±" + _f(pj["sigmaHPct"], 1) + "%</span>", _cls(pj["projPct"])))
    b.append(tile("P(up)", _f(100 * (pj.get("probUp") or 0), 0, "%")))
    b.append(tile("Role in %s" % r.get("sector"), "#%s of %s" % (r.get("rankInSector") or "—", r.get("ofN") or "—") + " · sec-rel " + _f(r.get("secRel"), 2, "", True)))
    b.append(tile("Analyst target", _f(v.get("targetUpsidePct"), 1, "%", True) + " <span class='mut'>" + _h.escape(str(v.get("rating") or "")) + "</span>", _cls(v.get("targetUpsidePct"))))
    b.append(tile("News", _pill(nw.get("label")) + " " + sentiment_bar(nw.get("net"))))
    b.append("</div>")
    b.append("<h2>Headwinds &amp; tailwinds</h2><table>")
    for k, vv in c.get("winds", []):
        b.append("<tr><td>%s</td><td>%s</td></tr>" % (_h.escape(k), _h.escape(str(vv))))
    for hdl in (nw.get("tailwinds") or [])[:3]:
        b.append("<tr><td class='up'>+ headline</td><td class='mut' style='font-size:11px'>%s</td></tr>" % _h.escape(str(hdl)))
    for hdl in (nw.get("headwinds") or [])[:3]:
        b.append("<tr><td class='dn'>− headline</td><td class='mut' style='font-size:11px'>%s</td></tr>" % _h.escape(str(hdl)))
    b.append("</table>")
    eb = c.get("ebitda", {})
    if eb.get("have"):
        b.append("<h2>EBITDA</h2><div class='tiles'>")
        b.append(tile("Adj. EBITDA last Q", _f(eb.get("lastQAdj"), 0)))
        b.append(tile("Expected EBITDA next Q", _f(eb.get("nextQExp"), 0)))
        if eb.get("growthPct") is not None:
            b.append(tile("Expected QoQ", _f(eb.get("growthPct"), 1, "%", True), _cls(eb.get("growthPct"))))
        b.append("</div>")
    cal = c.get("calendar", [])
    if cal:
        b.append("<h2>Important calendar dates</h2>" + cal_table(cal))
    s = c.get("sensitivities", {})
    if s.get("rate") or s.get("commodities") or s.get("market"):
        live = ("<div class='tiles'>" + tile("Live macro contribution (this period)", _f(s.get("liveContribPct"), 2, "%", True), _cls(s.get("liveContribPct"))) + "</div>") if s.get("hasLive") else ""
        b.append("<h2>Macro &amp; commodity sensitivities</h2>"
                 "<p class='sub'>macro R\u00b2 %s%% · dominant driver %s · sens = %% per +1\u03c3 of the driver · implied %% = sens \u00d7 driver\u2019s current \u03c3-move</p>"
                 % (_f(s.get("macroR2"), 0), _h.escape(str(s.get("dominantDriver") or "—"))))
        b.append(live)
        b.append(sens_table(s))
    b.append("<h2>Macro tilt (partial betas)</h2><div class='tiles'>")
    for d in c.get("macroTilt", []):
        b.append(tile(d["driver"], _f(d["beta"], 2, "", True), _cls(d["beta"])))
    b.append("</div>")
    body = "".join(b)
    return _shell("%s — Company Report" % c["ticker"], body) if shell else body
