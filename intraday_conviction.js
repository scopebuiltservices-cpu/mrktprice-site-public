/* ===== MrktPrice intraday CONVICTION engine (1:1 mirror of tools/market_map/intraday_conviction.py)
   Explicit FlipLong/FlipShort hard gate that PUBLISHES both the current value and the active cutoff for
   every metric, turning the board row into an audit trail. Exposes window.MrktIntradayConviction.
   Research only — not advice. */
(function (root) {
  'use strict';
  var DEFAULT_CUTOFFS = { rvol: 2.0, z: 2.0, obv_t: 2.0, mfi_hi: 80.0, mfi_lo: 20.0, atr: 1.0 };

  function sigmaTodDisplacement(price, vwap, sigmaTod) {
    if (sigmaTod == null || sigmaTod <= 0) return null;
    return (price - vwap) / sigmaTod;
  }
  function breakoutATR(price, breakoutLevel, atr) {
    if (atr == null || atr <= 0) return null;
    return (price - breakoutLevel) / atr;
  }
  function obvSlopeT(obv, win) {
    win = win || 8;
    var y = (obv || []).filter(function (v) { return v != null; }).map(Number);
    y = y.slice(-win); var n = y.length;
    if (n < 3) return null;
    var xs = []; for (var i = 0; i < n; i++) xs.push(i);
    var mx = xs.reduce(function (a, b) { return a + b; }, 0) / n;
    var my = y.reduce(function (a, b) { return a + b; }, 0) / n;
    var sxx = xs.reduce(function (a, x) { return a + (x - mx) * (x - mx); }, 0);
    if (sxx <= 0) return null;
    var sxy = 0; for (i = 0; i < n; i++) sxy += (xs[i] - mx) * (y[i] - my);
    var b = sxy / sxx;
    var sse = 0; for (i = 0; i < n; i++) { var yh = my + b * (xs[i] - mx); sse += (y[i] - yh) * (y[i] - yh); }
    if (n - 2 <= 0) return null;
    var s2 = sse / (n - 2);
    var se = (s2 > 0 && sxx > 0) ? Math.sqrt(s2 / sxx) : 0.0;
    if (se <= 0) return (s2 > 0) ? null : (b ? (b > 0 ? 99.0 : -99.0) : 0.0);
    return b / se;
  }
  function _passes(value, cutoff, side) {
    if (value == null) return false;
    return side === 'ge' ? value >= cutoff : value <= cutoff;
  }
  function evaluate(metrics, cutoffs, side) {
    side = side || 'long';
    var c = {}; var k; for (k in DEFAULT_CUTOFFS) c[k] = DEFAULT_CUTOFFS[k];
    if (cutoffs) for (k in cutoffs) c[k] = cutoffs[k];
    var m = metrics || {}, long = side === 'long', gates = [];
    function add(metric, value, cutoff, cmpSide, fmt) {
      var ok = _passes(value, cutoff, cmpSide);
      gates.push({ metric: metric, value: value, cutoff: cutoff, cmp: cmpSide, pass: ok, fmt: fmt(value, cutoff, ok) });
      return ok;
    }
    var g_rvol = add('RVOL', m.rvol, c.rvol, 'ge', function (v, t) { return 'RVOL ' + (v != null ? v.toFixed(2) : '—') + '≥' + t.toFixed(2); });
    var zc = long ? c.z : -c.z;
    var g_z = add('z-disp', m.z, zc, long ? 'ge' : 'le', function (v, t) { return 'z ' + (v != null ? (v >= 0 ? '+' : '') + v.toFixed(2) : '—') + 'σ ' + (long ? '≥' : '≤') + ' ' + t.toFixed(2); });
    var vr = m.vwap_reclaim, vwapVal;
    if (vr == null) vwapVal = null; else if (long) vwapVal = vr ? 1.0 : 0.0; else vwapVal = (!vr) ? 1.0 : 0.0;
    var g_vwap = add('VWAP', vwapVal, 1.0, 'ge', function (v, t, ok) { return 'VWAP ' + (long ? 'reclaim' : 'loss') + ' ' + (ok ? 'YES' : 'no'); });
    var obvc = long ? c.obv_t : -c.obv_t;
    var g_obv = add('OBV slope', m.obv_t, obvc, long ? 'ge' : 'le', function (v, t) { return 'OBV slope t=' + (v != null ? (v >= 0 ? '+' : '') + v.toFixed(2) : '—') + (long ? '≥' : '≤') + t.toFixed(2); });
    var core = g_rvol && g_z && g_vwap && g_obv;
    if (m.mfi != null) {
      if (long) add('MFI', m.mfi, c.mfi_hi, 'ge', function (v, t) { return 'MFI ' + Math.round(v) + '≥' + Math.round(t); });
      else add('MFI', m.mfi, c.mfi_lo, 'le', function (v, t) { return 'MFI ' + Math.round(v) + '≤' + Math.round(t); });
    }
    if (m.breakout_atr != null) {
      var bc = long ? c.atr : -c.atr;
      add('Breakout', m.breakout_atr, bc, long ? 'ge' : 'le', function (v, t) { return 'Breakout ' + (v >= 0 ? '+' : '') + v.toFixed(2) + ' ATR' + (long ? '≥' : '≤') + t.toFixed(2); });
    }
    var row = gates.map(function (g) { return g.fmt; }).join(' | ');
    return { flip: !!core, side: side, gates: gates, row: row, cutoffs: c };
  }
  var API = { sigmaTodDisplacement: sigmaTodDisplacement, breakoutATR: breakoutATR, obvSlopeT: obvSlopeT, evaluate: evaluate, DEFAULT_CUTOFFS: DEFAULT_CUTOFFS };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  root.MrktIntradayConviction = API;
})(typeof window !== 'undefined' ? window : this);
