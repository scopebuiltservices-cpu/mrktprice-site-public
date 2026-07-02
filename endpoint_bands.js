/* endpoint_bands.js — draw the HORIZON-ENDPOINT prediction intervals from the server's per-name expA block
 * onto the price canvas, at the cone's terminal-horizon x. This is the additive "triple-band at the horizon"
 * comparison the MC/quantile cone (CUR.pj) does NOT show: the PARAMETRIC band (expA.band, solid bracket) beside
 * the DEPENDENCE-AWARE moving-block BOOTSTRAP band (expA.bandBoot, dashed bracket). Seeing them together is the
 * honest econometric design: a single point estimate is never enough — show the model band and the
 * distribution-free band side by side so disagreement (bootstrap wider => tail/dependence risk the parametric
 * band understates) is visible.
 *
 * PURE + HEADLESS-TESTABLE: draw(ctx, opts) takes a 2D-context-like object and a price->y mapping, so it is
 * verified by test_endpoint_bands.mjs against a MOCK context that records ops — no browser, no screenshot. This
 * directly resolves "can't verify the visual result from here": geometry is asserted, not eyeballed. */
(function () {
  'use strict';
  var C = { param: '#9ab4e0', boot: '#39b6ff', up: '#2ecc8f', dn: '#ef5f4e', ink: '#cfd8e3' };

  function _lo(b) { return b && (b.lo != null ? b.lo : b.low); }   // accept {lo,hi} or {low,high}
  function _hi(b) { return b && (b.hi != null ? b.hi : b.high); }

  /* opts = {x, yOf(price)->px, expA, x2 (optional bracket half-width px, default 6), label (bool)}.
     Returns {drawn, bootWider} for the caller/test; no-op (drawn:false) when expA/bands are absent. */
  function draw(ctx, opts) {
    if (!ctx || !opts || !opts.expA) return { drawn: false };
    var e = opts.expA, yOf = opts.yOf, x = opts.x, w = opts.x2 || 6;
    var pb = e.band, bb = e.bandBoot;
    var plo = _lo(pb), phi = _hi(pb), blo = _lo(bb), bhi = _hi(bb);
    var drewAny = false, bootWider = null;

    // parametric band: solid bracket slightly LEFT of the horizon x
    if (plo != null && phi != null && isFinite(plo) && isFinite(phi)) {
      var xp = x - w - 1, yl = yOf(plo), yh = yOf(phi);
      ctx.strokeStyle = C.param; ctx.lineWidth = 1.5; if (ctx.setLineDash) ctx.setLineDash([]);
      ctx.beginPath();
      ctx.moveTo(xp, yh); ctx.lineTo(xp + w, yh);          // top cap
      ctx.moveTo(xp + w / 2, yh); ctx.lineTo(xp + w / 2, yl); // stem
      ctx.moveTo(xp, yl); ctx.lineTo(xp + w, yl);          // bottom cap
      ctx.stroke();
      drewAny = true;
    }
    // dependence-aware bootstrap band: dashed bracket slightly RIGHT of the horizon x
    if (blo != null && bhi != null && isFinite(blo) && isFinite(bhi)) {
      var xb = x + 1, ybl = yOf(blo), ybh = yOf(bhi);
      ctx.strokeStyle = C.boot; ctx.lineWidth = 1.5; if (ctx.setLineDash) ctx.setLineDash([3, 2]);
      ctx.beginPath();
      ctx.moveTo(xb, ybh); ctx.lineTo(xb + w, ybh);
      ctx.moveTo(xb + w / 2, ybh); ctx.lineTo(xb + w / 2, ybl);
      ctx.moveTo(xb, ybl); ctx.lineTo(xb + w, ybl);
      ctx.stroke();
      if (ctx.setLineDash) ctx.setLineDash([]);
      drewAny = true;
      if (plo != null && phi != null) bootWider = (bhi - blo) >= (phi - plo);
    }
    if (opts.label && drewAny && ctx.fillText) {
      ctx.fillStyle = C.ink; ctx.font = '8px sans-serif';
      ctx.fillText('band', x - w - 1, yOf(phi != null ? phi : bhi) - 3);
    }
    return { drawn: drewAny, bootWider: bootWider };
  }

  var API = { draw: draw };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  if (typeof window !== 'undefined') window.EndpointBands = API;
})();
