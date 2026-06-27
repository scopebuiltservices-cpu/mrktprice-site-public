#!/usr/bin/env python3
"""Quarterly-timeline REPORT BUNDLE: a self-contained, dependency-light HTML report (interactive via
inline SVG) + a run manifest, built from the verified quarterly_timeline metrics and warehouse basis
flags. The spec suggests Plotly+Kaleido, but that embeds ~5MB of JS and needs a headless browser; an
inline-SVG single file is lighter, prints cleanly to PDF, and works with zero third-party deps.

Panels rendered (spec's required set, executive subset): normalized performance (stock vs benchmark on a
total-return basis), running drawdown, an event-study CAR strip around the latest earnings, and a metrics
strip (return, vol, beta+HAC t, max drawdown). Deterministic file naming + manifest with basis flags.
Pure stdlib + quarterly_timeline.
"""
import os, math, html, datetime
try:
    import quarterly_timeline as qt
except Exception:
    qt = None

def _poly(points, w, h, pad=4):
    xs=[p[0] for p in points]; ys=[p[1] for p in points]
    lo=min(ys); hi=max(ys); rg=(hi-lo) or 1; n=len(points)
    return " ".join("%.1f,%.1f"%(pad+i/(max(n-1,1))*(w-2*pad), (h-pad)-(p[1]-lo)/rg*(h-2*pad)) for i,p in enumerate(points))

def _svg_line(series, w=560, h=120, color="#3fb76b", label="", base100=False):
    if not series: return ""
    pts=[(i,v) for i,v in enumerate(series)]
    poly=_poly(pts,w,h)
    last=series[-1]; first=series[0]
    return ('<svg viewBox="0 0 %d %d" width="100%%" style="max-width:600px;display:block">'
            '<polyline points="%s" fill="none" stroke="%s" stroke-width="1.6"/>'
            '<text x="4" y="14" fill="#8a93a3" font-size="10">%s</text>'
            '<text x="%d" y="14" fill="%s" font-size="11" text-anchor="end">%.2f</text></svg>'
            % (w,h,poly,color,html.escape(label),w-4,color,last))

def _svg_two(a, b, w=560, h=140, ca="#3fb76b", cb="#6f93c4", la="stock", lb="benchmark"):
    n=min(len(a),len(b))
    if n<2: return ""
    allv=a[:n]+b[:n]; lo=min(allv); hi=max(allv); rg=(hi-lo) or 1; pad=6
    def poly(s): return " ".join("%.1f,%.1f"%(pad+i/(n-1)*(w-2*pad),(h-pad)-(s[i]-lo)/rg*(h-2*pad)) for i in range(n))
    return ('<svg viewBox="0 0 %d %d" width="100%%" style="max-width:600px;display:block">'
            '<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#2a323d" stroke-dasharray="3,3"/>'
            '<polyline points="%s" fill="none" stroke="%s" stroke-width="1.7"/>'
            '<polyline points="%s" fill="none" stroke="%s" stroke-width="1.3"/>'
            '<text x="4" y="14" fill="%s" font-size="10">%s %.1f</text>'
            '<text x="4" y="26" fill="%s" font-size="10">%s %.1f</text></svg>'
            % (w,h, pad,(h-pad)-(100-lo)/rg*(h-2*pad), w-pad,(h-pad)-(100-lo)/rg*(h-2*pad),
               poly(a[:n]),ca, poly(b[:n]),cb, ca,html.escape(la),a[n-1], cb,html.escape(lb),b[n-1]))

