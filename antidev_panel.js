/* antidev_panel.js — terminal-side consumer of the server ANTI-DEVIATION analytics (projlearn.json ->
   byHorizon[H].antiDeviation, produced by projledger.py + anti_deviation.py).

   Anti-deviation is a post-forecast control layer learned from NO-LOOKAHEAD matured forecasts across the
   whole universe: it corrects the projection cone for systematic CENTER bias, SCALE (under/over-coverage),
   and TAIL asymmetry, but only when statistically gated (Geyer-ESS sufficiency + an out-of-sample
   interval-score benefit). This module:
     - loads the analytics once (cached),
     - exposes MrktAntiDev.on() (a user on/off toggle, persisted),
     - MrktAntiDev.adjustProjection(pj,H,sigDaily) -> returns a CORRECTED copy of the cone projection
       (shift drift by the learned bias, scale + skew the 80/95 bands) when ON and the controller is active;
       a strict no-op otherwise (identity-preserving),
     - MrktAntiDev.render() -> a tile showing the deviation vs anti-deviation values WITH plain-English
       reasoning.
   Server-authoritative numbers; the browser only displays/applies them. */
(function () {
  "use strict";
  var LS_KEY = "mrkt.antidev.on";
  var ZBASE = 1.645;                 // the controller's studentized band reference (z for ~90%)
  var _data = null, _loading = null;

  function _lsOn() {
    try { var v = localStorage.getItem(LS_KEY); return v === null ? true : v === "1"; } catch (e) { return true; }
  }
  function _setOn(v) { try { localStorage.setItem(LS_KEY, v ? "1" : "0"); } catch (e) {} }

  function on() {
    var box = document.getElementById("antidevOn");
    if (box) return !!box.checked;
    return _lsOn();
  }

  function load(cb) {
    if (_data) { cb && cb(_data); return; }
    if (_loading) { _loading.push(cb); return; }
    _loading = [cb];
    fetch("projlearn.json", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (j) {
      _data = j || {}; var q = _loading; _loading = null; q.forEach(function (f) { f && f(_data); });
    }).catch(function () { _data = {}; var q = _loading; _loading = null; q.forEach(function (f) { f && f(_data); }); });
  }

  /* pick the controller for the cone horizon H: the nearest calibrated horizon (5/10/21). */
  function controllerFor(H) {
    if (!_data || !_data.byHorizon) return null;
    var hs = Object.keys(_data.byHorizon).map(Number).filter(function (x) { return x; });
    if (!hs.length) return null;
    var best = hs[0], bd = Math.abs(hs[0] - H);
    hs.forEach(function (h) { var d = Math.abs(h - H); if (d < bd) { bd = d; best = h; } });
    var rec = _data.byHorizon[String(best)] || {};
    var ad = rec.antiDeviation || null;
    if (ad) ad = Object.assign({ _H: best }, ad);
    return ad;
  }

  /* Apply the learned corrections to a cone projection object {path,p80,p95}. Returns a NEW object.
     - drift:   each price *= exp(biasAdj · t/H)  (bias accrues linearly to the calibrated horizon)
     - scale:   band log-half-widths *= scaleAdj
     - skew:    lower half-width *= |qLower|/ZBASE, upper *= qUpper/ZBASE  (asymmetry from the controller)
     Identity-preserving: biasAdj≈0, scaleAdj≈1, qLower≈-ZBASE, qUpper≈+ZBASE  ->  unchanged. */
  function adjustProjection(pj, H, sigDaily) {
    try {
      if (!pj || !on()) return pj;
      var ad = controllerFor(H);
      if (!ad || !ad.active) return pj;
      var bias = +ad.biasAdj || 0, scl = +ad.scaleAdj || 1;
      var qLo = (ad.qLower != null) ? +ad.qLower : -ZBASE, qHi = (ad.qUpper != null) ? +ad.qUpper : ZBASE;
      var skDn = Math.abs(qLo) / ZBASE, skUp = Math.abs(qHi) / ZBASE;
      var Hc = ad._H || H || 1;
      function shiftPrice(t, p) { return p * Math.exp(bias * Math.min(t, Hc) / Hc); }
      function band(arr) {
        return arr.map(function (b) {
          var pOld = _priceAt(pj.path, b.t);
          var pNew = shiftPrice(b.t, pOld);
          var loLR = Math.log(b.low / pOld), hiLR = Math.log(b.high / pOld);
          var loN = loLR * scl * skDn, hiN = hiLR * scl * skUp;
          return { t: b.t, low: pNew * Math.exp(loN), high: pNew * Math.exp(hiN) };
        });
      }
      var path = pj.path.map(function (p) { return { t: p.t, price: shiftPrice(p.t, p.price) }; });
      return Object.assign({}, pj, {
        path: path, p80: band(pj.p80 || []), p95: band(pj.p95 || []),
        antidev: { biasAdj: bias, scaleAdj: scl, qLower: qLo, qUpper: qHi, H: Hc }
      });
    } catch (e) { return pj; }
  }
  function _priceAt(path, t) { for (var i = 0; i < path.length; i++) if (path[i].t === t) return path[i].price; return path.length ? path[path.length - 1].price : 0; }

  function _pct(x, d) { return (x == null || isNaN(x)) ? "—" : ((x >= 0 ? "+" : "") + (x * 100).toFixed(d == null ? 2 : d) + "%"); }
  function _n(x, d) { return (x == null || isNaN(x)) ? "—" : (+x).toFixed(d == null ? 2 : d); }

  function _reason(ad, H) {
    if (!ad) return "No anti-deviation analytics for this horizon yet (run projledger).";
    if (!ad.active) {
      return "Anti-deviation GATED OFF for ~" + ad._H + "d — the correction is not statistically justified " +
        "(insufficient effective sample n_eff=" + _n(ad.nEff, 0) + ", or no out-of-sample interval-score benefit). " +
        "The cone is shown RAW; no edge is invented.";
    }
    var dir = ad.biasAdj > 0 ? "up" : (ad.biasAdj < 0 ? "down" : "flat");
    var wide = ad.scaleAdj > 1.02 ? ("widened ×" + _n(ad.scaleAdj)) : (ad.scaleAdj < 0.98 ? ("tightened ×" + _n(ad.scaleAdj)) : "kept width");
    var covTxt = (ad.coverageRaw != null && ad.coverageAdj != null)
      ? (" Historically the raw band covered " + Math.round(ad.coverageRaw * 100) + "% vs a " + Math.round((ad.target || 0.9) * 100) +
         "% target; after correction " + Math.round(ad.coverageAdj * 100) + "%.")
      : "";
    var skew = (ad.qUpper != null && ad.qLower != null && Math.abs(Math.abs(ad.qUpper) - Math.abs(ad.qLower)) > 0.15)
      ? (Math.abs(ad.qUpper) > Math.abs(ad.qLower) ? " Upside tail is fatter (asymmetric)." : " Downside tail is fatter (asymmetric).")
      : "";
    return "Anti-deviation ACTIVE for ~" + ad._H + "d: cone shifted " + dir + " by " + _pct(ad.biasAdj) +
      " and " + wide + " (learned from " + _n(ad.nRaw, 0) + " matured forecasts, n_eff=" + _n(ad.nEff, 0) + ")." +
      covTxt + skew;
  }

  function render() {
    var host = document.getElementById("antidevTile");
    if (!host) return;
    load(function () {
      var H = (typeof CUR === "object" && CUR && CUR.coneH) ? CUR.coneH : 10;
      var ad = controllerFor(H);
      var isOn = on();
      var head = '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">' +
        '<b style="font-size:12px">Anti-deviation</b>' +
        '<span class="pill ' + (!ad ? "n" : (ad.active ? (isOn ? "t" : "n") : "h")) + '">' +
        (!ad ? "no data" : (ad.active ? (isOn ? "ON · active" : "active (off)") : "gated off")) + '</span>' +
        '<span style="font-size:9px;color:var(--faint,#646e7c)">server-learned, no-lookahead</span></div>';
      var rows = "";
      if (ad) {
        function cell(k, v, sub) { return '<div class="tile" style="padding:7px 9px"><div class="k" style="font-size:10px;color:var(--muted,#8a93a0)">' + k + '</div><div class="v" style="font-size:15px;font-weight:600">' + v + (sub ? ' <span style="font-size:9px;color:var(--faint,#646e7c)">' + sub + '</span>' : '') + '</div></div>'; }
        rows = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:7px;margin-top:7px">' +
          cell("Center bias", _pct(ad.biasAdj), "drift shift") +
          cell("Scale", "×" + _n(ad.scaleAdj), "band width") +
          cell("Tails (lo/hi)", _n(ad.qLower) + " / " + _n(ad.qUpper), "σ-units") +
          cell("Coverage", (ad.coverageRaw != null ? Math.round(ad.coverageRaw * 100) + "%" : "—") + " → " + (ad.coverageAdj != null ? Math.round(ad.coverageAdj * 100) + "%" : "—"), "raw→adj") +
          cell("Evidence", _n(ad.nRaw, 0) + " obs", "n_eff " + _n(ad.nEff, 0)) +
          cell("OOS benefit", _n(ad.iscDelta), "interval-score Δ") +
          '</div>';
      }
      host.innerHTML = head + rows +
        '<div style="font-size:10px;color:var(--muted,#8a93a0);margin-top:7px;line-height:1.45">' + _reason(ad, H) + '</div>';
    });
  }

  window.MrktAntiDev = { on: on, setOn: _setOn, load: load, controllerFor: controllerFor, adjustProjection: adjustProjection, render: render, _reason: _reason };
  if (typeof module !== "undefined" && module.exports) module.exports = window.MrktAntiDev;   // node-testable
  if (typeof document !== "undefined" && document.addEventListener) {
    document.addEventListener("DOMContentLoaded", function () {
      var b = document.getElementById("antidevOn");
      if (b) { b.checked = _lsOn(); b.addEventListener("change", function () { _setOn(b.checked); try { render(); } catch (e) {} }); try { render(); } catch (e) {} }
    });
  }
})();
