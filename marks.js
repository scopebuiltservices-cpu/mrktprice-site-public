/* marks.js — ECONOMETRICIAN MARKS: pure SVG-string builders for the chart's annotation vocabulary.
 * Each mark is backed by a verified engine field (conformal cone, dependence-aware bootstrap band,
 * simultaneous sup-t band, expected-peak/MFE-MAE from path_projection, calibration e-process). No DOM,
 * no side effects — every function returns an SVG fragment string given data + a pixel scale, so it is
 * unit-testable in isolation and drawn as one <svg> overlay above the (canvas) price pane. This keeps the
 * mark logic OUT of terminal.html (de-monolith) and parity/property-testable like the other engines.
 *
 * DISCIPLINE (Visualization-as-Econometric-Design): no band without its uncertainty, no verdict without
 * its significance, and the chart reports its OWN calibration. Tier 1 here: triple-band cone + calibration
 * chip + expected-peak node. Tier 2/3 marks (breaks, regime ribbon, OU line, CAR windows) extend this file. */
(function () {
  'use strict';
  var C = { acc: '#39b6ff', up: '#2ecc8f', dn: '#ef5f4e', warn: '#e0c14a', muted: '#8a93a0', line: '#2a2f3a', ink: '#eef3f8' };

  function _sc(lo, hi, yTop, yBot) {                       // value -> y px (high value = small y)
    var span = (hi - lo) || 1;
    return function (v) { return yBot - (v - lo) / span * (yBot - yTop); };
  }
  function _pts(xs, vals, y) {                              // "x,y x,y ..." for polyline/polygon
    var s = [], i; for (i = 0; i < xs.length; i++) { if (vals[i] == null) continue; s.push(xs[i].toFixed(1) + ',' + y(vals[i]).toFixed(1)); }
    return s.join(' ');
  }

  /* Triple-band projection cone. o = {xs:[px...], conf:{up,lo}, boot:{up,lo}, supt:{up,lo}, median:[],
   * priceLo, priceHi, yTop, yBot, anchorX, anchorY}. Bands are PRICE arrays aligned to xs. Returns
   * {svg, half:{conf,boot,supt}} where half.* is the half-width (px) at the far end for nesting checks. */
  function coneBands(o) {
    var y = _sc(o.priceLo, o.priceHi, o.yTop, o.yBot), s = '', last = o.xs.length - 1;
    function band(b, cls, dash, w, op) {
      if (!b || !b.up || !b.lo) return;
      s += '<polyline points="' + _pts(o.xs, b.up, y) + '" fill="none" stroke="' + cls + '" stroke-width="' + w + '"' + (dash ? ' stroke-dasharray="' + dash + '"' : '') + ' opacity="' + op + '"/>'
         + '<polyline points="' + _pts(o.xs, b.lo, y) + '" fill="none" stroke="' + cls + '" stroke-width="' + w + '"' + (dash ? ' stroke-dasharray="' + dash + '"' : '') + ' opacity="' + op + '"/>';
    }
    // conformal (pointwise) as a shaded fan (up forward + lo reversed)
    if (o.conf && o.conf.up && o.conf.lo) {
      var upP = _pts(o.xs, o.conf.up, y), loArr = [], xr = [], i;
      for (i = o.xs.length - 1; i >= 0; i--) { loArr.push(o.conf.lo[i]); xr.push(o.xs[i]); }
      s += '<polygon points="' + upP + ' ' + _pts(xr, loArr, y) + '" fill="' + C.acc + '" fill-opacity="0.16" stroke="none"/>';
    }
    band(o.supt, C.muted, '1,4', 1, 0.8);                  // simultaneous / pathwise — dotted, widest
    band(o.boot, C.acc, '4,3', 1, 0.75);                   // dependence-aware bootstrap — dashed
    if (o.median) s += '<polyline points="' + _pts(o.xs, o.median, y) + '" fill="none" stroke="' + C.acc + '" stroke-width="1.5"/>';
    function hw(b) { return (b && b.up && b.lo && b.up[last] != null) ? Math.abs(y(b.lo[last]) - y(b.up[last])) / 2 : 0; }
    return { svg: s, half: { conf: hw(o.conf), boot: hw(o.boot), supt: hw(o.supt) } };
  }

  /* Calibration e-process chip — the meta-mark: the chart declares whether its own bands are trustworthy.
   * ce = eprocess.conformal_eprocess output {level, eMax, pAnytime}. o = {x,y,w,h}. */
  function calibChip(ce, o) {
    o = o || {}; var x = o.x || 0, yy = o.y || 0, w = o.w || 150, h = o.h || 24;
    var lvl = (ce && ce.level) || 'ok';
    var col = lvl === 'kill' ? C.dn : (lvl === 'warn' ? C.warn : C.up);
    var tag = lvl === 'kill' ? 'CALIB FAIL' : (lvl === 'warn' ? 'CALIB DRIFT' : 'CALIB ✓');
    var e = ce && ce.eMax != null ? (' e=' + (Math.round(ce.eMax * 10) / 10)) : '';
    var p = ce && ce.pAnytime != null ? (' p≤' + ce.pAnytime) : '';
    return '<g><rect x="' + x + '" y="' + yy + '" width="' + w + '" height="' + h + '" rx="' + (h / 2) + '" fill="' + col + '" fill-opacity="0.14"/>'
      + '<circle cx="' + (x + 12) + '" cy="' + (yy + h / 2) + '" r="4" fill="' + col + '"/>'
      + '<text x="' + (x + 22) + '" y="' + (yy + h / 2 + 4) + '" font-size="11" font-weight="500" fill="' + col + '">' + tag + e + p + '</text></g>';
  }

  /* Expected-peak node + MFE/MAE excursion whiskers + days-to-peak. o = {x, priceLo,priceHi,yTop,yBot,
   * peak, mfe, mae, ttpLabel}. peak/mfe/mae are PRICES (mfe above, mae below expected path). */
  function peakNode(o) {
    var y = _sc(o.priceLo, o.priceHi, o.yTop, o.yBot), x = o.x, py = y(o.peak);
    var s = '';
    if (o.mfe != null) s += '<line x1="' + x + '" y1="' + y(o.mfe).toFixed(1) + '" x2="' + x + '" y2="' + py.toFixed(1) + '" stroke="' + C.up + '" stroke-width="1"/>'
      + '<line x1="' + (x - 4) + '" y1="' + y(o.mfe).toFixed(1) + '" x2="' + (x + 4) + '" y2="' + y(o.mfe).toFixed(1) + '" stroke="' + C.up + '" stroke-width="1.5"/>';
    if (o.mae != null) s += '<line x1="' + x + '" y1="' + py.toFixed(1) + '" x2="' + x + '" y2="' + y(o.mae).toFixed(1) + '" stroke="' + C.dn + '" stroke-width="1"/>'
      + '<line x1="' + (x - 4) + '" y1="' + y(o.mae).toFixed(1) + '" x2="' + (x + 4) + '" y2="' + y(o.mae).toFixed(1) + '" stroke="' + C.dn + '" stroke-width="1.5"/>';
    s += '<rect x="' + (x - 5) + '" y="' + (py - 5).toFixed(1) + '" width="10" height="10" transform="rotate(45 ' + x + ' ' + py.toFixed(1) + ')" fill="' + C.acc + '"/>';
    if (o.ttpLabel) s += '<text x="' + (x + 8) + '" y="' + (py + 3).toFixed(1) + '" font-size="10" fill="' + C.muted + '">' + o.ttpLabel + '</text>';
    return s;
  }

  /* Persist/fade verdict glyph with Chow-Denning significance star. vp = {vrStar, pJoint}. */
  function verdictGlyph(vp, o) {
    o = o || {}; var x = o.x || 0, yy = o.y || 0;
    if (!vp) return '';
    var sig = vp.pJoint != null && vp.pJoint <= 0.10;
    var lab = sig ? (vp.vrStar > 1 ? '↑ PERSIST' : '↓ FADE') : '~ RW';
    var col = sig ? (vp.vrStar > 1 ? C.up : C.dn) : C.warn;
    return '<text x="' + x + '" y="' + yy + '" font-size="11" font-weight="500" fill="' + col + '" text-anchor="end">' + lab + (sig ? ' ✱' : '') + '</text>';
  }

  /* ---- Tier 2 marks ------------------------------------------------------------------------------- */

  /* Structural-break verticals (Bai-Perron / PELT / ICSS). o = {breaks:[{x, label, kind}], yTop, yBot}.
     kind: 'mean' (Bai-Perron/PELT level shift) => amber; 'var' (ICSS variance shift) => accent. Dashed so
     they never read as price levels. Backed by the server break detectors. */
  function breakLines(o) {
    if (!o || !o.breaks || !o.breaks.length) return '';
    var s = '', yTop = o.yTop, yBot = o.yBot;
    o.breaks.forEach(function (b) {
      if (b.x == null) return;
      var col = b.kind === 'var' ? C.acc : C.warn;
      s += '<line x1="' + b.x + '" y1="' + yTop + '" x2="' + b.x + '" y2="' + yBot + '" stroke="' + col + '" stroke-width="1" stroke-dasharray="2,3" opacity="0.7"/>';
      if (b.label) s += '<text x="' + (b.x + 3) + '" y="' + (yTop + 10) + '" font-size="9" fill="' + col + '">' + b.label + '</text>';
    });
    return s;
  }

  /* Regime ribbon — a thin band along the top encoding the HMM/ICSS state over time. o = {segments:[{x0,x1,
     state}], y, h}. state 0=calm(up-green), 1=stressed(danger), 2=transition(amber); unknown=muted. */
  function regimeRibbon(o) {
    if (!o || !o.segments || !o.segments.length) return '';
    var y = o.y || 0, h = o.h || 6, pal = [C.up, C.dn, C.warn], s = '';
    o.segments.forEach(function (g) {
      if (g.x0 == null || g.x1 == null) return;
      var col = (g.state != null && pal[g.state]) ? pal[g.state] : C.muted;
      s += '<rect x="' + g.x0 + '" y="' + y + '" width="' + Math.max(0, g.x1 - g.x0) + '" height="' + h + '" fill="' + col + '" fill-opacity="0.55"/>';
    });
    return s;
  }

  /* OU equilibrium line + ±σ mean-reversion zone + half-life label. o = {mu, sigma, priceLo, priceHi,
     yTop, yBot, x0, x1, halfLifeLabel}. The band is where the process is "pulled back"; the line is θ-fit μ. */
  function ouLine(o) {
    if (!o || o.mu == null) return '';
    var y = _sc(o.priceLo, o.priceHi, o.yTop, o.yBot), ym = y(o.mu), s = '';
    if (o.sigma != null) {
      var yhi = y(o.mu + o.sigma), ylo = y(o.mu - o.sigma);
      s += '<rect x="' + o.x0 + '" y="' + Math.min(yhi, ylo).toFixed(1) + '" width="' + Math.max(0, o.x1 - o.x0) + '" height="' + Math.abs(ylo - yhi).toFixed(1) + '" fill="' + C.acc + '" fill-opacity="0.08"/>';
    }
    s += '<line x1="' + o.x0 + '" y1="' + ym.toFixed(1) + '" x2="' + o.x1 + '" y2="' + ym.toFixed(1) + '" stroke="' + C.acc + '" stroke-width="1" stroke-dasharray="6,4"/>';
    s += '<text x="' + o.x0 + '" y="' + (ym - 4).toFixed(1) + '" font-size="9" fill="' + C.acc + '">OU μ' + (o.halfLifeLabel ? ' · t½ ' + o.halfLifeLabel : '') + '</text>';
    return s;
  }

  /* Event CAR window shading — cumulative abnormal return around an event. o = {x0, x1, yTop, yBot, car}.
     car>0 => green wash (positive drift), car<0 => red. Backed by event_engine CAR. */
  function carShade(o) {
    if (!o || o.x0 == null || o.x1 == null) return '';
    var col = (o.car || 0) >= 0 ? C.up : C.dn;
    return '<rect x="' + o.x0 + '" y="' + o.yTop + '" width="' + Math.max(0, o.x1 - o.x0) + '" height="' + (o.yBot - o.yTop) + '" fill="' + col + '" fill-opacity="0.06"/>';
  }

  var API = { coneBands: coneBands, calibChip: calibChip, peakNode: peakNode, verdictGlyph: verdictGlyph,
              breakLines: breakLines, regimeRibbon: regimeRibbon, ouLine: ouLine, carShade: carShade };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  if (typeof window !== 'undefined') window.MrktMarks = API;
})();
