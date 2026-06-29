/* event_panel.js — surfaces SEC-filing events (8-K/13D/13G/Form 3-4-5) + FMP health on the board.
   EXTERNAL module (same pattern as portfolio_panel.js / factor_neutral.js): reads window.MMAP.names[].ev
   (written nightly by event_board.py) and ./fmp_health.json (6-hourly probe). Injects (a) an "evt ±x%"
   chip per Bull/Bear row with a Considerations tooltip listing recent filings, and (b) an FMP-status badge
   at the top of the board. No surgery in the monolith. Research only, not advice. */
(function () {
  'use strict';
  var EVB = 'bbev', FMPB = 'bbfmp';

  function fmtForm(e) {
    var f = e.form, it = (e.items && e.items.length) ? ' ' + e.items.join('/') : '';
    var icon = f === '8-K' ? '◆' : (f.indexOf('13D') >= 0 ? '▲' : f.indexOf('13G') >= 0 ? '▣' : '●');
    return icon + ' ' + e.date + '  ' + f + it + (e.sev != null ? ' (sev ' + e.sev.toFixed(2) + ')' : '');
  }

  function evFor(tk) {
    try {
      var m = window.MMAP && window.MMAP.names; if (!m || !tk) return null;
      tk = tk.toUpperCase();
      for (var i = 0; i < m.length; i++) if ((m[i].t || '').toUpperCase() === tk && m[i].ev) return m[i].ev;
    } catch (e) {}
    return null;
  }

  function chips(board) {
    var rows = Array.prototype.slice.call(board.querySelectorAll('.bbrow'));
    rows.forEach(function (r) {
      var tk = r.getAttribute('data-tk'); if (!tk) return;
      var ev = evFor(tk); if (!ev || ev.tilt == null) return;
      var hd = r.querySelector('.bbhd'); if (!hd) return;
      var old = hd.querySelector('.' + EVB); if (old) old.parentNode.removeChild(old);
      if ((ev.n8k + ev.n13d + ev.n13g + ev.nins) === 0) return;
      var sp = document.createElement('span'); sp.className = EVB;
      var col = ev.tilt >= 0.15 ? '#2ecc8f' : ev.tilt <= -0.15 ? '#ef5f4e' : '#9aa7b4';
      sp.style.cssText = 'font-size:9px;font-weight:700;color:' + col + ';margin-left:6px;white-space:nowrap';
      var recent = (ev.events || []).slice(0, 6).map(fmtForm).join('\n');
      sp.title = 'SEC event tilt ' + (ev.tilt >= 0 ? '+' : '') + ev.tilt.toFixed(2) + '% — intensity ' + ev.intensity.toFixed(2)
        + ' · 8-K ' + ev.n8k + ' · 13D ' + ev.n13d + ' · 13G ' + ev.n13g + ' · insider ' + ev.nins
        + ' · stake ' + ev.stake + ' · insiderNet ' + ev.netIns
        + (recent ? ('\n— recent filings —\n' + recent) : '') + '\nResearch only, not advice.';
      sp.textContent = 'evt ' + (ev.tilt >= 0 ? '+' : '') + ev.tilt.toFixed(1) + '%';
      hd.appendChild(sp);
    });
  }

  var _fmp = null, _fmpTried = false;
  function fmpBadge(board) {
    var col = { ok: '#2ecc8f', degraded: '#d8b24a', down: '#ef5f4e', no_key: '#69727f' };
    function paint() {
      if (!_fmp) return;
      var head = board.querySelector('.bbcol .bbh') || board;
      var host = board.querySelector('#' + FMPB);
      if (!host) { host = document.createElement('div'); host.id = FMPB;
        host.style.cssText = 'font-size:9px;padding:2px 7px;color:#9aa7b4;border-top:1px solid var(--line)';
        board.insertBefore(host, board.firstChild); }
      var c = col[_fmp.overall] || '#69727f';
      var det = (_fmp.endpoints || []).map(function (e) { return (e.ok ? '✓' : '✗') + ' ' + e.name + (e.ok ? '' : ' (' + e.reason + ')'); }).join('  ');
      host.innerHTML = 'FMP Ultimate: <b style="color:' + c + '">' + (_fmp.overall || '?').toUpperCase() + '</b>'
        + (_fmp.okCount != null ? ' ' + _fmp.okCount + '/' + _fmp.total : '') + ' <span style="color:#69727f" title="' + det + '">· hover for endpoints</span>';
    }
    if (_fmpTried) { paint(); return; }
    _fmpTried = true;
    try {
      fetch('fmp_health.json', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) { _fmp = j; paint(); }).catch(function () {});
    } catch (e) {}
  }

  var t = null, applying = false;
  function schedule() { clearTimeout(t); t = setTimeout(run, 120); }
  function run() {
    var b = document.getElementById('bullBearBoard'); if (!b || !b.querySelector('.bbcol')) return;
    applying = true;
    try { chips(b); fmpBadge(b); } catch (e) {}
    setTimeout(function () { applying = false; }, 0);
  }
  if (typeof document !== 'undefined') {
    if (document.readyState !== 'loading') schedule();
    else document.addEventListener('DOMContentLoaded', schedule);
    new MutationObserver(function (muts) {
      if (applying) return;
      for (var i = 0; i < muts.length; i++) { var tg = muts[i].target;
        if (tg && (tg.id === 'bullBearBoard' || (tg.closest && tg.closest('#bullBearBoard')))) { schedule(); return; } }
    }).observe(document.body, { childList: true, subtree: true });
  }
})();
