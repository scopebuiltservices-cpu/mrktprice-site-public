/* ===== MrktPrice — COMPOSITE deflated-Sharpe conviction scaler (external module) =====
   Reads the nightly composite DSR gate (dataHealth-adjacent fields the build now emits:
   convictionScale + compositeGate) and applies it to the Bull/Bear board: it sets the global
   window.MRKT_CONV_SCALE that the board multiplies into its conviction z (so HIGH->MED->LOW
   demote when the composite is over-searched or fails its deflated-Sharpe hurdle), and renders a
   compact banner that publishes the composite Sharpe, DSR, honest trial count, and the scale.
   Self-contained; degrades silently; research only. */
(function () {
  'use strict';
  function pct(x) { return (x == null) ? '—' : (Math.round(x * 100) + '%'); }
  function num(x, d) { return (x == null) ? '—' : Number(x).toFixed(d == null ? 2 : d); }

  function apply(scale, cg) {
    try {
      window.MRKT_CONV_SCALE = (scale == null ? 1 : Math.max(0, Math.min(1, scale)));
      // re-render the board if its builder is exposed (board multiplies the global into conviction z)
      if (typeof window.buildBullBearBoard === 'function') { try { window.buildBullBearBoard(); } catch (e) {} }
      banner(window.MRKT_CONV_SCALE, cg);
    } catch (e) {}
  }

  function banner(scale, cg) {
    try {
      var id = 'mrktConvScaleBanner', old = document.getElementById(id); if (old) old.remove();
      var host = document.querySelector('[data-board="bullbear"]') ||
                 (function () { // fall back to inserting just above the BULL/BEAR header text
                    var els = document.querySelectorAll('div,section'); for (var i = 0; i < els.length; i++) {
                      if (/BULL\s*\/\s*BEAR/i.test(els[i].textContent || '') && els[i].children.length < 40) return els[i];
                    } return null; })();
      var el = document.createElement('div'); el.id = id;
      var weak = scale < 0.999;
      el.style.cssText = 'font:600 11px/1.4 system-ui,-apple-system,sans-serif;padding:6px 10px;margin:6px 0;border-radius:6px;'
        + (weak ? 'background:#2c2410;color:#e7c06a;border:1px solid #5c4a1e' : 'background:#0f221a;color:#7fd7a3;border:1px solid #1d3a2c');
      var msg;
      if (cg && cg.compositeSharpe != null) {
        msg = (weak ? '⚠ ' : '● ') + 'Composite gate: Sharpe ' + num(cg.compositeSharpe, 2)
            + ' · deflated-Sharpe ' + pct(cg.dsr) + ' (hurdle ' + pct(cg.dsrHurdle || 0.95) + ')'
            + ' · honest trials ' + (cg.nTrials != null ? cg.nTrials : '—')
            + ' · conviction ×' + num(scale, 2)
            + (weak ? ' — tiers degraded (over-searched / below hurdle)' : ' — composite passes; full conviction');
      } else {
        msg = '● Composite gate: priors mode (factor-IC history maturing) · conviction ×' + num(scale, 2)
            + ' — fitted deflated-Sharpe gate activates once the IC history matures';
      }
      el.appendChild(document.createTextNode(msg));
      if (host && host.parentNode) host.parentNode.insertBefore(el, host);
      else if (document.body) document.body.insertBefore(el, document.body.firstChild);
    } catch (e) {}
  }

  function read(d) {
    var cs = (d && d.convictionScale != null) ? d.convictionScale
           : (d && d.compositeGate && d.compositeGate.convictionScale != null) ? d.compositeGate.convictionScale
           : (typeof d === 'object' && d && d.factorMode === 'priors') ? 0.6 : 1;
    apply(cs, d && d.compositeGate);
  }

  function go() {
    try { if (window.MMAP && (window.MMAP.convictionScale != null || window.MMAP.compositeGate)) { read(window.MMAP); return; } } catch (e) {}
    try { fetch('marketmap.json', { cache: 'no-cache' }).then(function (r) { return r.json(); }).then(read).catch(function () {}); } catch (e) {}
  }

  if (document.readyState !== 'loading') go(); else document.addEventListener('DOMContentLoaded', go);
  // re-apply after the main loader swaps MMAP in
  if (typeof window.load === 'function') { var _o = window.load; window.load = function () { var r = _o.apply(this, arguments); setTimeout(go, 250); return r; }; }
})();
