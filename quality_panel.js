/* ===== MrktPrice — per-ticker DATA-QUALITY / DRIFT panel (external) =====
   For the loaded ticker, surfaces the build's honesty layer: data-quality verdict, run-over-run + in-sample
   return-distribution drift (PSI/KS), cross-source agreement (FMP vs yfinance), real-rate duration class,
   and the nearest high-impact macro event (event-aware context). Reads window.MMAP. Research only. */
(function () {
  'use strict';
  function nodeFor(sym) {
    try {
      var M = window.MMAP; if (!M || !sym) return null; sym = sym.toUpperCase();
      if (M.names && M.names.length) { for (var i = 0; i < M.names.length; i++) { if (M.names[i] && (M.names[i].t || '').toUpperCase() === sym) return M.names[i]; } }
      if (M[sym] && M[sym].t) return M[sym];
    } catch (e) {} return null;
  }
  function chip(label, val, col) {
    return '<span style="display:inline-flex;gap:4px;align-items:center;border:1px solid ' + (col || 'var(--line,#222)') + '55;border-radius:5px;padding:2px 7px;margin:2px 4px 2px 0;font-size:10px">'
      + '<b style="color:var(--faint,#646e7c);font-weight:600;text-transform:uppercase;letter-spacing:.3px">' + label + '</b> <span style="color:' + (col || 'var(--ink,#eef3f8)') + '">' + val + '</span></span>';
  }
  function lvlColor(l) { return l === 'significant' ? '#ef5f4e' : l === 'moderate' ? '#e0a13c' : l === 'stable' ? '#2ecc8f' : 'var(--muted,#8a93a3)'; }
  function dqColor(v) { return v === 'reject' ? '#ef5f4e' : v === 'degraded' ? '#e0a13c' : v === 'clean' ? '#2ecc8f' : 'var(--muted,#8a93a3)'; }

  function render() {
    try {
      if (typeof CUR !== 'object' || !CUR || !CUR.sym) return;
      var sym = (CUR.sym || '').toUpperCase(), n = nodeFor(sym);
      var host = document.getElementById('qualityPanel');
      if (!host) {
        host = document.createElement('div'); host.id = 'qualityPanel'; host.style.marginTop = '6px';
        var anchor = document.getElementById('ptCoverage') || document.getElementById('readout') || document.querySelector('.chartcard');
        if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(host, anchor.nextSibling); else return;
      }
      if (!n) { host.innerHTML = '<div class="note" style="font-size:10px"><b style="color:var(--gold)">DATA QUALITY · ' + sym + '</b> — no universe node (load a covered ticker).</div>'; return; }
      var parts = [];
      // data-quality verdict
      if (n.dq) parts.push(chip('quality', n.dq, dqColor(n.dq)));
      // drift (run-over-run + in-sample)
      var d = n.drift || null;
      if (d) {
        if (d.level && d.level !== 'baseline' && d.level !== 'insufficient')
          parts.push(chip('drift', d.level + (d.psi != null ? ' · PSI ' + Number(d.psi).toFixed(2) : ''), lvlColor(d.level)));
        else if (d.level === 'baseline') parts.push(chip('drift', 'baseline set', 'var(--muted,#8a93a3)'));
        var ins = d.inSample;
        if (ins && ins.level && ins.level !== 'insufficient') parts.push(chip('in-sample', ins.level, lvlColor(ins.level)));
      }
      // cross-source agreement
      if (n.xsrc && n.xsrc.agree != null)
        parts.push(chip('FMP vs yf', (n.xsrc.agree ? 'agree' : 'DISAGREE') + (n.xsrc.dev != null ? ' (' + (n.xsrc.dev * 100).toFixed(2) + '%)' : ''), n.xsrc.agree ? '#2ecc8f' : '#ef5f4e'));
      // real-rate duration class
      if (n.rate && n.rate.class) parts.push(chip('rate', n.rate.class.split(' (')[0], '#9ab4e0'));
      // nearest high-impact macro event (event-aware)
      try {
        var ev = window.MMAP && window.MMAP.events;
        if (ev && ev.nextHighImpact) {
          var dn = ev.daysToNext, col = (dn != null && dn <= 2) ? '#e0a13c' : 'var(--muted,#8a93a3)';
          parts.push(chip('next macro', ev.nextHighImpact.event + (dn != null ? ' · ' + dn + 'd' : ''), col));
        }
      } catch (e) {}
      if (!parts.length) parts.push('<span style="font-size:10px;color:var(--muted)">no quality flags — series clean, no drift</span>');
      host.innerHTML = '<div style="font-size:8px;color:var(--muted);text-transform:uppercase;letter-spacing:.3px;margin-bottom:3px">data quality &amp; drift · ' + sym + '</div>'
        + '<div style="display:flex;flex-wrap:wrap;align-items:center">' + parts.join('') + '</div>';
    } catch (e) {}
  }
  window.renderQualityPanel = render;
  if (document.readyState !== 'loading') setTimeout(render, 1600); else document.addEventListener('DOMContentLoaded', function () { setTimeout(render, 1600); });
  setInterval(render, 20000);
  if (typeof window.load === 'function') { var _l = window.load; window.load = function () { var r = _l.apply(this, arguments); setTimeout(render, 140); return r; }; }
})();
