/* factor_neutral.js — overlays a FACTOR-NEUTRAL alpha on the Bull/Bear board, netting out the
   Fama-French factor-explained return (n.fac.expPct, written nightly by residualize_board.py) from each
   row's displayed alpha. EXTERNAL module (same pattern as portfolio_panel.js): reads each .bbrow's
   data-tk + data-adj/data-tot, looks up window.MMAP.names for the per-name fac block, and injects an
   "fnα X.X%" chip + tooltip with the 6 betas. No surgery in the monolith. Research only, not advice. */
(function () {
  'use strict';
  var BADGE = 'bbfn', FACT = ['MktRF', 'SMB', 'HML', 'RMW', 'CMA', 'Mom'];

  function num(s) { var v = parseFloat(s); return (v === v) ? v : null; }

  function facFor(tk) {
    try {
      var m = window.MMAP && window.MMAP.names;
      if (!m || !tk) return null;
      tk = tk.toUpperCase();
      for (var i = 0; i < m.length; i++) if ((m[i].t || '').toUpperCase() === tk && m[i].fac) return m[i].fac;
    } catch (e) {}
    return null;
  }

  function compute(board) {
    var rows = Array.prototype.slice.call(board.querySelectorAll('.bbrow'));
    rows.forEach(function (r) {
      var tk = r.getAttribute('data-tk'); if (!tk) return;
      var fac = facFor(tk); if (!fac || fac.expPct == null) return;
      // displayed alpha: EB-adjusted if present, else raw total
      var base = num(r.getAttribute('data-adj')); if (base == null) base = num(r.getAttribute('data-tot'));
      if (base == null) return;
      var fn = base - fac.expPct;                  // factor-neutral expected return (%)
      var hd = r.querySelector('.bbhd'); if (!hd) return;
      var old = hd.querySelector('.' + BADGE); if (old) old.parentNode.removeChild(old);
      var sp = document.createElement('span'); sp.className = BADGE;
      var col = fn >= 0 ? '#2ecc8f' : '#ef5f4e';
      sp.style.cssText = 'font-size:9px;font-weight:700;color:' + col + ';margin-left:6px;white-space:nowrap';
      var betas = FACT.map(function (f) { return f + ' ' + (fac.b && fac.b[f] != null ? fac.b[f].toFixed(2) : '?'); }).join(', ');
      sp.title = 'factor-neutral alpha = displayed alpha (' + base.toFixed(1) + '%) − FF factor-explained return ('
        + (fac.expPct >= 0 ? '+' : '') + fac.expPct.toFixed(1) + '%). Betas: ' + betas + ' · R²=' + (fac.r2 != null ? fac.r2.toFixed(2) : '?')
        + ' · n=' + (fac.n || '?') + '. Strips compensated factor bets (market/size/value/profitability/investment/momentum). Research only.';
      sp.textContent = 'fnα ' + (fn >= 0 ? '+' : '') + fn.toFixed(1) + '%';
      hd.appendChild(sp);
    });
  }

  var t = null, applying = false;
  function schedule() { clearTimeout(t); t = setTimeout(run, 110); }
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
