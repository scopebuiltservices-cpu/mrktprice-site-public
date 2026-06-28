/* portfolio_panel.js — overlays a suggested long-only WEIGHT % on the Bull column, computed from the
   board's OWN rendered rows via window.MrktPort (mean-variance optimum on a single-factor risk model).
   EXTERNAL module by design: the weights math never touches the 776 KB terminal.html monolith — it reads
   data-* attributes off the rows and injects a badge, re-applying after each re-render via a guarded
   MutationObserver (same pattern as bullbear_controls.js). Node-checkable in isolation. Research only. */
(function () {
  'use strict';
  var SIGMA_M_DAILY = 1.10;   // ~17.5% annualized market vol as daily %; upgradeable to a measured value
  var W_MAX = 0.10, LAM = 1.0, BADGE = 'bbwt';

  function num(s) { var v = parseFloat(s); return (v === v) ? v : null; }

  function compute(board) {
    if (!window.MrktPort || !window.MrktPort.mvWeightsFactor) return;
    var bull = board.querySelector('.bbcol[data-side="bull"]');
    if (!bull) return;
    var rows = Array.prototype.slice.call(bull.querySelectorAll('.bbrow'));
    if (!rows.length) return;
    var picks = [];
    rows.forEach(function (r) {
      // mu = net-of-cost edge if present, else EB-adjusted total, else raw total. Long-only -> clamp >= 0.
      var mu = num(r.getAttribute('data-net'));
      if (mu == null) mu = num(r.getAttribute('data-adj'));
      if (mu == null) mu = num(r.getAttribute('data-tot'));
      var beta = num(r.getAttribute('data-beta')); if (beta == null) beta = 1.0;
      var volA = num(r.getAttribute('data-vol'));                       // annualized vol fraction
      var sIdio = (volA != null && volA > 0) ? (volA * 100) / Math.sqrt(252) : 1.5;  // daily % idio proxy
      picks.push({ r: r, mu: Math.max(0, mu == null ? 0 : mu), beta: beta, sidio: sIdio });
    });
    var mu = picks.map(function (p) { return p.mu; });
    var beta = picks.map(function (p) { return p.beta; });
    var sid = picks.map(function (p) { return p.sidio; });
    if (mu.every(function (x) { return x <= 0; })) return;             // no positive-edge bull -> nothing to size
    var w;
    try {
      var wr = window.MrktPort.mvWeightsFactor(mu, beta, SIGMA_M_DAILY, sid, LAM);
      w = window.MrktPort.projectLongOnly(wr, W_MAX, 1.0);             // 10% cap, fully invested
      // tiny-N / tight-cap fallback: if the cap makes full investment infeasible (few positive-edge
      // names), renormalize the achieved weights to sum to 1 so the displayed allocation is complete.
      var sw = w.reduce(function (a, b) { return a + b; }, 0);
      if (sw > 1e-9 && sw < 1 - 1e-6) w = w.map(function (x) { return x / sw; });
    } catch (e) { return; }
    picks.forEach(function (p, i) {
      var hd = p.r.querySelector('.bbhd'); if (!hd) return;
      var old = hd.querySelector('.' + BADGE); if (old) old.parentNode.removeChild(old);
      var sp = document.createElement('span'); sp.className = BADGE;
      sp.style.cssText = 'font-size:9px;font-weight:700;color:#d8b24a;margin-left:6px;white-space:nowrap';
      sp.title = 'suggested long-only weight — mean-variance optimizer (#7) on a single-factor risk model '
        + '(beta + per-name vol), ' + (W_MAX * 100) + '% position cap, fully invested. Research only, not advice.';
      sp.textContent = 'wt ' + (w[i] * 100).toFixed(1) + '%';
      hd.appendChild(sp);
    });
  }

  var t = null, applying = false;
  function schedule() { clearTimeout(t); t = setTimeout(run, 90); }
  function run() {
    var b = document.getElementById('bullBearBoard');
    if (!b || !b.querySelector('.bbcol')) return;
    applying = true;
    try { compute(b); } catch (e) {}
    setTimeout(function () { applying = false; }, 0);
  }
  if (typeof document !== 'undefined') {
    if (document.readyState !== 'loading') schedule();
    else document.addEventListener('DOMContentLoaded', schedule);
    new MutationObserver(function (muts) {
      if (applying) return;
      for (var i = 0; i < muts.length; i++) {
        var tg = muts[i].target;
        if (tg && (tg.id === 'bullBearBoard' || (tg.closest && tg.closest('#bullBearBoard')))) { schedule(); return; }
      }
    }).observe(document.body, { childList: true, subtree: true });
  }
})();
