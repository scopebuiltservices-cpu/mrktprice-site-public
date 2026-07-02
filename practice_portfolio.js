/* practice_portfolio.js — PRACTICE PORTFOLIO · teacher dashboard (below the graphs).
 * A hands-on, education-first practice book: add tickers + share counts, watch total value and each
 * position re-rank live by value, track confirmed 5-minute & 15-minute momentum (wall-clock windows
 * sampled from the live/close feed), and get nuanced, evidence-based portfolio-management EDUCATION
 * (concentration/HHI, diversification, momentum leadership, and per-holding persist/fade + expected
 * path from the parity-locked engines). Research & education only — NOT investment advice, no orders.
 *
 * Reuses: window.intradayFetch (live 15-min metrics), window._isRTH, window.DATA / window.MMAP (prices +
 * history), window.PathProj (vrMulti persistence + path projection). Pure DOM, localStorage-persisted. */
(function () {
  'use strict';
  var LS_HOLD = 'mrkt.practice.v1';      // [{t, shares}]
  var LS_PX = 'mrkt.practice.px.';       // per-symbol price ring buffer [[ts, price], ...]
  var MAXPX = 400, SAMPLE_MS = 20000, POLL_MS = 30000, MAXHOLD = 40;
  var LIVE = {};                          // {SYM: {price, ts, mom15}}
  var _timer = null, _mount = null;

  // ---------- storage ----------
  function _ls(k, d) { try { var v = JSON.parse(localStorage.getItem(k)); return v == null ? d : v; } catch (_e) { return d; } }
  function _save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_e) {} }
  function holdings() { return _ls(LS_HOLD, []).filter(function (h) { return h && h.t && h.shares > 0; }); }
  function setHoldings(h) { _save(LS_HOLD, h); }

  // ---------- price / history resolution (any ticker) ----------
  function _DATA() { try { return window.DATA || (typeof DATA !== 'undefined' ? DATA : null); } catch (_e) { return null; } }
  function _mmap() { try { return (window.MMAP && window.MMAP.names) ? window.MMAP.names : null; } catch (_e) { return null; } }
  function _node(sym) { var m = _mmap(); if (!m) return null; sym = sym.toUpperCase(); for (var i = 0; i < m.length; i++) if ((m[i].t || '').toUpperCase() === sym) return m[i]; return null; }
  function closesOf(sym) { var D = _DATA(); if (D && D[sym] && D[sym].closes && D[sym].closes.length) return D[sym].closes; var n = _node(sym); if (n && n.closes && n.closes.length) return n.closes; return null; }
  function volsOf(sym) { var D = _DATA(); return (D && D[sym] && D[sym].volumes) ? D[sym].volumes : null; }
  function lastClose(sym) { var c = closesOf(sym); if (c && c.length) return c[c.length - 1]; var n = _node(sym); return (n && n.px != null) ? n.px : null; }
  function prevClose(sym) { var c = closesOf(sym); return (c && c.length >= 2) ? c[c.length - 2] : null; }

  function spot(sym) { // best available price + source
    var lv = LIVE[sym];
    if (lv && lv.price != null && (Date.now() - lv.ts) < 20 * 60000) return { price: lv.price, src: 'live' };
    var c = lastClose(sym); return c != null ? { price: c, src: 'close' } : null;
  }

  // ---------- wall-clock momentum from a sampled ring buffer ----------
  function sample(sym, price) {
    if (!(price > 0)) return;
    var k = LS_PX + sym, buf = _ls(k, []), now = Date.now();
    if (!buf.length || buf[buf.length - 1][0] < now - SAMPLE_MS) {
      // only record a genuinely NEW (confirmed) price point
      if (!buf.length || buf[buf.length - 1][1] !== price) { buf.push([now, price]); if (buf.length > MAXPX) buf = buf.slice(-MAXPX); _save(k, buf); }
    }
  }
  function mom(sym, mins) { // % change over the last `mins` wall-clock minutes
    var buf = _ls(LS_PX + sym, []); if (buf.length < 2) return null;
    var now = buf[buf.length - 1][0], cut = now - mins * 60000, base = null, i;
    for (i = buf.length - 1; i >= 0; i--) { if (buf[i][0] <= cut) { base = buf[i][1]; break; } }
    if (base == null) { if (buf[0][0] > now - mins * 60000 * 0.5) return null; base = buf[0][1]; } // not enough span yet
    var last = buf[buf.length - 1][1];
    return (base > 0) ? (last / base - 1) * 100 : null;
  }

  // ---------- live poll ----------
  function poll() {
    var hs = holdings(); if (!hs.length) return;
    var live = !!((window.MRKT_TOKEN || window.MRKT_CODE) && window._isRTH && window._isRTH());
    hs.slice(0, MAXHOLD).forEach(function (h) {
      var sym = h.t;
      if (live && window.intradayFetch) {
        window.intradayFetch(sym).then(function (j) {
          var m = j && j.metrics; if (m && m.price != null) { LIVE[sym] = { price: m.price, ts: Date.now(), mom15: m.momentumPctPerBar }; sample(sym, m.price); }
        }).catch(function () {});
      } else {
        var c = lastClose(sym); if (c != null) sample(sym, c);   // close-mode: seed the buffer so weights/rank work
      }
    });
    setTimeout(function () { try { render(); } catch (_e) {} }, 1500);
  }

  // ---------- per-holding row model ----------
  function rowModel(h) {
    var sym = h.t, sp = spot(sym), price = sp ? sp.price : null, src = sp ? sp.src : 'none';
    var pc = prevClose(sym), lc = lastClose(sym);
    var dayPct = null;
    if (price != null) {
      if (src === 'live' && lc) dayPct = (price / lc - 1) * 100;         // live vs last completed close
      else if (pc) dayPct = (lc / pc - 1) * 100;                          // last completed session move
    }
    var value = (price != null) ? h.shares * price : null;
    var m5 = mom(sym, 5), m15 = mom(sym, 15);
    if (m15 == null && LIVE[sym] && LIVE[sym].mom15 != null) m15 = LIVE[sym].mom15; // fallback to engine 15-min bar momentum
    // persistence + expected path (parity-locked engines) when history is available
    var vp = null, pj = null, cl = closesOf(sym);
    if (cl && cl.length >= 60 && window.PathProj) {
      try { var vm = window.PathProj.vrMulti(cl); if (vm) vp = vm; } catch (_e) {}
      try { pj = window.PathProj.project(cl, volsOf(sym), 21, 5); } catch (_e2) {}
    }
    return { sym: sym, shares: h.shares, price: price, src: src, dayPct: dayPct, value: value, m5: m5, m15: m15, vp: vp, pj: pj };
  }

  // ---------- education / recommendations (NOT advice) ----------
  function recommendations(rows, total) {
    var recs = [], n = rows.length;
    if (!n) return recs;
    var weights = rows.map(function (r) { return (r.value != null && total > 0) ? r.value / total : 0; });
    var hhi = weights.reduce(function (a, w) { return a + w * w; }, 0);
    var eff = hhi > 0 ? 1 / hhi : 0;                                        // effective number of positions
    var top = rows[0], topW = weights[0] || 0;
    if (topW >= 0.4) recs.push(['Concentration', 'Your largest position, <b>' + top.sym + '</b>, is <b>' + (topW * 100).toFixed(0) + '%</b> of the book. One name driving the portfolio means one name drives your risk. Sizing rules of thumb (e.g. 5–10% per name) exist because idiosyncratic shocks are survivable only when no single holding can sink you.', '#ef5f4e']);
    else if (n >= 3 && topW < 0.25) recs.push(['Balance', 'No position exceeds ' + (topW * 100).toFixed(0) + '% — a reasonably balanced book. Effective breadth ≈ <b>' + eff.toFixed(1) + '</b> independent-sized positions (1/HHI).', '#2ecc8f']);
    if (n < 3) recs.push(['Diversification', 'With ' + n + ' holding' + (n === 1 ? '' : 's') + ', portfolio outcomes ≈ single-stock outcomes. Diversification only starts reducing idiosyncratic variance once holdings are several AND not highly correlated — count *independent bets*, not tickers.', '#e0c14a']);
    // momentum leadership: are the biggest weights the momentum leaders or the laggards?
    var withMom = rows.filter(function (r) { return r.m15 != null; });
    if (withMom.length >= 2) {
      var lead = withMom.slice().sort(function (a, b) { return (b.m15) - (a.m15); })[0];
      var lag = withMom.slice().sort(function (a, b) { return (a.m15) - (b.m15); })[0];
      recs.push(['Momentum leadership', 'Live 15-min leader: <b>' + lead.sym + '</b> (' + (lead.m15 >= 0 ? '+' : '') + lead.m15.toFixed(2) + '%); laggard: <b>' + lag.sym + '</b> (' + (lag.m15 >= 0 ? '+' : '') + lag.m15.toFixed(2) + '%). Whether to add to strength or trim it depends on the persist/fade regime below — momentum alone is not a plan.', '#39b6ff']);
    }
    // persistence mix from the VR engine
    var per = 0, fad = 0, rw = 0;
    rows.forEach(function (r) { if (r.vp) { var sig = r.vp.pJoint != null && r.vp.pJoint <= 0.10; if (sig && r.vp.vrStar > 1) per++; else if (sig && r.vp.vrStar < 1) fad++; else rw++; } });
    if (per + fad + rw > 0) recs.push(['Regime mix', per + ' name(s) in a significant <b style="color:#2ecc8f">persist</b> regime, ' + fad + ' in <b style="color:#ef5f4e">fade</b>, ' + rw + ' random-walk. Persisters reward letting winners run and adding on strength; faders reward trimming into strength and buying weakness. Trading a fader like a persister (or vice-versa) is a classic self-inflicted loss.', '#c9a24a']);
    return recs;
  }

  var EDU = [
    ['Position sizing before selection', 'The size of a bet usually matters more than which bet. Equal-conviction names deserve roughly equal risk, not equal dollars — a volatile name at the same dollar weight carries more risk. Size down what moves more.'],
    ['Concentration vs diversification', 'Diversification lowers idiosyncratic (stock-specific) risk, not market risk. Its benefit fades as holdings correlate: 10 tech names ≈ one big tech bet. Track *effective* positions (1/HHI), not the ticker count.'],
    ['Let winners run — but only in the right regime', 'Trend-following pays when returns persist (variance ratio > 1, significant). Averaging down and fading pays when they mean-revert (VR < 1). The persist/fade tile tells you which world a name is in; the biggest mistakes come from using the wrong playbook.'],
    ['Rebalance with intent, not reflex', 'Rebalancing sells strength and buys weakness — powerful for mean-reverters, costly for strong trends. Rebalance on a rule (bands or calendar), and be aware it fights momentum.'],
    ['Momentum is a clock, not a compass', 'A 5- or 15-minute push tells you what is happening now, not where price ends up. Confirmed intraday direction + a significant multi-day persistence regime is a far stronger combination than either alone.'],
    ['Costs, taxes, and overtrading', 'Every trade pays spread + fees, and (in a taxable account) can trigger tax. The edge from a marginal trade must beat those frictions — the cheapest alpha is often the trade you do not make.']
  ];

  // ---------- render ----------
  function fmtMoney(x) { return x == null ? '—' : '$' + x.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function pctSpan(x, dp) { if (x == null) return '<span style="color:var(--faint,#646e7c)">—</span>'; var c = x >= 0 ? '#2ecc8f' : '#ef5f4e'; return '<span style="color:' + c + '">' + (x >= 0 ? '+' : '') + x.toFixed(dp == null ? 2 : dp) + '%</span>'; }

  function render() {
    if (!_mount) _mount = document.getElementById('practicePortfolio');
    if (!_mount) return;
    // don't rebuild while the user is typing inside the panel (preserve focus)
    var ae = document.activeElement;
    var typing = ae && _mount.contains(ae) && (ae.tagName === 'INPUT');
    if (typing && _mount.querySelector('#ppBody')) return;

    var hs = holdings(), rows = hs.map(rowModel);
    rows.sort(function (a, b) { return (b.value || -1) - (a.value || -1); });   // hierarchy by value, live-reordering
    var total = rows.reduce(function (a, r) { return a + (r.value || 0); }, 0);
    var totalPrev = rows.reduce(function (a, r) { var pc = prevClose(r.sym), lc = lastClose(r.sym); var base = (r.src === 'live') ? lc : pc; return a + ((base != null) ? r.shares * base : 0); }, 0);
    var totDay = (totalPrev > 0) ? (total / totalPrev - 1) * 100 : null;
    var liveOn = !!((window.MRKT_TOKEN || window.MRKT_CODE) && window._isRTH && window._isRTH());

    var css = 'background:var(--panel2,#141a24);border:1px solid var(--line,#2a2f3a);border-radius:10px;padding:10px 12px';
    var h = '<div style="' + css + '">';
    h += '<div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px">'
      + '<span style="font-size:13px;font-weight:800;letter-spacing:.04em;color:var(--ink,#eef3f8)">PRACTICE PORTFOLIO <span style="font-weight:600;color:var(--muted,#8a93a0)">· teacher dashboard</span></span>'
      + '<span style="font-size:11px;color:var(--muted,#8a93a0)">total <b style="font-size:15px;color:var(--ink,#eef3f8)">' + fmtMoney(total) + '</b> · ' + pctSpan(totDay) + ' · <span style="padding:1px 6px;border-radius:5px;font-size:9px;font-weight:700;background:' + (liveOn ? '#123' : '#222') + ';color:' + (liveOn ? '#2ecc8f' : '#8a93a0') + '">' + (liveOn ? 'LIVE 15-min' : 'CLOSE') + '</span></span></div>';

    // add form (persistent ids so focus survives)
    h += '<div id="ppForm" style="display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 6px">'
      + '<input id="ppSym" placeholder="ticker" style="width:90px;text-transform:uppercase;background:var(--panel,#10141b);border:1px solid var(--line,#2a2f3a);color:var(--ink,#eef3f8);border-radius:6px;padding:5px 7px;font-size:12px">'
      + '<input id="ppSh" type="number" min="0" step="1" placeholder="shares" style="width:90px;background:var(--panel,#10141b);border:1px solid var(--line,#2a2f3a);color:var(--ink,#eef3f8);border-radius:6px;padding:5px 7px;font-size:12px">'
      + '<button id="ppAdd" style="background:var(--brand,#16c79a);color:#04120d;border:none;border-radius:6px;padding:5px 12px;font-size:12px;font-weight:700;cursor:pointer">+ Add</button>'
      + '<span style="font-size:9px;color:var(--faint,#646e7c);align-self:center">value ranks the book; 5m/15m are confirmed wall-clock momentum from the live feed</span></div>';

    h += '<div id="ppBody">';
    if (!rows.length) {
      h += '<div style="font-size:11px;color:var(--faint,#646e7c);padding:6px 0">Add a ticker and a share count to start your practice book. Everything is saved in this browser.</div>';
    } else {
      h += '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:11px">'
        + '<tr style="color:var(--faint,#646e7c);text-align:right;font-size:9px;letter-spacing:.04em;text-transform:uppercase">'
        + '<th style="text-align:left;padding:3px 4px">#</th><th style="text-align:left">ticker</th><th>shares</th><th>price</th><th>value</th><th>weight</th><th>day</th><th>5m</th><th>15m</th><th style="text-align:left;padding-left:8px">regime</th><th></th></tr>';
      rows.forEach(function (r, i) {
        var w = (total > 0 && r.value != null) ? (r.value / total * 100) : null;
        var badge = r.src === 'live' ? '<span style="color:#2ecc8f;font-size:8px"> ●</span>' : (r.src === 'close' ? '<span style="color:#8a93a0;font-size:8px"> ○</span>' : '');
        var reg = '—';
        if (r.vp) { var sig = r.vp.pJoint != null && r.vp.pJoint <= 0.10; var lab = sig ? (r.vp.vrStar > 1 ? 'PERSIST' : 'FADE') : 'RW'; var rc = lab === 'PERSIST' ? '#2ecc8f' : (lab === 'FADE' ? '#ef5f4e' : '#e0c14a'); reg = '<span style="color:' + rc + ';font-weight:700">' + lab + '</span>' + (r.pj && r.pj.smart ? ' <span style="color:var(--faint,#646e7c)">' + r.pj.pathPct.toFixed(0) + '% ' + (r.pj.dir > 0 ? '↑' : '↓') + '</span>' : ''); }
        h += '<tr style="text-align:right;border-top:1px solid var(--line,#2a2f3a)">'
          + '<td style="text-align:left;padding:4px;color:var(--faint,#646e7c)">' + (i + 1) + '</td>'
          + '<td style="text-align:left;font-weight:700;color:var(--ink,#eef3f8)">' + r.sym + badge + '</td>'
          + '<td><input class="ppShInp" data-sym="' + r.sym + '" type="number" min="0" step="1" value="' + r.shares + '" style="width:64px;text-align:right;background:transparent;border:1px solid var(--line,#2a2f3a);color:var(--ink,#eef3f8);border-radius:4px;padding:2px 4px;font-size:11px"></td>'
          + '<td>' + (r.price != null ? r.price.toFixed(2) : '—') + '</td>'
          + '<td style="font-weight:700;color:var(--ink,#eef3f8)">' + fmtMoney(r.value) + '</td>'
          + '<td>' + (w != null ? w.toFixed(1) + '%' : '—') + '</td>'
          + '<td>' + pctSpan(r.dayPct) + '</td>'
          + '<td>' + pctSpan(r.m5) + '</td>'
          + '<td>' + pctSpan(r.m15) + '</td>'
          + '<td style="text-align:left;padding-left:8px">' + reg + '</td>'
          + '<td><span class="ppDel" data-sym="' + r.sym + '" title="remove" style="cursor:pointer;color:var(--faint,#646e7c);padding:0 4px">×</span></td></tr>';
      });
      h += '</table></div>';

      // recommendations (education, not advice)
      var recs = recommendations(rows, total);
      if (recs.length) {
        h += '<div style="margin-top:9px;border-top:1px solid var(--line,#2a2f3a);padding-top:7px"><div style="font-size:9px;letter-spacing:.05em;text-transform:uppercase;color:var(--faint,#646e7c);margin-bottom:4px">Coaching · what this book is telling you</div>';
        recs.forEach(function (r) {
          h += '<div style="display:flex;gap:7px;margin:4px 0;font-size:10.5px;line-height:1.4"><span style="flex:0 0 auto;min-width:78px;color:' + r[2] + ';font-weight:700">' + r[0] + '</span><span style="color:var(--muted,#8a93a0)">' + r[1] + '</span></div>';
        });
        h += '</div>';
      }
    }
    // education (always available)
    h += '<details style="margin-top:8px"><summary style="cursor:pointer;font-size:10px;color:var(--muted,#8a93a0);letter-spacing:.04em;text-transform:uppercase">Portfolio management — principles</summary><div style="margin-top:5px">';
    EDU.forEach(function (e) { h += '<div style="margin:5px 0;font-size:10.5px;line-height:1.45"><b style="color:var(--ink,#eef3f8)">' + e[0] + '.</b> <span style="color:var(--muted,#8a93a0)">' + e[1] + '</span></div>'; });
    h += '</div></details>';
    h += '<div style="font-size:8px;color:var(--faint,#646e7c);margin-top:6px">Practice &amp; education only — a paper book saved in your browser. Not investment advice; no orders are placed. Live prices need sign-in during market hours; otherwise last close is used.</div>';
    h += '</div>';
    _mount.innerHTML = h;
    bind();
  }

  function bind() {
    var add = document.getElementById('ppAdd');
    if (add) add.onclick = function () {
      var s = (document.getElementById('ppSym').value || '').trim().toUpperCase();
      var sh = parseFloat(document.getElementById('ppSh').value);
      if (!s || !(sh > 0)) return;
      var h = holdings(); var ex = h.filter(function (x) { return x.t === s; })[0];
      if (ex) ex.shares = sh; else h.push({ t: s, shares: sh });
      setHoldings(h); LIVE[s] = LIVE[s] || null; poll(); render();
    };
    Array.prototype.forEach.call(_mount.querySelectorAll('.ppDel'), function (el) {
      el.onclick = function () { var s = el.getAttribute('data-sym'); setHoldings(holdings().filter(function (x) { return x.t !== s; })); render(); };
    });
    Array.prototype.forEach.call(_mount.querySelectorAll('.ppShInp'), function (el) {
      el.onchange = function () { var s = el.getAttribute('data-sym'), v = parseFloat(el.value); var h = holdings(); var ex = h.filter(function (x) { return x.t === s; })[0]; if (ex) { if (v > 0) ex.shares = v; else h = h.filter(function (x) { return x.t !== s; }); setHoldings(h); render(); } };
    });
  }

  function init() {
    _mount = document.getElementById('practicePortfolio'); if (!_mount) return;
    render(); poll();
    if (!_timer) _timer = setInterval(function () { try { poll(); } catch (_e) {} }, POLL_MS);
  }

  window.PracticePortfolio = { init: init, render: render, poll: poll };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else setTimeout(init, 0);
})();