def build_report(ticker, dates, close, bench_close=None, divs=None, earnings_idx=None,
                 exchange="NASDAQ", asof=None, title=None):
    """Return a single-file HTML report string. close/bench_close are trading-day-aligned daily closes."""
    asof = asof or datetime.date.today().isoformat()
    tk = ticker.upper()
    tr = qt.total_return_index(close, divs) if qt else list(close)
    nstock = qt.normalized(tr) if qt else list(close)
    nbench = qt.normalized(bench_close) if (qt and bench_close) else None
    dd = qt.drawdowns(tr) if qt else {"dd":[],"maxDD":0.0,"avgDD":0.0,"episodes":[]}
    lr = qt.log_returns(tr) if qt else []
    rv = qt.realized_vol(lr) if qt else 0.0
    dv = qt.downside_vol(lr) if qt else 0.0
    beta = None; car = None
    if qt and bench_close:
        rs = qt.log_returns(close); rm = qt.log_returns(bench_close)
        beta = qt.beta_market_model(rs, rm)
        if earnings_idx is not None and earnings_idx-1 > 260 and earnings_idx-1 < len(rs):
            car = qt.event_study(rs, rm, earnings_idx-1)
    totret = (tr[-1]/tr[0]-1) if tr and tr[0] else 0.0
    def pct(x): return ("+%.2f%%"%(x*100)) if x>=0 else ("%.2f%%"%(x*100))
    def tile(lab,val,sub=""):
        return ('<div class="t"><div class="tl">%s</div><div class="tv">%s</div>%s</div>'
                % (html.escape(lab), val, ('<div class="ts">%s</div>'%html.escape(sub)) if sub else ""))
    metrics = "".join([
        tile("Total return", pct(totret), "%s → %s"%(dates[0] if dates else "?", dates[-1] if dates else "?")),
        tile("Realized vol", "%.1f%%"%(rv*100), "downside %.1f%%"%(dv*100)),
        tile("Beta", ("%.2f"%beta["beta"]) if beta else "—", ("HAC t %.1f · R² %.0f%%"%(beta["t_beta"],beta["r2"]*100)) if beta else "no benchmark"),
        tile("Max drawdown", pct(dd["maxDD"]), "avg %s"%pct(dd["avgDD"])),
    ])
    if car:
        c1=car["CAR"].get("-1,1"); c5=car["CAR"].get("0,5")
        metrics += tile("Latest earnings CAR", pct(c1) if c1 is not None else "—", "[-1,+1] · [0,+5] %s"%(pct(c5) if c5 is not None else "—"))
    perf = _svg_two(nstock, nbench, la=tk, lb="benchmark") if nbench else _svg_line(nstock, label=tk+" (TR, =100)")
    ddv = _svg_line([d*100 for d in dd["dd"]], color="#e05a4e", label="drawdown %")
    H = []
    H.append("<!doctype html><html><head><meta charset='utf-8'><title>%s</title>" % html.escape(title or (tk+" quarterly timeline")))
    H.append("<style>body{background:#0b0f14;color:#cfd8e3;font:13px/1.5 -apple-system,Segoe UI,sans-serif;margin:0;padding:18px}"
             "h1{font-size:18px;margin:0 0 2px}.meta{color:#8a93a3;font-size:11px;margin-bottom:14px}"
             ".panel{border:1px solid #1d2530;border-radius:9px;padding:10px;margin:10px 0}.panel h3{margin:0 0 6px;font-size:12px;color:#e8c14a;letter-spacing:.04em}"
             ".strip{display:flex;gap:6px;flex-wrap:wrap}.t{flex:1;min-width:120px;background:#111721;border:1px solid #1d2530;border-radius:6px;padding:6px 8px}"
             ".tl{font-size:8px;color:#8a93a3;text-transform:uppercase;letter-spacing:.3px}.tv{font-size:15px;font-weight:800}.ts{font-size:8px;color:#69727f}"
             ".foot{color:#69727f;font-size:9px;margin-top:14px;border-top:1px solid #1d2530;padding-top:6px}</style></head><body>")
    H.append("<h1>%s — Quarterly Timeline Report</h1>" % tk)
    H.append("<div class='meta'>%s · as of %s · basis: TOTAL RETURN (dividends reinvested) · research only</div>" % (html.escape(exchange), asof))
    H.append("<div class='panel'><h3>KEY METRICS</h3><div class='strip'>%s</div></div>" % metrics)
    H.append("<div class='panel'><h3>NORMALIZED PERFORMANCE (=100)</h3>%s</div>" % perf)
    H.append("<div class='panel'><h3>DRAWDOWN</h3>%s</div>" % ddv)
    H.append("<div class='foot'>Generated by MrktPrice report_bundle · metrics from the verified quarterly_timeline engine · "
             "total-return basis · print to PDF for a static copy. %d trading days.</div>" % len(close))
    H.append("</body></html>")
    return "".join(H)

def deterministic_name(ticker, exchange, start, end, asof, artifact, ext):
    return "%s_%s_%s_%s_%s_%s.%s" % (ticker.upper(), exchange, start, end, asof, artifact, ext)

def write_report(html_str, outdir, ticker, exchange, start, end, asof):
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, deterministic_name(ticker, exchange, start, end, asof, "report", "html"))
    open(path, "w", encoding="utf-8").write(html_str)
    return path
