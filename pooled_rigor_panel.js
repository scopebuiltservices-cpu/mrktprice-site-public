/* ===== MrktPrice — POOLED RIGOR+ panel (external) =====
   Runs window.PooledRigor over the live basket (ACTIVE() + DATA[tk].closes) to surface the selection-bias
   and panel-dependence layer the Reproducible Report specified: effective breadth (eigenvalue participation
   ratio), random-effects meta (pooled beta + I2), PSR + MinTRL of the pooled composite Sharpe, PBO (CSCV)
   over the threshold x hold grid, and White Reality Check + Hansen SPA over the threshold variants.
   Self-contained; degrades gracefully; research only. */
(function () {
  'use strict';
  var H = 10, THR = [0.1, 0.2, 0.3, 0.4], HOLDS = [3, 5, 10];
  function clamp(v) { return Math.max(-1, Math.min(1, v)); }
  function lr(c) { var o = []; for (var i = 1; i < c.length; i++) if (c[i - 1] > 0 && c[i] > 0) o.push(Math.log(c[i] / c[i - 1])); return o; }
  function sma(c, i, n) { var s = 0; for (var k = i - n + 1; k <= i; k++) s += c[k]; return s / n; }
  function std(c, i, n) { var m = sma(c, i, n), s = 0; for (var k = i - n + 1; k <= i; k++) s += (c[k] - m) * (c[k] - m); return Math.sqrt(s / (n - 1)); }
  function ema(c, n) { var a = 2 / (n + 1), e = [c[0]]; for (var i = 1; i < c.length; i++)e.push(a * c[i] + (1 - a) * e[i - 1]); return e; }
  function sig(c) {                                   // btEdge composite: 0.5*clamp(slope/1.5)+0.5*clamp(z/2)
    var n = c.length, e5 = ema(c, 5), out = new Array(n).fill(0);
    for (var i = 25; i < n; i++) { var sl = (e5[i] - e5[i - 5]) / c[i] / 5 * 100, z = (c[i] - sma(c, i, 20)) / (std(c, i, 20) || 1e-9); out[i] = 0.5 * clamp(sl / 1.5) + 0.5 * clamp(z / 2); }
    return out;
  }
  function olsSlopeT(x, y) {                          // slope + NW-ish (here OLS) SE for meta-analysis
    var n = x.length; if (n < 10) return null; var mx = 0, my = 0, i; for (i = 0; i < n; i++) { mx += x[i]; my += y[i]; } mx /= n; my /= n;
    var sxx = 0, sxy = 0; for (i = 0; i < n; i++) { sxx += (x[i] - mx) * (x[i] - mx); sxy += (x[i] - mx) * (y[i] - my); } if (sxx <= 0) return null;
    var b = sxy / sxx, sse = 0; for (i = 0; i < n; i++) { var yh = my + b * (x[i] - mx); sse += (y[i] - yh) * (y[i] - yh); }
    var s2 = sse / Math.max(n - 2, 1), se = Math.sqrt(s2 / sxx); return { b: b, se: se };
  }

  function compute() {
    var Rg = window.PooledRigor; if (!Rg || typeof ACTIVE !== 'function' || typeof DATA !== 'object') return null;
    var tks = ACTIVE().filter(function (t) { return DATA[t] && DATA[t].closes && DATA[t].closes.length >= 80; }).slice(0, 60);
    if (tks.length < 3) return null;
    // per-ticker signal, forward return, returns
    var betas = [], ses = [], rets = [], pooledStrat = [], moverTop = null, moverVal = -1e18;
    var L = Math.min.apply(null, tks.map(function (t) { return lr(DATA[t].closes).length; }));
    var gridSeries = {}; THR.forEach(function (th) { HOLDS.forEach(function (h) { gridSeries[th + '_' + h] = []; }); });
    var rcCols = {};                                   // threshold variant differential returns vs buy&hold
    THR.forEach(function (th) { rcCols[th] = []; });
    tks.forEach(function (t) {
      var c = DATA[t].closes, s = sig(c), n = c.length, x = [], y = [];
      for (var i = 25; i < n - H; i++) { x.push(s[i]); y.push(c[i + H] / c[i] - 1); }
      var fit = olsSlopeT(x, y); if (fit) { betas.push(fit.b); ses.push(fit.se); }
      rets.push(lr(c).slice(-L));
      // pooled composite strategy (thr .3 / hold 1) returns for PSR/MinTRL
      for (i = 25; i < n - 1; i++) { var q = s[i] > 0.3 ? 1 : (s[i] < -0.3 ? -1 : 0); pooledStrat.push(q * (c[i + 1] / c[i] - 1)); }
      // top mover by |latest signal change|
      var dv = Math.abs(s[n - 1] - s[n - 6]); if (dv > moverVal) { moverVal = dv; moverTop = { t: t, now: s[n - 1], prev: s[n - 6] }; }
    });
    // correlation matrix -> effective breadth
    var K = rets.length, corr = [];
    for (var a = 0; a < K; a++) { corr[a] = []; for (var b = 0; b < K; b++) { corr[a][b] = a === b ? 1 : pearson(rets[a], rets[b]); } }
    var effB = Rg.effectiveBreadth(corr);
    var meta = Rg.randomEffectsMeta(betas, ses);
    var sr = Rg.sharpe(pooledStrat), ps = sr != null ? Rg.psr(sr, pooledStrat.length) : null, mt = sr != null ? Rg.minTRL(sr) : null;
    // PBO over the threshold x hold grid (pooled per-period strat return per config)
    var Tlen = L, configs = Object.keys(gridSeries), M = [];
    for (var ti = 0; ti < Tlen; ti++) M.push(new Array(configs.length).fill(0));
    tks.forEach(function (t) {
      var c = DATA[t].closes, s = sig(c), n = c.length, rr = lr(c), off = rr.length - Tlen;
      configs.forEach(function (cfg, ci) {
        var th = parseFloat(cfg.split('_')[0]);
        for (var i = 0; i < Tlen; i++) { var idx = off + i + 25; if (idx < n - 1) { var q = s[idx] > th ? 1 : (s[idx] < -th ? -1 : 0); M[i][ci] += q * (c[idx + 1] / c[idx] - 1) / tks.length; } }
      });
    });
    var pbo = Rg.pboCSCV(M, 8);
    // Reality Check / SPA: threshold-variant pooled strat minus buy&hold, per period
    var D = [];
    for (ti = 0; ti < Tlen; ti++) { var row = []; THR.forEach(function (th, k) { row.push(M[ti][configs.indexOf(th + '_' + HOLDS[1])] - (M[ti][0] >= 0 ? 0 : 0)); }); D.push(row); }
    var rc = Rg.realityCheck(D, 400), spa = Rg.spa(D, 400);
    var mover = moverTop ? Rg.moverDecomp({ sMR: 0, sMom: moverTop.now, sSig: 0, sVol: 0 }, { sMR: 0, sMom: moverTop.prev, sSig: 0, sVol: 0 }) : null;
    return { N: tks.length, effB: effB, meta: meta, sr: sr, psr: ps, mtrl: mt, pbo: pbo, rc: rc, spa: spa, mover: mover, moverTop: moverTop };
  }
  function pearson(a, b) { var n = Math.min(a.length, b.length); if (n < 5) return 0; var ma = 0, mb = 0, i; for (i = 0; i < n; i++) { ma += a[a.length - n + i]; mb += b[b.length - n + i]; } ma /= n; mb /= n; var sa = 0, sb = 0, sab = 0; for (i = 0; i < n; i++) { var da = a[a.length - n + i] - ma, db = b[b.length - n + i] - mb; sa += da * da; sb += db * db; sab += da * db; } return sab / (Math.sqrt(sa * sb) || 1e-9); }

  function num(x, d) { return x == null ? '—' : Number(x).toFixed(d == null ? 2 : d); }
  function render() {
    try {
      var host = document.getElementById('pooledRigorPlusPanel');
      if (!host) {
        // mount next to the EXISTING pooled panel (#rigorPanel) so the two pooled-rigor blocks sit together;
        // fall back through known-stable containers.
        var anchor = document.getElementById('rigorPanel') || document.getElementById('scanEdge') || document.getElementById('scanner') || document.querySelector('.chartcard');
        if (!anchor || !anchor.parentNode) return;
        host = document.createElement('div'); host.id = 'pooledRigorPlusPanel'; host.style.cssText = 'margin:8px 0;padding:9px 11px;border:1px solid var(--line,#222);border-radius:7px;background:var(--panel2,#111721)';
        anchor.parentNode.insertBefore(host, anchor.nextSibling);
      }
      var r = compute();
      if (!r) { host.innerHTML = '<div style="font-size:10px;color:var(--muted)"><b style="color:var(--gold)">POOLED RIGOR+</b> — load a basket (≥3 names, ≥80 bars) to compute selection-bias diagnostics.</div>'; return; }
      var psrCol = (r.psr != null && r.psr >= 0.9) ? '#2ecc8f' : (r.psr != null && r.psr >= 0.6 ? '#e0a13c' : '#ef5f4e');
      var pboCol = (r.pbo.pbo != null && r.pbo.pbo <= 0.25) ? '#2ecc8f' : (r.pbo.pbo != null && r.pbo.pbo <= 0.5 ? '#e0a13c' : '#ef5f4e');
      function row(lab, val, col, sub) { return '<div style="flex:1;min-width:120px;padding:5px 7px;border:1px solid var(--line);border-radius:6px"><div style="font-size:8px;letter-spacing:.4px;color:var(--muted);text-transform:uppercase">' + lab + '</div><div style="font-size:13px;font-weight:700;color:' + (col || 'var(--ink)') + '">' + val + '</div>' + (sub ? '<div style="font-size:8px;color:var(--muted)">' + sub + '</div>' : '') + '</div>'; }
      host.innerHTML = '<div style="font-size:10px;color:var(--muted);margin-bottom:5px"><b style="color:var(--gold)">POOLED RIGOR+</b> · selection-bias &amp; panel-dependence · ' + r.N + ' names · research only</div>'
        + '<div style="display:flex;gap:6px;flex-wrap:wrap">'
        + row('Effective breadth', num(r.effB, 1), (r.effB < r.N * 0.6 ? '#e0a13c' : 'var(--ink)'), 'of ' + r.N + ' names (independent bets)')
        + row('Composite Sharpe', num(r.sr, 2), 'var(--ink)', 'per-rebalance')
        + row('PSR', r.psr != null ? (r.psr * 100).toFixed(0) + '%' : '—', psrCol, 'P(true SR>0)')
        + row('MinTRL', r.mtrl != null ? Math.ceil(r.mtrl) : '—', 'var(--ink)', 'obs for 95% PSR')
        + row('PBO (CSCV)', r.pbo.pbo != null ? (r.pbo.pbo * 100).toFixed(0) + '%' : '—', pboCol, 'backtest-overfit prob')
        + row('Meta β / I²', num(r.meta.beta_re, 3) + ' / ' + (r.meta.I2 != null ? r.meta.I2.toFixed(0) + '%' : '—'), (r.meta.I2 > 60 ? '#e0a13c' : 'var(--ink)'), 'random-effects pooled')
        + row('Reality Check p', num(r.rc.p, 2), (r.rc.p != null && r.rc.p < 0.1 ? '#2ecc8f' : 'var(--muted)'), 'White data-snooping')
        + row('SPA p', num(r.spa.p, 2), (r.spa.p != null && r.spa.p < 0.1 ? '#2ecc8f' : 'var(--muted)'), 'Hansen data-snooping')
        + '</div>'
        + (r.moverTop ? '<div style="font-size:8px;color:var(--faint,#646e7c);margin-top:4px">top mover ' + r.moverTop.t + ': Δnet ' + num(r.mover.dnet, 3) + ' (momentum component)</div>' : '');
    } catch (e) {}
  }
  window.renderPooledRigorPlus = render;
  if (document.readyState !== 'loading') setTimeout(render, 2200); else document.addEventListener('DOMContentLoaded', function () { setTimeout(render, 2200); });
})();
