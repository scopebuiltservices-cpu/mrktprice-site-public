/* fib_panel.js — the MISSING projClose-vs-priceNow tiles. Renders multi-horizon projected-close tiles
   (24H / 48H / 1W / 1M) for the loaded ticker, each compared to the live price, using window.MrktFib
   (the verified fib_engine.js port of fib_ref.py). Reads CUR (the terminal's current-ticker object:
   CUR.c=closes, CUR.last=priceNow, CUR.sym). Edge = mean of last 5 log returns (5-session momentum
   drift); horizon vol is variance-ratio-corrected and the drift decays by the OU half-life. Research only.
   Externalized per the project protocol (node-checkable). */
(function () {
  'use strict';
  var MOUNT = 'fibProjTiles', lastKey = '';

  function cur() { try { return (typeof CUR === 'object' && CUR) ? CUR : null; } catch (e) { return null; } }
  function fmt(x, d) { return (x == null || x !== x) ? '—' : x.toFixed(d == null ? 2 : d); }
  function pct(x) { return (x == null || x !== x) ? '—' : (x >= 0 ? '+' : '') + (x * 100).toFixed(2) + '%'; }
  var GRN = '#2ecc8f', RED = '#ef5f4e', IK = 'var(--ink)', MU = 'var(--muted)';

  function mount() {
    var p = document.getElementById(MOUNT);
    if (p) return p;
    p = document.createElement('div'); p.id = MOUNT; p.style.margin = '6px 0';
    var host = document.getElementById('intradayProjPanel') || document.getElementById('intradayStrip')
      || document.getElementById('intradayEodPanel');
    if (host && host.parentNode) host.parentNode.insertBefore(p, host.nextSibling);
    else document.body.appendChild(p);
    return p;
  }

  function tile(label, projClose, delta, deltaPct, pUp, lo, hi, zEdge, capped) {
    var col = delta >= 0 ? GRN : RED;
    var arrow = delta >= 0 ? '▲' : '▼';
    var conf = (zEdge == null || zEdge !== zEdge) ? '' :
      '<span style="color:' + (Math.abs(zEdge) >= 1 ? col : MU) + '"> · z ' + (zEdge >= 0 ? '+' : '') + zEdge.toFixed(2) + '</span>';
    return '<div style="flex:1;min-width:104px;background:var(--panel2,#111721);border:1px solid var(--line);border-left:3px solid ' + col + ';border-radius:6px;padding:6px 8px">'
      + '<div style="font-size:8px;letter-spacing:.4px;color:' + MU + ';text-transform:uppercase">' + label + ' proj close' + (capped ? ' · capped' : '') + '</div>'
      + '<div style="font-size:15px;font-weight:700;color:' + col + '">$' + fmt(projClose) + '</div>'
      + '<div style="font-size:9px;color:' + col + '">' + arrow + ' ' + (delta >= 0 ? '+' : '') + '$' + fmt(Math.abs(delta)) + ' · ' + pct(deltaPct) + '</div>'
      + '<div style="font-size:8px;color:' + MU + '">P↑ ' + (pUp == null || pUp !== pUp ? '—' : Math.round(pUp * 100) + '%') + ' · 1σ $' + fmt(lo) + '–$' + fmt(hi) + conf + '</div>'
      + '</div>';
  }

  function nowTile(priceNow, hl, sigD) {
    return '<div style="flex:1;min-width:104px;background:#0b0e13;border:1px solid var(--line);border-radius:6px;padding:6px 8px">'
      + '<div style="font-size:8px;letter-spacing:.4px;color:' + MU + ';text-transform:uppercase">price now</div>'
      + '<div style="font-size:15px;font-weight:700;color:' + IK + '">$' + fmt(priceNow) + '</div>'
      + '<div style="font-size:8px;color:' + MU + '">half-life ' + fmt(hl, 1) + 'd · σ/d ' + (sigD != null && sigD === sigD ? (sigD * 100).toFixed(2) + '%' : '—') + '</div>'
      + '</div>';
  }

  function render() {
    if (!window.MrktFib) return;
    var C = cur();
    var p = document.getElementById(MOUNT);
    if (!C || !C.c || !C.c.length) { if (p) p.innerHTML = ''; lastKey = ''; return; }
    var closes = C.c, priceNow = (C.last != null) ? C.last : closes[closes.length - 1], sym = (C.sym || '').toUpperCase();
    if (!(priceNow > 0) || closes.length < 30) {
      p = mount();
      p.innerHTML = '<div class="note" style="font-size:10px"><b style="color:var(--gold)">MULTI-HORIZON PROJECTION</b> — need ≥30 daily bars (' + closes.length + ' loaded).</div>';
      lastKey = sym + ':short'; return;
    }
    var key = sym + ':' + closes.length + ':' + priceNow;
    if (key === lastKey && p && p.children.length) return;   // nothing changed
    var F = window.MrktFib;
    var rets = F.logret(closes);
    var edge = rets.length >= 5 ? rets.slice(-5).reduce(function (a, b) { return a + b; }, 0) / 5.0 : (rets.length ? rets.reduce(function (a, b) { return a + b; }, 0) / rets.length : 0);
    var hl = F.fit_halflife(closes), sigD = F.blended_sigma_daily(rets);
    var proj = F.project(priceNow, edge, closes, F.horizons('fib'), { hl: hl });   // 1,2,3,5,8,13,21,34,55 — contains all user tiles (1/2/5/21)
    var sub = F.user_subset(proj);
    var order = ['24H', '48H', '1W', '1M'];
    var tiles = nowTile(priceNow, hl, sigD);
    order.forEach(function (lab) {
      var q = sub[lab]; if (!q) return;
      var projClose = q.projPrice, delta = projClose - priceNow, dPct = projClose / priceNow - 1.0;
      var pUp = F.prob_above(priceNow, q.muLog, q.sigmaH, priceNow);
      tiles += tile(lab, projClose, delta, dPct, pUp, q.lo, q.hi, q.zEdge, q.capped);
    });
    // SERVER cross-check: the no-lookahead OU/EMA-blend 21d projection (proj_board.py -> n.pj) — the SAME
    // forecast the projClose-vs-priceNow learning is scored on. Shown as a reference beside the client tiles.
    var _srv = '';
    try {
      var _m = window.MMAP && window.MMAP.names, _pj = null;
      if (_m) { for (var _i = 0; _i < _m.length; _i++) { if ((_m[_i].t || '').toUpperCase() === sym && _m[_i].pj) { _pj = _m[_i].pj; break; } } }
      if (_pj) {
        var _c = _pj.projPct >= 0 ? 'var(--up,#2ecc8f)' : 'var(--down,#ef5f4e)';
        _srv = '<div style="font-size:9px;color:' + MU + ';margin:5px 0 0"><b style="color:#9ab4e0">server ' + (_pj.h || 21) + 'd (no-lookahead, OU/EMA blend)</b> · proj $' + (_pj.projClose != null ? _pj.projClose : '?')
          + ' <span style="color:' + _c + '">' + (_pj.projPct >= 0 ? '+' : '') + _pj.projPct + '%</span> · P(up) ' + (_pj.probUp != null ? Math.round(_pj.probUp * 100) + '%' : '?')
          + ' · σ' + (_pj.sigmaHPct != null ? _pj.sigmaHPct + '%' : '?') + ' — the forecast the daily learning is scored against</div>';
      }
    } catch (e) {}
    p = mount();
    p.innerHTML = '<div style="font-size:10px;color:' + MU + ';margin:4px 0"><b style="color:var(--gold)">MULTI-HORIZON PROJECTION</b> · ' + sym
      + ' · projected close vs price now · VR-corrected σ, half-life-decayed drift · research only</div>'
      + '<div style="display:flex;gap:5px;flex-wrap:wrap">' + tiles + '</div>' + _srv;
    lastKey = key;
  }

  function loop() { try { render(); } catch (e) {} }
  if (document.readyState !== 'loading') setTimeout(loop, 800);
  else document.addEventListener('DOMContentLoaded', function () { setTimeout(loop, 800); });
  setInterval(loop, 1500);
})();
