/* ===== MrktPrice — DATA-QUALITY badge (external) =====
   Surfaces the build's data-quality census (dataHealth.dataQuality: clean/degraded/reject + flagged
   tickers) and the real-rate curve source/validation, so skewed or stale pulls are visible to the
   operator rather than silently trusted. Self-contained; degrades silently; research only. */
(function () {
  'use strict';
  function go() {
    try {
      var d = (window.MMAP && window.MMAP.dataHealth) ? window.MMAP.dataHealth : null;
      if (d) return render(d, window.MMAP);
      fetch('marketmap.json', { cache: 'no-cache' })
        .then(function (r) { return r.json(); })
        .then(function (j) { render(j.dataHealth || {}, j); }).catch(function () {});
    } catch (e) {}
  }
  function render(dh, mm) {
    try {
      var dq = dh.dataQuality || null;
      var id = 'mrktDataQualityBadge', old = document.getElementById(id); if (old) old.remove();
      var host = document.querySelector('[data-coverage="universe"]') ||
        (function () { var els = document.querySelectorAll('div,section'); for (var i = 0; i < els.length; i++) { if (/DATA COVERAGE/i.test(els[i].textContent || '') && (els[i].children.length < 60)) return els[i]; } return null; })();
      var el = document.createElement('div'); el.id = id;
      var clean = dq ? (dq.clean || 0) : null, deg = dq ? (dq.degraded || 0) : 0, rej = dq ? (dq.reject || 0) : 0;
      var bad = (deg + rej) > 0;
      el.style.cssText = 'font:600 11px/1.4 system-ui,-apple-system,sans-serif;padding:6px 10px;margin:6px 0;border-radius:6px;'
        + (bad ? 'background:#2c2410;color:#e7c06a;border:1px solid #5c4a1e' : 'background:#0f221a;color:#7fd7a3;border:1px solid #1d3a2c');
      // real-rate curve credibility
      var rc = (mm && mm.realCurve) || null;
      var rcSrc = rc && rc.source ? rc.source : (dh.fmpKey ? 'pending (FRED/Treasury)' : '—');
      var parts = [];
      if (dq) parts.push((bad ? '⚠ ' : '● ') + 'Data quality: ' + clean + ' clean · ' + deg + ' degraded · ' + rej + ' rejected');
      else parts.push('● Data quality: census pending next build');
      if (dq && dq.flagged && dq.flagged.length) {
        parts.push('flagged: ' + dq.flagged.slice(0, 8).map(function (f) { return (f.t || '?') + '(' + (f.v || '') + ')'; }).join(', '));
      }
      parts.push('real-rate curve src: ' + rcSrc);
      el.textContent = parts.join(' · ');
      if (host && host.parentNode) host.parentNode.insertBefore(el, host); else if (document.body) document.body.insertBefore(el, document.body.firstChild);
    } catch (e) {}
  }
  if (document.readyState !== 'loading') go(); else document.addEventListener('DOMContentLoaded', go);
  if (typeof window.load === 'function') { var _o = window.load; window.load = function () { var r = _o.apply(this, arguments); setTimeout(go, 300); return r; }; }
})();
