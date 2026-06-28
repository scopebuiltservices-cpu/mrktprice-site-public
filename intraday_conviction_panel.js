/* ===== MrktPrice — INTRADAY CONVICTION panel (external; renders the published-cutoff audit row) =====
   Derives the conviction metrics from the live 15-min buffer (mrkt.intra.<sym>.<today>) + the EOD
   outlook, then calls window.MrktIntradayConviction.evaluate() and prints the row literally, e.g.:
     RVOL 2.34≥2.00 | z +2.41σ≥2.00 | VWAP reclaim YES | OBV slope t=+2.27≥2.00
   showing the current value AND the active cutoff for every gate. Research only — not advice. */
(function () {
  'use strict';
  function today() { return new Date().toISOString().slice(0, 10); }
  function buf(sym) { try { return JSON.parse(localStorage.getItem('mrkt.intra.' + sym + '.' + today()) || '[]'); } catch (e) { return []; } }
  function panel() {
    var p = document.getElementById('intradayConvictionPanel');
    if (!p) {
      p = document.createElement('div'); p.id = 'intradayConvictionPanel'; p.style.marginTop = '6px';
      var host = document.getElementById('intradayEodPanel') || document.getElementById('intradayProjPanel');
      if (host && host.parentNode) host.parentNode.insertBefore(p, host.nextSibling); else return null;
    }
    return p;
  }
  function std(a) { if (a.length < 2) return 0; var m = a.reduce(function (x, y) { return x + y; }, 0) / a.length; return Math.sqrt(a.reduce(function (s, x) { return s + (x - m) * (x - m); }, 0) / (a.length - 1)); }

  function render() {
    try {
      var IC = window.MrktIntradayConviction, EOD = window.MrktIntradayEOD;
      if (!IC || !EOD || typeof CUR !== 'object' || !CUR || !CUR.sym) return;
      var p = panel(); if (!p) return;
      var sym = (CUR.sym || '').toUpperCase(), b = buf(sym);
      if (b.length < 4) { p.innerHTML = '<div class="note" style="font-size:10px"><b style="color:var(--gold)">INTRADAY CONVICTION</b> — warming up (need ≥4 fifteen-minute bars; market hours).</div>'; return; }
      var bars = b.map(function (rec, i) { var pr = (rec.price > 0 ? rec.price : 1); return { bucket: i, ret: (rec.r || 0), vol: (rec.rvol > 0 ? rec.rvol : 1), price: pr, p: Math.log(pr) }; });
      var o = EOD.eodOutlook(bars, { avgDailyVol: 26, openPx: bars[0].price, totalBuckets: 26 });
      if (!o) { p.innerHTML = ''; return; }
      // build OBV series + price-vs-VWAP residual sigma (a same-session proxy for σ_tod)
      var obv = [0], resid = [];
      for (var i = 0; i < bars.length; i++) {
        var sgn = i === 0 ? 0 : (bars[i].price > bars[i - 1].price ? 1 : (bars[i].price < bars[i - 1].price ? -1 : 0));
        obv.push(obv[obv.length - 1] + sgn * bars[i].vol);
        resid.push(bars[i].price - o.vwap);
      }
      var sigTod = std(resid) || (o.vwap * 0.001);
      var priceNow = o.priceNow, vwap = o.vwap;
      var prevAboveVwap = bars.length >= 2 ? (bars[bars.length - 2].price >= vwap) : false;
      var metrics = {
        rvol: (o.volPace != null ? o.volPace : o.projRVOL),
        z: IC.sigmaTodDisplacement(priceNow, vwap, sigTod),
        vwap_reclaim: priceNow >= vwap,                          // above VWAP now
        obv_t: IC.obvSlopeT(obv, 8)
      };
      var side = priceNow >= vwap ? 'long' : 'short';
      // a true reclaim/loss requires the prior bar on the other side; pass that nuance through
      if (side === 'long') metrics.vwap_reclaim = priceNow >= vwap;     // long gate wants above
      else metrics.vwap_reclaim = priceNow >= vwap;                     // short gate inverts internally (wants below)
      var r = IC.evaluate(metrics, (window.MMAP && window.MMAP.triggerCutoffs) || null, side);
      var col = r.flip ? (side === 'long' ? '#2ecc8f' : '#ef5f4e') : 'var(--muted)';
      var verdict = r.flip ? (side === 'long' ? 'LONG conviction FLIP' : 'SHORT conviction FLIP') : 'no flip — gate not met';
      p.innerHTML = '<div style="font-size:10px;color:var(--muted);margin:4px 0"><b style="color:var(--gold)">INTRADAY CONVICTION</b> · '
        + o.elapsed + ' bars · <b style="color:' + col + '">' + verdict + '</b> · research only</div>'
        + '<div style="font:600 11px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--panel2,#111721);border:1px solid var(--line);border-radius:6px;padding:7px 9px;color:var(--ink)">'
        + r.row.replace(/\|/g, '<span style="color:var(--faint,#646e7c)"> | </span>') + '</div>'
        + '<div style="font-size:8px;color:var(--faint,#646e7c);margin-top:3px">σ_tod from same-session price–VWAP residuals · RVOL = session volume pace · cutoffs are literature defaults until walk-forward fitted from your trigger history.</div>';
    } catch (e) {}
  }
  if (document.readyState !== 'loading') setTimeout(render, 1700); else document.addEventListener('DOMContentLoaded', function () { setTimeout(render, 1700); });
  setInterval(render, 20000);
  window.renderIntradayConviction = render;
})();
