/* projlearn_panel.js — FRONT-AND-CENTER projClose-vs-priceNow learning panel. Logs each day's predicted
   log-return per horizon to a localStorage ledger, attaches the realized outcome when the matured bar
   arrives, fits the Mincer-Zarnowitz recalibration (projlearn_engine, pooled by horizon across tickers),
   applies the LEARNED correction to the projClose, and renders big tiles: priceNow -> corrected projClose,
   %move, raw-vs-corrected, skill-vs-naive, samples, and the learning status. EXTERNAL module (no monolith
   surgery): reads the global CUR and injects a panel atop .chartcard. Research only, not advice. */
(function () {
  'use strict';
  var KEY = 'mp_projledger', HZ = [5, 10, 21], MAXN = 6000;

  function cur() { try { return (typeof CUR !== 'undefined') ? CUR : null; } catch (e) { return null; } }
  function load() { try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch (e) { return []; } }
  function save(a) { try { localStorage.setItem(KEY, JSON.stringify(a.slice(-MAXN))); } catch (e) {} }
  function L() { return window.MrktProjLearn; }

  function logForecast(led, c) {
    if (!c || !c.sym || !c.pj || !c.pj.path || !c.d || !c.d.length || !(c.last > 0)) return false;
    var asof = c.d[c.d.length - 1], tk = (c.sym || '').toUpperCase(), changed = false;
    HZ.forEach(function (h) {
      if (c.pj.path.length < h) return;
      var pc = c.pj.path[h - 1] && c.pj.path[h - 1].price; if (!(pc > 0)) return;
      var predLR = Math.log(pc / c.last);
      var dup = led.some(function (e) { return e.tk === tk && e.asof === asof && e.h === h; });
      if (!dup) { led.push({ tk: tk, asof: asof, h: h, pNow: c.last, predLR: predLR }); changed = true; }
    });
    return changed;
  }

  function attachRealized(led, c) {
    if (!c || !c.c || !c.d) return false;
    var tk = (c.sym || '').toUpperCase(), idxOf = {}, changed = false;
    for (var i = 0; i < c.d.length; i++) idxOf[c.d[i]] = i;
    led.forEach(function (e) {
      if (e.tk !== tk || e.real != null) return;
      var i0 = idxOf[e.asof]; if (i0 == null) return;
      var it = i0 + e.h; if (it < c.c.length && c.c[it] > 0 && e.pNow > 0) {
        e.real = Math.log(c.c[it] / e.pNow); e.rzDate = c.d[it]; changed = true;
      }
    });
    return changed;
  }

  function models(led) {
    var out = {}; if (!L()) return out;
    HZ.forEach(function (h) {
      var m = led.filter(function (e) { return e.h === h && e.real != null; });
      out[h] = { model: L().learn(m.map(function (e) { return e.predLR; }), m.map(function (e) { return e.real; })), n: m.length };
    });
    return out;
  }

  function tile(h, c, mo, srv) {
    var pc = (c.pj.path.length >= h && c.pj.path[h - 1]) ? c.pj.path[h - 1].price : null;
    if (!(pc > 0)) return '';
    var rawLR = Math.log(pc / c.last), m = mo.model, applied = m && m.applied;
    // correction source: the user's OWN cone outcomes when learned; else the universe seed (projlearn.json)
    // but ONLY if the universe model actually has positive skill — never apply a no-edge shrink.
    var sm = (srv && srv.byHorizon) ? srv.byHorizon[String(h)] : null;
    var seeded = false;
    if (!applied && L() && sm && sm.applied && sm.skill > 0) { m = sm; seeded = true; }
    var corrLR = (m && (applied || seeded) && L()) ? L().recalibrate(rawLR, m.wAlpha, m.wBeta) : rawLR;
    var corrPx = c.last * Math.exp(corrLR), rawPct = (Math.exp(rawLR) - 1) * 100, corrPct = (Math.exp(corrLR) - 1) * 100;
    var col = corrPct >= 0 ? '#2ecc8f' : '#ef5f4e';
    var skillPct = (m && m.skill != null) ? Math.max(-100, Math.min(100, m.skill * 100)) : null;
    var status = applied ? ('✓ learning · skill ' + (skillPct >= 0 ? '+' : '') + (skillPct == null ? '?' : skillPct.toFixed(0)) + '%')
      : seeded ? ('✓ universe-seeded · skill +' + skillPct.toFixed(0) + '%')
      : ('calibrating ' + (mo.n || 0) + '/8');
    var uni = (sm && sm.n) ? ('universe @' + h + 'd: skill ' + (sm.skill >= 0 ? '+' : '') + (sm.skill * 100).toFixed(0) + '% · β ' + sm.beta.toFixed(2) + ' · n=' + sm.n
      + (sm.skill <= 0 ? ' (momentum: no horizon edge → trust price now)' : '')) : '';
    var skBar = skillPct == null ? '' : '<div style="height:4px;background:#1b2026;border-radius:2px;margin-top:4px;overflow:hidden">'
      + '<div style="height:100%;width:' + Math.max(0, Math.min(100, (skillPct + 100) / 2)) + '%;background:' + (skillPct >= 0 ? '#2ecc8f' : '#ef5f4e') + '"></div></div>';
    return '<div style="flex:1;min-width:150px;background:var(--panel2,#11151b);border:1px solid var(--line,#222);border-radius:8px;padding:9px 11px">'
      + '<div style="font-size:9px;color:var(--muted,#8a94a3);letter-spacing:.5px">' + h + '-DAY PROJECTION</div>'
      + '<div style="font-size:11px;color:#cfe0f0;margin-top:3px">$' + c.last.toFixed(2) + ' <span style="color:#69727f">→</span> '
      + '<b style="font-size:18px;color:' + col + '">$' + corrPx.toFixed(2) + '</b></div>'
      + '<div style="font-size:15px;font-weight:700;color:' + col + '">' + (corrPct >= 0 ? '+' : '') + corrPct.toFixed(2) + '%</div>'
      + skBar
      + '<div style="font-size:8px;color:#69727f;margin-top:4px">' + status + (applied ? (' · β ' + m.wBeta.toFixed(2) + ' · bias ' + (m.bias * 100).toFixed(2) + '%') : '')
      + '<br>raw ' + (rawPct >= 0 ? '+' : '') + rawPct.toFixed(2) + '% → corrected ' + (corrPct >= 0 ? '+' : '') + corrPct.toFixed(2) + '% · n=' + (mo.n || 0)
      + (uni ? ('<br><span style="color:#5a6470">' + uni + '</span>') : '') + '</div>'
      + '</div>';
  }

  var _srv = null, _srvTried = false;
  function srv() {
    if (_srvTried) return _srv; _srvTried = true;
    try { fetch('projlearn.json', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { _srv = j; }).catch(function () {}); } catch (e) {}
    return _srv;
  }

  function render(c, mos) {
    var card = document.querySelector('.chartcard'); if (!card) return;
    var host = document.getElementById('projLearnPanel');
    if (!host) { host = document.createElement('div'); host.id = 'projLearnPanel';
      host.style.cssText = 'margin:0 0 8px 0'; card.insertBefore(host, card.firstChild); }
    var totN = HZ.reduce(function (a, h) { return a + (mos[h] ? mos[h].n : 0); }, 0);
    var tiles = HZ.map(function (h) { return tile(h, c, mos[h] || { model: {}, n: 0 }, _srv); }).join('');
    host.innerHTML = '<div style="display:flex;align-items:center;gap:8px;margin-bottom:5px">'
      + '<b style="font-size:11px;color:var(--brand,#d8b24a);letter-spacing:.5px">PROJ CLOSE vs PRICE NOW — SELF-LEARNING</b>'
      + '<span style="font-size:8px;color:#69727f">Mincer-Zarnowitz recalibration · learns daily from realized outcomes · ' + totN + ' matured · research only</span></div>'
      + '<div style="display:flex;gap:8px;flex-wrap:wrap">' + tiles + '</div>';
  }

  var last = '', t = null;
  function tick() {
    var c = cur(); if (!c || !c.sym || !c.pj || !c.pj.path) return;
    var sig = (c.sym || '') + '|' + (c.d ? c.d[c.d.length - 1] : '') + '|' + (c.pj.path.length);
    var led = load(), ch = false;
    ch = logForecast(led, c) || ch; ch = attachRealized(led, c) || ch;
    if (ch) save(led);
    if (sig !== last || ch) { last = sig; try { render(c, models(led)); } catch (e) {} }
  }
  if (typeof document !== 'undefined') {
    setInterval(tick, 900);
    if (document.readyState !== 'loading') setTimeout(tick, 600);
    else document.addEventListener('DOMContentLoaded', function () { setTimeout(tick, 600); });
  }
})();
