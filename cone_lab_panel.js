/* cone_lab_panel.js — live 3-cone σ-source comparison for the terminal cone area.
 * window.ConeLab.render(containerEl, closes, coneEval) draws a compact side-by-side cone for each
 * sigma source (sqrt-time / champion / arbiter) from the ticker's real closes, with out-of-sample
 * coverage + interval score, and highlights the server's recommendation (n.coneEval.recommend).
 * Same math as cone_eval.py. Self-contained (no deps); safe to load even if unused. */
(function (root) {
  var COLORS = { sqrt_time: '#e0a13c', champion: '#2ecc8f', arbiter: '#39b6ff' };
  var LABEL = { sqrt_time: '√t', champion: 'Champion', arbiter: 'Arbiter' };

  function lr(c) { var o = [], i; for (i = 1; i < c.length; i++) if (c[i] > 0 && c[i - 1] > 0) o.push(Math.log(c[i] / c[i - 1])); return o; }
  function sd(x) { if (x.length < 2) return null; var m = 0, i; for (i = 0; i < x.length; i++) m += x[i]; m /= x.length; var s = 0; for (i = 0; i < x.length; i++) s += (x[i] - m) * (x[i] - m); return Math.sqrt(s / (x.length - 1)); }
  function ew(x, l) { if (!x.length) return null; var v = x[0] * x[0], i; for (i = 1; i < x.length; i++) v = l * v + (1 - l) * x[i] * x[i]; return Math.sqrt(v); }
  function vr(c, q) { var r = lr(c); if (r.length < q * 4) return null; var m = 0, i; for (i = 0; i < r.length; i++) m += r[i]; m /= r.length; var v1 = 0; for (i = 0; i < r.length; i++) v1 += (r[i] - m) * (r[i] - m); v1 /= r.length; if (v1 <= 0) return null; var s = 0, k; for (k = q - 1; k < r.length; k++) { var su = 0; for (i = 0; i < q; i++) su += r[k - i]; s += (su - q * m) * (su - q * m); } s /= (r.length - q + 1); return s / (q * v1); }
  function cl(x, a, b) { return Math.max(a, Math.min(b, x)); }
  function vl(v, ne) { if (v == null || ne < 60) return 0; return 0.5 * cl((ne - 60) / 180, 0, 1) * cl(Math.abs(v - 1) / 0.5, 0, 1); }
  var SRC = {
    sqrt_time: function (c, H) { var s = sd(lr(c)); return s > 0 ? s * Math.sqrt(H) : null; },
    champion: function (c, H) { var s = sd(lr(c)); if (!(s > 0)) return null; var v = vr(c, Math.min(H, Math.max(2, (c.length / 4) | 0))); v = (v && v > 0) ? v : 1; return s * Math.sqrt(H * v); },
    arbiter: function (c, H) { var r = lr(c); if (r.length < 10) return null; var s = sd(r); if (!(s > 0)) return null; var cm = [[s * Math.sqrt(H), 0.9]], e = ew(r, 0.94); if (e > 0) cm.push([e * Math.sqrt(H), 0.8]); var v = vr(c, Math.min(H, Math.max(2, (c.length / 4) | 0))), lam = v != null ? vl(v, r.length) : 0, nu = 0, de = 0, i; for (i = 0; i < cm.length; i++) { nu += cm[i][1] * cm[i][0] * cm[i][0]; de += cm[i][1]; } var s2 = nu / de; if (v != null && lam > 0) { var sv = s * Math.sqrt(H * Math.max(v, 1e-6)); s2 = (1 - lam) * s2 + lam * sv * sv; } return Math.sqrt(s2); }
  };
  function ppf(p) { var a = [-39.6968302866538, 220.946098424521, -275.928510446969, 138.357751867269, -30.6647980661472, 2.50662827745924], b = [-54.4760987982241, 161.585836858041, -155.698979859887, 66.8013118877197, -13.2806815528857], c = [-0.00778489400243029, -0.322396458041136, -2.40075827716184, -2.54973253934373, 4.37466414146497, 2.93816398269878], d = [0.00778469570904146, 0.322467129070399, 2.445134137143, 3.75440866190742], pl = 0.02425, ph = 1 - pl, q, r; if (p < pl) { q = Math.sqrt(-2 * Math.log(p)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); } if (p <= ph) { q = p - 0.5; r = q * q; return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1); } q = Math.sqrt(-2 * Math.log(1 - p)); return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
  function bt(c, H, lv, fn) { var z = ppf((1 + lv) / 2), al = 1 - lv, hit = 0, n = 0, ws = 0, is = 0, t; for (t = 60; t < c.length - H; t += 3) { var h = c.slice(0, t + 1), sH = fn(h, H); if (!(sH > 0)) continue; var rr = Math.log(c[t + H] / c[t]), lo = -z * sH, hi = z * sH; hit += (rr >= lo && rr <= hi) ? 1 : 0; n++; ws += z * sH; var s = hi - lo; if (rr < lo) s += 2 / al * (lo - rr); else if (rr > hi) s += 2 / al * (rr - hi); is += s; } return n ? { cov: hit / n, hw: ws / n, is: is / n, cal: Math.abs(hit / n - lv), n: n } : null; }
  function draw(cv, c, fn, H, lv, col) { if (!cv || !cv.getContext) return; var dpr = root.devicePixelRatio || 1, W = cv.clientWidth || 200, Hh = cv.height / dpr; cv.width = W * dpr; cv.style.height = Hh + 'px'; var x = cv.getContext('2d'); x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, W, Hh); var nh = Math.min(90, c.length), hs = c.slice(c.length - nh), P0 = hs[hs.length - 1], z = ppf((1 + lv) / 2), lo = [], hi = [], k, i; for (k = 1; k <= H; k++) { var sH = fn(c, k) || 0; lo.push(P0 * Math.exp(-z * sH)); hi.push(P0 * Math.exp(z * sH)); } var mn = 1 / 0, mx = -1 / 0; for (i = 0; i < hs.length; i++) { mn = Math.min(mn, hs[i]); mx = Math.max(mx, hs[i]); } mn = Math.min(mn, lo[lo.length - 1]); mx = Math.max(mx, hi[hi.length - 1]); var pd = (mx - mn) * 0.08; mn -= pd; mx += pd; var gw = W - 8, gh = Hh - 10, tt = nh + H; function X(j) { return 4 + j / (tt - 1) * gw; } function Y(p) { return 5 + (1 - (p - mn) / (mx - mn)) * gh; } x.beginPath(); x.moveTo(X(nh - 1), Y(P0)); for (i = 0; i < hi.length; i++) x.lineTo(X(nh + i), Y(hi[i])); for (i = lo.length - 1; i >= 0; i--) x.lineTo(X(nh + i), Y(lo[i])); x.closePath(); x.fillStyle = col; x.globalAlpha = 0.16; x.fill(); x.globalAlpha = 1; x.strokeStyle = '#c9d3de'; x.lineWidth = 1.2; x.beginPath(); for (i = 0; i < hs.length; i++) { var xx = X(i), yy = Y(hs[i]); i ? x.lineTo(xx, yy) : x.moveTo(xx, yy); } x.stroke(); x.fillStyle = col; x.beginPath(); x.arc(X(nh - 1), Y(P0), 2.5, 0, 7); x.fill(); }

  function render(el, closes, coneEval, opts) {
    if (!el) return;
    opts = opts || {};
    var H = opts.H || (coneEval && coneEval.H) || 21, lv = opts.level || (coneEval && coneEval.level) || 0.90;
    var c = (closes || []).map(Number).filter(function (v) { return v > 0; });
    if (c.length < 80) { el.innerHTML = '<div style="color:var(--faint,#646e7c);font-size:11px">Cone σ-source lab: need ≥80 closes.</div>'; return; }
    var rec = coneEval && coneEval.recommend;
    var b = {}; ['sqrt_time', 'champion', 'arbiter'].forEach(function (k) { b[k] = bt(c, H, lv, SRC[k]); });
    var recBadge = rec ? '<span style="font-size:9px;font-weight:700;color:#0a0d12;background:' + (COLORS[rec] || '#c9d3de') + ';padding:1px 6px;border-radius:5px">server pick: ' + (LABEL[rec] || rec) + '</span>' : '';
    var head = '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px"><span style="font-size:9px;letter-spacing:.05em;text-transform:uppercase;color:var(--faint,#646e7c)">Cone σ-source coverage (H=' + H + ', ' + (lv * 100) + '%)</span>' + recBadge + '</div>';
    var grid = '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">';
    ['sqrt_time', 'champion', 'arbiter'].forEach(function (k) {
      var m = b[k], on = (k === rec);
      grid += '<div style="border:1px solid ' + (on ? (COLORS[k] + '88') : 'var(--line,#232a36)') + ';border-radius:8px;padding:6px">' +
        '<div style="font-size:11px;font-weight:700;color:' + COLORS[k] + '">' + LABEL[k] + (on ? ' ◂' : '') + '</div>' +
        '<canvas class="_clc" data-src="' + k + '" height="90"></canvas>' +
        (m ? '<div style="display:flex;gap:8px;margin-top:4px;font-size:10px;color:var(--muted,#8b98a5)"><span><b style="color:var(--ink,#e6edf3)">' + (m.cov * 100).toFixed(0) + '%</b> cov</span><span><b style="color:var(--ink,#e6edf3)">' + m.is.toFixed(3) + '</b> iS</span></div>' : '<div style="font-size:10px;color:var(--faint)">n/a</div>') +
        '</div>';
    });
    grid += '</div>';
    el.innerHTML = head + grid;
    var cvs = el.querySelectorAll('canvas._clc');
    Array.prototype.forEach.call(cvs, function (cv) { var k = cv.getAttribute('data-src'); draw(cv, c, SRC[k], H, lv, COLORS[k]); });
  }

  root.ConeLab = { render: render, sources: SRC, backtest: bt };
})(typeof window !== 'undefined' ? window : this);
