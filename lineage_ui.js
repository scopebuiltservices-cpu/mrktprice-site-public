/* lineage_ui.js — Phase 5 UI (improved). Highest-probability lineage ribbon (MAP + alternate
   branches), node scatter, sigma-volume heatmap, and node card -> #lineagePanel.
   Reads cards/<T>.json (card.lineage) with window.MMAP fallback. Event-driven (no polling);
   draws the top-3 branches as ribbons (solid MAP + dashed alternates) using per-regime drift/vol;
   marks nodes whose horizon contains an earnings date as event-linked. Degrades gracefully. */
(function () {
  "use strict";
  var PRIMARY = { intraday: 1, "1d": 1, "5d": 1 };
  var DAYS = { intraday: 0.25, "1d": 1, "5d": 5, "10d": 10, "20d": 20, "63d": 63 };
  var ORDER = ["intraday", "1d", "5d", "10d", "20d", "63d"];
  var Z90 = 1.2815515594, Z75 = 0.6744897502, Z95 = 1.6448536270;
  var ACC = "#e0c14a", BLUE = "#39b6ff", UP = "#2ecc8f", DN = "#ef5f4e", VIO = "#b98ad0",
      INK = "var(--ink,#eef3f8)", FAINT = "var(--faint,#646e7c)", MUTED = "var(--muted,#8a93a0)",
      LINE = "var(--line,#2a2f3a)", PANEL = "var(--panel2,#141a24)";
  var BRANCH_COL = [BLUE, VIO, ACC];
  var _last = null, _focus = null, _state = null;

  function el(id) { return document.getElementById(id); }
  function curSym() { var e = el("symsel") || el("sym"); return e ? String(e.value || "").toUpperCase().trim() : ""; }
  function nameOf(sym) { var m = window.MMAP && window.MMAP.names; if (!m) return null; for (var i = 0; i < m.length; i++) if (String(m[i].t || "").toUpperCase() === sym) return m[i]; return null; }
  function pct(x, d) { return (x >= 0 ? "+" : "") + (x * 100).toFixed(d == null ? 2 : d) + "%"; }
  function fmtVol(v) { return v == null ? "—" : v >= 1e9 ? (v / 1e9).toFixed(1) + "B" : v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? (v / 1e3).toFixed(0) + "K" : (+v).toFixed(0); }
  function gol(c){return c;}
  function esc(s) { return String(s).replace(/[&<>]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]; }); }

  function binFor(retZ, sigvolH) {
    if (!sigvolH) return null;
    var keys = Object.keys(sigvolH);
    for (var i = 0; i < keys.length; i++) { var p = keys[i].split(".."); if (retZ >= +p[0] && retZ < +p[1]) return sigvolH[keys[i]]; }
    return retZ < 0 ? sigvolH[keys[0]] : sigvolH[keys[keys.length - 1]];
  }
  function earnInWindow(name, days) {
    try {
      var nx = name && name.earn && name.earn.next; if (!nx || !nx.d) return null;
      var t = new Date(nx.d + "T00:00:00Z"), dCal = (t - new Date()) / 86400000, span = days * 1.45;
      return (dCal >= -1 && dCal <= span) ? nx.d : null;
    } catch (e) { return null; }
  }

  function buildNodes(lin, name) {
    var hz = lin.horizons || {}, nodes = [];
    var labels = ORDER.filter(function (l) { return hz[l]; });
    var mapP = (lin.branches && lin.branches[0]) ? lin.branches[0].p : null;
    var dsig = (lin.volBase && lin.volBase.dailySigma) || null;
    labels.forEach(function (h) {
      var H = hz[h], drift = H.mapDrift, vol = H.mapVol, evol = null;
      if (lin.sigvol && lin.sigvol[h] && dsig) {
        var days = DAYS[h] || 1, b = binFor(drift / ((dsig * Math.sqrt(days)) || 1e-9), lin.sigvol[h]); evol = b ? b.meanCumVol : null;
      }
      var v = lin.valid && lin.valid[h], t = lin.touch && lin.touch[h];
      nodes.push({
        h: h, primary: !!PRIMARY[h], drift: drift, vol: vol, rd: H.rd || null, rv: H.rv || null,
        q10: drift - Z90 * vol, q25: drift - Z75 * vol, q50: drift, q75: drift + Z75 * vol, q90: drift + Z90 * vol, q95: drift + Z95 * vol,
        pNode: mapP, evol: evol, branching: H.branching, diffusive: H.diffusive,
        calib: v ? v.coverage : null, valid: v || null, pUp: t ? t.pUp : null, pDn: t ? t.pDn : null,
        S: t ? t.S : null, eventLinked: earnInWindow(name, DAYS[h] || 1), pq: (lin.pq && lin.pq.horizons && lin.pq.horizons[h]) || null
      });
    });
    return nodes;
  }

  function ribbonSVG(nodes, branches) {
    if (!nodes.length) return "";
    var W = 680, Ht = 158, padL = 44, padR = 96, padT = 12, padB = 26;
    var lo = -0.01, hi = 0.01;
    nodes.forEach(function (n) { lo = Math.min(lo, n.q10); hi = Math.max(hi, n.q90); });
    (branches || []).forEach(function (b) { nodes.forEach(function (n) { if (n.rd && n.rv) { lo = Math.min(lo, n.rd[b.regime] - Z90 * n.rv[b.regime]); hi = Math.max(hi, n.rd[b.regime] + Z90 * n.rv[b.regime]); } }); });
    var pad = (hi - lo) * 0.08 || 0.01; lo -= pad; hi += pad;
    var X = function (i) { return padL + (nodes.length === 1 ? 0.5 : i / (nodes.length - 1)) * (W - padL - padR); };
    var Y = function (r) { return padT + (1 - (r - lo) / (hi - lo)) * (Ht - padT - padB); };
    var s = '<svg viewBox="0 0 ' + W + ' ' + Ht + '" width="100%" style="display:block">';
    s += '<line x1="' + padL + '" y1="' + Y(0) + '" x2="' + (W - padR) + '" y2="' + Y(0) + '" stroke="' + LINE + '" stroke-dasharray="3 3"/>';
    s += '<text x="' + (W - padR + 4) + '" y="' + (Y(0) + 3) + '" fill="' + FAINT + '" font-size="9">now 0%</text>';
    var op = nodes[0].pNode != null ? Math.max(0.12, Math.min(0.4, nodes[0].pNode * 0.45)) : 0.22;
    var top = "", bot = "";
    nodes.forEach(function (n, i) { top += (i ? " L" : "M") + X(i) + " " + Y(n.q90); });
    for (var i = nodes.length - 1; i >= 0; i--) bot += " L" + X(i) + " " + Y(nodes[i].q10);
    s += '<path d="' + top + bot + ' Z" fill="rgba(57,182,255,' + op + ')"/>';
    var t2 = "", b2 = "";
    nodes.forEach(function (n, i) { t2 += (i ? " L" : "M") + X(i) + " " + Y(n.q75); });
    for (i = nodes.length - 1; i >= 0; i--) b2 += " L" + X(i) + " " + Y(nodes[i].q25);
    s += '<path d="' + t2 + b2 + ' Z" fill="rgba(57,182,255,' + (op + 0.1) + ')"/>';
    // options-implied (Q) envelope: dotted lines at q50 +/- z90*sigQ (per horizon)
    var qUp = "", qLo = "";
    nodes.forEach(function (n, i) { var sq = n.pq && n.pq.sigQ; if (sq != null) { qUp += (qUp ? " L" : "M") + X(i) + " " + Y(n.q50 + Z90 * sq); qLo += (qLo ? " L" : "M") + X(i) + " " + Y(n.q50 - Z90 * sq); } });
    if (qUp) { s += '<path d="' + qUp + '" stroke="' + VIO + '" stroke-width="1" stroke-dasharray="1 3" fill="none"/><path d="' + qLo + '" stroke="' + VIO + '" stroke-width="1" stroke-dasharray="1 3" fill="none"/>'; }
    // alternate-branch center lines (dashed), opacity by branch probability
    (branches || []).slice(1, 3).forEach(function (b, bi) {
      if (!nodes[0].rd) return;
      var d = "", okAny = false;
      nodes.forEach(function (n, i) { if (n.rd) { d += (i ? " L" : "M") + X(i) + " " + Y(n.rd[b.regime]); okAny = true; } });
      if (okAny) s += '<path d="' + d + '" stroke="' + BRANCH_COL[(bi + 1) % BRANCH_COL.length] + '" stroke-width="1.1" stroke-dasharray="4 3" fill="none" opacity="' + Math.max(0.3, Math.min(0.85, b.p + 0.2)).toFixed(2) + '"/>';
    });
    // MAP center line
    var c = "";
    nodes.forEach(function (n, i) { c += (i ? " L" : "M") + X(i) + " " + Y(n.q50); });
    s += '<path d="' + c + '" stroke="' + BLUE + '" stroke-width="1.6" fill="none"/>';
    var maxV = 0; nodes.forEach(function (n) { if (n.evol) maxV = Math.max(maxV, n.evol); });
    nodes.forEach(function (n, i) {
      var r = n.evol && maxV ? 3 + 7 * Math.sqrt(n.evol / maxV) : 4;
      var col = n.branching == null ? BLUE : (n.branching > 0.5 ? DN : UP);
      var ring = n.eventLinked ? '<circle cx="' + X(i) + '" cy="' + Y(n.q50) + '" r="' + (r + 2.6).toFixed(1) + '" fill="none" stroke="' + ACC + '" stroke-width="1.4"/>' : '';
      s += ring + '<circle cx="' + X(i) + '" cy="' + Y(n.q50) + '" r="' + r.toFixed(1) + '" fill="' + col + '" stroke="#0a0d12" stroke-width="0.6" style="cursor:pointer" onclick="window.MrktLineageUI.focus(\'' + n.h + '\')"><title>' + n.h + ' median ' + pct(n.q50) + ' | 10-90 ' + pct(n.q10) + '/' + pct(n.q90) + (n.evol ? ' | vol ' + fmtVol(n.evol) : '') + (n.eventLinked ? ' | earnings ' + n.eventLinked : '') + '</title></circle>';
      s += '<text x="' + X(i) + '" y="' + (Ht - 12) + '" fill="' + (n.primary ? INK : FAINT) + '" font-size="9" text-anchor="middle">' + n.h + '</text>';
    });
    s += '<text x="2" y="' + (Y(hi) + 8) + '" fill="' + FAINT + '" font-size="9">' + pct(hi, 0) + '</text>';
    s += '<text x="2" y="' + Y(lo) + '" fill="' + FAINT + '" font-size="9">' + pct(lo, 0) + '</text>';
    // legend
    var leg = '<text x="' + padL + '" y="' + (Ht - 1) + '" fill="' + FAINT + '" font-size="8">solid = MAP branch';
    (branches || []).slice(1, 3).forEach(function (b, bi) { leg += '  ·  <tspan fill="' + BRANCH_COL[(bi + 1) % BRANCH_COL.length] + '">– – R' + b.regime + ' ' + (b.p * 100).toFixed(0) + '%</tspan>'; });
    if (nodes.some(function(n){return n.pq&&n.pq.sigQ!=null;})) leg += '  ·  <tspan fill="'+VIO+'">&middot;&middot;&middot; Q (options-implied)</tspan>';
    leg += '  ·  <tspan fill="' + ACC + '">○ earnings-in-window</tspan></text>';
    s += leg + '</svg>';
    return s;
  }

  function heatmapHTML(lin) {
    var sv = lin.sigvol;
    if (!sv) return '<div style="font-size:9px;color:' + FAINT + '">Sigma-volume heatmap populates after the next data build (needs daily volume history).</div>';
    var cols = ORDER.filter(function (h) { return sv[h]; });
    var bins = ["2..3", "1..2", "0..1", "-1..0", "-2..-1", "-3..-2"];
    var maxV = 0;
    cols.forEach(function (h) { bins.forEach(function (b) { var c = sv[h][b]; if (c && c.meanCumVol) maxV = Math.max(maxV, c.meanCumVol); }); });
    var s = '<div style="overflow-x:auto"><table style="border-collapse:collapse;font-size:9px;width:100%">';
    s += '<tr><th style="text-align:right;color:' + FAINT + ';padding:2px 4px">σ \\ horizon</th>' + cols.map(function (h) { return '<th style="color:' + MUTED + ';padding:2px 4px">' + h + '</th>'; }).join("") + '</tr>';
    bins.forEach(function (b) {
      s += '<tr><td style="text-align:right;color:' + FAINT + ';padding:2px 4px">' + b + 'σ</td>';
      cols.forEach(function (h) {
        var c = sv[h][b], mv = c ? c.meanCumVol : null, n = c ? c.n : 0, inten = (mv && maxV) ? mv / maxV : 0;
        s += '<td style="padding:2px 4px;text-align:center;background:' + (mv ? 'rgba(57,182,255,' + (0.06 + 0.5 * inten).toFixed(3) + ')' : "transparent") + ';color:' + INK + '">' + (mv ? fmtVol(mv) : "·") + '<br><span style="color:' + FAINT + '">n=' + n + '</span></td>';
      });
      s += '</tr>';
    });
    s += '</table></div><div style="font-size:8px;color:' + FAINT + ';margin-top:3px">E[cumulative volume | terminal kσ move, horizon] — the volume the tape carries to each move size.</div>';
    return s;
  }

  function nodeCardHTML(node, lin, name) {
    if (!node) return "";
    function chip(k, v, c) { return '<div style="display:flex;flex-direction:column;gap:1px;min-width:78px"><span style="font-size:8.5px;letter-spacing:.04em;text-transform:uppercase;color:' + FAINT + '">' + k + '</span><span style="font-size:13px;font-weight:700;color:' + (c || INK) + '">' + v + '</span></div>'; }
    var S = node.S;
    function px(r) { return S ? "$" + (S * Math.exp(r)).toFixed(2) : pct(r); }
    var evt = node.eventLinked;
    var dlabel = evt ? "event-linked" : "associated";
    var drivers = (name && name.macro3 && name.macro3.top) ? name.macro3.top.slice(0, 3) : [];
    var driverHTML = drivers.length ? drivers.map(function (d) {
      var c = (d.sens >= 0 ? UP : DN);
      return '<span style="color:' + INK + '">' + esc(d.f) + '</span> <span style="color:' + c + '">' + (d.sens >= 0 ? "+" : "") + d.sens + '%/σ</span> <span style="color:' + FAINT + '">(' + dlabel + (d.weak ? ", weak" : "") + ')</span>';
    }).join(" · ") : '<span style="color:' + FAINT + '">no significant rate/commodity drivers learned</span>';
    var v = node.valid;
    var validHTML = v ? ('coverage ' + (v.coverage * 100).toFixed(0) + '% (target ' + (v.target * 100).toFixed(0) + '%, Wilson ' + (v.wilsonLo * 100).toFixed(0) + '–' + (v.wilsonHi * 100).toFixed(0) + '%) · CRPS ' + v.crps + ' · PIT p ' + (v.pitUniformP != null ? v.pitUniformP : "—") + ' · ' + (v.calibrated ? '<span style="color:' + UP + '">calibrated</span>' : '<span style="color:' + DN + '">miscalibrated</span>'))
      : '<span style="color:' + FAINT + '">validation populates after the next build</span>';
    var reason = node.h + ': median ' + px(node.q50) + ' (10–90 ' + px(node.q10) + '/' + px(node.q90) + '), MAP branch ' + (node.pNode != null ? (node.pNode * 100).toFixed(0) + '%' : "—") + '.'
      + (evt ? ' Earnings ' + evt + ' inside this horizon (event-linked).' : '')
      + (node.pUp != null ? ' Touch-up ' + (node.pUp * 100).toFixed(0) + '%/down ' + (node.pDn * 100).toFixed(0) + '%.' : '')
      + (node.evol != null ? ' Expected volume ' + fmtVol(node.evol) + '.' : '')
      + (node.branching != null ? ' Confidence ' + (node.branching * 100).toFixed(0) + '% branch/' + (node.diffusive * 100).toFixed(0) + '% diffusion.' : '');
    var post = lin.post ? lin.post.map(function (p) { return (p * 100).toFixed(0) + '%'; }).join(" / ") : "—";
    var pq = node.pq, top = (lin.pq || {});
    var pqHTML = "";
    if (pq && pq.sigQ != null) {
      var mvp = function (r) { return r == null ? "—" : (S ? "$" + (S * r).toFixed(2) : (r * 100).toFixed(2) + "%"); };
      pqHTML = '<div style="margin-top:6px;border-top:1px solid ' + LINE + ';padding-top:5px">'
        + '<div style="font-size:8.5px;letter-spacing:.05em;text-transform:uppercase;color:' + VIO + '">Physical vs Risk-neutral (P / Q)' + (top.modellable ? ' · <span style="color:' + UP + '">IV present</span>' : ' · <span style="color:' + DN + '">no IV</span>') + '</div>'
        + '<div style="display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end;margin-top:3px">'
        + chip("σ_P model", pct(pq.sigP)) + chip("σ_Q implied", pct(pq.sigQ), VIO) + chip("σ_House", pct(pq.sigHouse))
        + chip("implied |move|", mvp(pq.impliedAbsMove), VIO) + chip("σ-equiv move", mvp(pq.sigmaEquiv))
        + '</div>'
        + '<div style="margin-top:3px;font-size:8.5px;color:' + MUTED + '">event-variance share <b style="color:' + INK + '">' + (pq.eventShare != null ? (pq.eventShare * 100).toFixed(0) + "%" : "—") + '</b> of implied variance (implied-over-realized excess' + (pq.evtIn ? ", earnings in window" : "") + '). IV ' + (top.ivAnnual != null ? (top.ivAnnual * 100).toFixed(0) + "% ann · " + top.ivDays + "d ATM" : "—") + ', &omega;_Q ' + (top.omegaQ != null ? top.omegaQ : "—") + '. Straddle &asymp; implied |move|, NOT the 1&sigma; move.</div>'
        + '</div>';
    }
    var evtChip = evt ? '<span style="font-size:9px;font-weight:700;color:#0a0d12;background:' + ACC + ';padding:1px 7px;border-radius:5px;margin-left:8px">⚑ earnings ' + evt + '</span>' : '';
    return '<div style="background:' + PANEL + ';border:1px solid ' + LINE + ';border-left:3px solid ' + ACC + ';border-radius:8px;padding:8px 10px;margin-top:7px">'
      + '<div style="font-size:9px;letter-spacing:.06em;text-transform:uppercase;color:' + ACC + ';margin-bottom:5px">Lineage node · ' + node.h + (node.primary ? '' : ' (context)') + evtChip + '</div>'
      + '<div style="display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end">'
      + chip("median", px(node.q50), BLUE) + chip("10–90", px(node.q10) + " / " + px(node.q90))
      + chip("σ-equiv", pct(node.vol)) + chip("p(node)", node.pNode != null ? (node.pNode * 100).toFixed(0) + "%" : "—")
      + chip("touch ↑/↓", node.pUp != null ? (node.pUp * 100).toFixed(0) + "% / " + (node.pDn * 100).toFixed(0) + "%" : "—")
      + chip("exp. volume", node.evol != null ? fmtVol(node.evol) : "—", BLUE)
      + '</div>'
      + '<div style="margin-top:6px;font-size:9px;color:' + MUTED + '">Confidence — branch <b style="color:' + INK + '">' + (node.branching != null ? (node.branching * 100).toFixed(0) + "%" : "—") + '</b> · diffusion <b style="color:' + INK + '">' + (node.diffusive != null ? (node.diffusive * 100).toFixed(0) + "%" : "—") + '</b> · calibration <b style="color:' + INK + '">' + (node.calib != null ? (node.calib * 100).toFixed(0) + "%" : "—") + '</b> &nbsp;·&nbsp; regime posterior ' + post + '</div>'
      + '<div style="margin-top:4px;font-size:9px;color:' + MUTED + '">Drivers (ranked) — ' + driverHTML + '</div>'
      + '<div style="margin-top:4px;font-size:9px;color:' + MUTED + '">Validation — ' + validHTML + '</div>'
      + pqHTML
      + '<div style="margin-top:5px;font-size:8.5px;color:' + FAINT + '">' + esc(reason) + ' Research only; not advice.</div>'
      + '</div>';
  }

  function governanceHTML(lin) {
    var g = lin.gov;
    var uni = (window.MMAP && window.MMAP.governance) || null;
    if (!g) {
      var ub = uni ? ' &nbsp;·&nbsp; universe: ' + (uni.counts.deployable||0) + ' deployable / ' + (uni.counts["research-only"]||0) + ' research-only / ' + (uni.counts.blocked||0) + ' blocked' : '';
      return '<div style="margin-top:7px;padding:7px 9px;border:1px dashed ' + LINE + ';border-radius:6px;font-size:9px;color:' + FAINT + '">Governance (FRTB ES · SR 11-7 challenger gate · SPAN scan-risk) populates after the next build.' + ub + '</div>';
    }
    var gate = g.releaseGate || "blocked";
    var gcol = gate === "deployable" ? UP : (gate === "research-only" ? ACC : DN);
    function chip(k, v, c) { return '<div style="display:flex;flex-direction:column;gap:1px;min-width:74px"><span style="font-size:8.5px;letter-spacing:.04em;text-transform:uppercase;color:' + FAINT + '">' + k + '</span><span style="font-size:12px;font-weight:700;color:' + (c || INK) + '">' + v + '</span></div>'; }
    function p2(x) { return x == null ? "—" : (x * 100).toFixed(1) + "%"; }
    var ch = g.challenger, sr = g.scanRisk, sm = g.simm, pr = g.provenance, es = g.es975, ses = g.stressedES;
    // challenger bars (lower CRPS = better)
    var chHTML = "";
    if (ch && ch.crps) {
      var ks = Object.keys(ch.crps), mx = 0; ks.forEach(function (k) { mx = Math.max(mx, ch.crps[k]); });
      chHTML = ks.map(function (k) {
        var w = mx ? (ch.crps[k] / mx * 100) : 0, win = (k === ch.winner);
        var lbl = { model: "model", rw: "random-walk", ewma: "EWMA", q: "options-Q" }[k] || k;
        return '<div style="display:flex;align-items:center;gap:6px;font-size:9px;margin-top:2px"><span style="width:74px;color:' + (win ? INK : MUTED) + '">' + lbl + (win ? ' ★' : '') + '</span><span style="flex:1;background:' + PANEL + ';border:1px solid ' + LINE + ';border-radius:3px;height:9px;position:relative"><span style="position:absolute;left:0;top:0;bottom:0;width:' + w.toFixed(0) + '%;background:' + (win ? UP : "rgba(57,182,255,.4)") + ';border-radius:3px"></span></span><span style="width:54px;text-align:right;color:' + (win ? INK : FAINT) + '">' + ch.crps[k] + '</span></div>';
      }).join("");
    }
    var badges = [
      ["FRTB", es ? "ES97.5 " + p2(es.es) : "—"],
      ["STANS", ses ? "stressed " + p2(ses.es) : "—"],
      ["SPAN", sr ? "scan " + p2(sr.scanRisk) : "—"],
      ["SIMM", sm && sm.delta ? "Δ " + esc(sm.delta.factor) : "—"],
      ["SR 11-7", gate]
    ].map(function (b) { return '<span style="font-size:8px;border:1px solid ' + LINE + ';border-radius:4px;padding:1px 5px;color:' + MUTED + '"><b style="color:' + INK + '">' + b[0] + '</b> ' + esc(b[1]) + '</span>'; }).join(" ");
    var srcHTML = pr && pr.sources ? pr.sources.map(esc).join(" · ") : "—";
    return '<div style="background:' + PANEL + ';border:1px solid ' + LINE + ';border-left:3px solid ' + gol(gcol) + ';border-radius:8px;padding:8px 10px;margin-top:7px">'
      + '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px">'
      + '<span style="font-size:9px;letter-spacing:.06em;text-transform:uppercase;color:' + MUTED + '">Governance &amp; release gate</span>'
      + '<span style="font-size:10px;font-weight:700;color:#0a0d12;background:' + gol(gol(gcol)) + ';padding:1px 8px;border-radius:5px">' + gate.toUpperCase() + '</span>'
      + '</div>'
      + (uni ? '<div style="font-size:8.5px;color:' + FAINT + ';margin-top:2px">universe: <b style="color:' + UP + '">' + (uni.counts.deployable || 0) + '</b> deployable · <b style="color:' + ACC + '">' + (uni.counts["research-only"] || 0) + '</b> research-only · <b style="color:' + DN + '">' + (uni.counts.blocked || 0) + '</b> blocked</div>' : '')
      + '<div style="display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end;margin-top:5px">'
      + chip("ES 97.5", p2(es && es.es), DN) + chip("stressed ES", p2(ses && ses.es), DN)
      + chip("scan risk", p2(sr && sr.scanRisk), DN) + chip("vega (σQ−σP)", sm && sm.vega != null ? p2(sm.vega) : "—", VIO)
      + chip("Δ driver", sm && sm.delta ? esc(sm.delta.factor) : "—")
      + '</div>'
      + (chHTML ? '<div style="margin-top:6px"><div style="font-size:8.5px;letter-spacing:.05em;text-transform:uppercase;color:' + MUTED + '">Challenger scorecard · CRPS (lower = better) · winner ★ ' + (ch.calibrated ? '<span style="color:' + UP + '">calibrated</span>' : '<span style="color:' + DN + '">miscalibrated</span>') + '</div>' + chHTML + '</div>' : '')
      + '<div style="margin-top:5px;font-size:8.5px;color:' + MUTED + '">Verdict — <b style="color:' + gol(gcol) + '">' + gate + '</b>: ' + esc(g.gateReason || "") + '. Curvature ' + (sm && sm.curvature == null ? 'n/a (needs option gamma)' : (sm ? p2(sm.curvature) : '—')) + '.</div>'
      + '<div style="margin-top:4px;font-size:8px;color:' + FAINT + '">Frameworks — ' + badges + '</div>'
      + '<div style="margin-top:3px;font-size:8px;color:' + FAINT + '">Provenance — sources: ' + srcHTML + ' · model ' + (pr ? esc(pr.modelVersion) : "—") + ' · built ' + (pr && pr.builtAt ? esc(pr.builtAt.slice(0, 16).replace("T", " ")) + " UTC" : "—") + ' · ' + (pr ? pr.histWeeks : "—") + 'w history. Research only; not advice.</div>'
      + '</div>';
  }
  function paint(sym, lin, name) {
    var host = el("lineagePanel"); if (!host) return;
    var head = '<div style="font-size:9px;letter-spacing:.06em;text-transform:uppercase;color:' + MUTED + ';margin:8px 0 4px">Lineage forecast · ' + esc(sym) + '</div>';
    if (!lin || !lin.horizons || !Object.keys(lin.horizons).length) {
      host.innerHTML = '<div style="background:' + PANEL + ';border:1px solid ' + LINE + ';border-radius:8px;padding:8px 10px;margin-top:7px">' + head + '<div style="font-size:10px;color:' + FAINT + '">Regime-lineage forecast populates after the next data build for ' + esc(sym) + ' (HMM branches, diffusive/branching confidence, calibration, sigma-volume, touch odds).</div></div>';
      return;
    }
    var nodes = buildNodes(lin, name), branches = lin.branches || [];
    _state = { sym: sym, lin: lin, name: name, nodes: nodes };
    if (!_focus || !nodes.some(function (n) { return n.h === _focus; })) {
      var prim = nodes.filter(function (n) { return n.primary; });
      _focus = (prim[prim.length - 1] || nodes[0]).h;
    }
    var fnode = nodes.filter(function (n) { return n.h === _focus; })[0] || nodes[0];
    var regNow = (lin.regimeNow != null) ? ("regime " + lin.regimeNow + (lin.means ? " (" + (lin.means[lin.regimeNow] >= 0 ? "bull-leaning" : "bear-leaning") + ")" : "")) : "";
    var branchTxt = branches.map(function (b) { return "R" + b.regime + " " + (b.p * 100).toFixed(0) + "%"; }).join(" · ");
    host.innerHTML =
      '<div style="background:' + PANEL + ';border:1px solid ' + LINE + ';border-radius:8px;padding:8px 10px;margin-top:7px">'
      + head
      + '<div style="font-size:9px;color:' + MUTED + ';margin-bottom:4px">Now: ' + regNow + ' &nbsp;·&nbsp; top branches: ' + branchTxt + ' &nbsp;·&nbsp; <span style="color:' + FAINT + '">click a node to inspect</span></div>'
      + ribbonSVG(nodes, branches)
      + '<div style="margin-top:8px;font-size:9px;letter-spacing:.05em;text-transform:uppercase;color:' + MUTED + '">Sigma-volume (expected volume ahead)</div>'
      + heatmapHTML(lin)
      + nodeCardHTML(fnode, lin, name)
      + governanceHTML(lin)
      + '<div style="margin-top:4px;font-size:8px;color:' + FAINT + '">Ribbon = MAP-branch projected return band (q10–q90 outer, q25–q75 inner), opacity ∝ branch probability; dashed lines = alternate-regime branches; dots sized by expected volume, coloured by branch-vs-diffusion confidence, gold ring = earnings inside the horizon. Returns from the current level. Research only.</div>'
      + '</div>';
  }

  function render(sym) {
    if (!sym) return;
    fetch("cards/" + encodeURIComponent(sym) + ".json", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (card) { paint(sym, (card && card.lineage) || (nameOf(sym) || {}).lineage || null, nameOf(sym) || card || null); })
      .catch(function () { paint(sym, (nameOf(sym) || {}).lineage || null, nameOf(sym)); });
  }

  window.MrktLineageUI = { render: render, focus: function (h) { _focus = h; if (_state) paint(_state.sym, _state.lin, _state.name); } };

  function boot() {
    if (!el("lineagePanel")) return;
    var trigger = function () { var s = curSym(); if (s && s !== _last) { _last = s; render(s); } };
    var inp = el("sym");
    if (inp) { inp.addEventListener("change", trigger); inp.addEventListener("input", function () { setTimeout(trigger, 60); }); }
    var sel = el("symsel"); if (sel) sel.addEventListener("change", trigger);
    var dec = el("decision"); if (dec) { try { new MutationObserver(function () { setTimeout(trigger, 50); }).observe(dec, { childList: true, subtree: true }); } catch (e) {} }
    trigger();
    // slow safety net until MMAP is ready, then stop
    var tries = 0, iv = setInterval(function () { trigger(); if ((window.MMAP && window.MMAP.names && ++tries > 2) || ++tries > 120) clearInterval(iv); }, 1500);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
