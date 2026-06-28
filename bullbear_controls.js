/* bullbear_controls.js — turns the static Bull/Bear board into an INTERACTIVE analytical board:
   sort (Total / Conviction / |z| / Ticker), conviction filter (All / MED+ / HIGH), and live ticker
   search — all as pure DOM operations over the data-* attributes rowH() emits, so nothing is recomputed.
   State persists in localStorage; a MutationObserver re-applies after the board re-renders on new data.
   Externalized per the project protocol (small, node-checkable) instead of growing terminal.html. */
(function () {
  'use strict';
  var KEY = { sort: 'bbSort', filt: 'bbFilter', q: 'bbQuery' };
  var CONVRANK = { HIGH: 3, MED: 2, LOW: 1 };
  var applying = false, t = null;

  function ls(k, d) { try { var v = localStorage.getItem(k); return v == null ? d : v; } catch (e) { return d; } }
  function setls(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  var state = { sort: ls(KEY.sort, 'score'), filt: ls(KEY.filt, 'all'), q: ls(KEY.q, '') };

  function seg(items, getCur, on) {
    var s = document.createElement('span'); s.className = 'seg';
    items.forEach(function (it) {
      var b = document.createElement('b'); b.textContent = it[1]; b.dataset.v = it[0];
      if (it[0] === getCur()) b.className = 'on';
      b.onclick = function () { on(it[0]); };
      s.appendChild(b);
    });
    return s;
  }

  function controls(board) {
    if (document.getElementById('bbCtl')) return;
    var bar = document.createElement('div'); bar.id = 'bbCtl';
    var l1 = document.createElement('span'); l1.textContent = 'sort'; bar.appendChild(l1);
    bar.appendChild(seg([['score', 'Confidence'], ['tot', 'Total'], ['conv', 'Conviction'], ['z', '|z|'], ['tk', 'Ticker']],
      function () { return state.sort; },
      function (v) { state.sort = v; setls(KEY.sort, v); refreshChips(); apply(board); }));
    var l2 = document.createElement('span'); l2.textContent = 'conviction'; bar.appendChild(l2);
    bar.appendChild(seg([['all', 'All'], ['med', 'MED+'], ['high', 'HIGH']],
      function () { return state.filt; },
      function (v) { state.filt = v; setls(KEY.filt, v); refreshChips(); apply(board); }));
    var inp = document.createElement('input'); inp.placeholder = 'search ticker'; inp.value = state.q;
    inp.oninput = function () { state.q = inp.value.toUpperCase(); setls(KEY.q, state.q); apply(board); };
    bar.appendChild(inp);
    var stat = document.createElement('span'); stat.id = 'bbStatus';
    stat.style.cssText = 'margin-left:8px;font-size:10px;color:var(--muted,#8a93a0);cursor:pointer';
    stat.title = 'click to clear the conviction filter / search and show every company';
    stat.onclick = function () { state.filt = 'all'; state.q = ''; setls(KEY.filt, 'all'); setls(KEY.q, ''); var ip = bar.querySelector('input'); if (ip) ip.value = ''; refreshChips(); apply(board); };
    bar.appendChild(stat);
    board.parentNode.insertBefore(bar, board);   // sibling BEFORE the board, so board.innerHTML re-renders don't wipe it
  }

  function refreshChips() {
    var bar = document.getElementById('bbCtl'); if (!bar) return;
    var segs = bar.querySelectorAll('.seg');
    [state.sort, state.filt].forEach(function (cur, i) {
      if (!segs[i]) return;
      Array.prototype.forEach.call(segs[i].querySelectorAll('b'), function (b) { b.className = (b.dataset.v === cur) ? 'on' : ''; });
    });
  }

  function cmp(side) {
    return function (a, b) {
      if (state.sort === 'tk') return a.dataset.tk < b.dataset.tk ? -1 : (a.dataset.tk > b.dataset.tk ? 1 : 0);
      if (state.sort === 'z') return Math.abs(+b.dataset.z) - Math.abs(+a.dataset.z);
      if (state.sort === 'conv') return (CONVRANK[b.dataset.conv] || 0) - (CONVRANK[a.dataset.conv] || 0) || (Math.abs(+b.dataset.z) - Math.abs(+a.dataset.z));
      if (state.sort === 'score') return side === 'bull' ? (+b.dataset.score - +a.dataset.score) : (+a.dataset.score - +b.dataset.score);  // confidence-adjusted, by own direction
      return side === 'bull' ? (+b.dataset.tot - +a.dataset.tot) : (+a.dataset.tot - +b.dataset.tot);   // tot: by own direction
    };
  }
  function pass(row) {
    if (state.filt === 'high' && row.dataset.conv !== 'HIGH') return false;
    if (state.filt === 'med' && row.dataset.conv === 'LOW') return false;
    if (state.q && row.dataset.tk.indexOf(state.q) < 0) return false;
    return true;
  }

  function apply(board) {
    applying = true;
    var totAll = 0, totVis = 0;
    Array.prototype.forEach.call(board.querySelectorAll('.bbcol'), function (col) {
      var box = col.querySelector('.bbrows'); if (!box) return;
      var rows = Array.prototype.slice.call(box.querySelectorAll('.bbrow'));
      rows.sort(cmp(col.dataset.side));
      var vis = 0;
      rows.forEach(function (r) {
        totAll++;
        var ok = pass(r); r.style.display = ok ? '' : 'none';
        if (ok) { vis++; totVis++; var rk = r.querySelector('.bbrk'); if (rk) rk.textContent = vis; }
        box.appendChild(r);   // reorder in place
      });
      var v = col.querySelector('.bbvis'); if (v) v.textContent = vis;
    });
    var stat = document.getElementById('bbStatus');
    if (stat) {
      var hidden = totAll - totVis;
      stat.textContent = 'showing ' + totVis + ' of ' + totAll + ' companies'
        + (hidden > 0 ? ' · ' + hidden + ' hidden by ' + (state.filt !== 'all' ? state.filt.toUpperCase() + ' filter' : 'search') + ' — click to show all' : '');
      stat.style.color = hidden > 0 ? '#e0a13c' : 'var(--muted,#8a93a0)';
    }
    setTimeout(function () { applying = false; }, 0);
  }

  function enhance() {
    var board = document.getElementById('bullBearBoard');
    if (!board || !board.querySelector('.bbcol')) return;
    controls(board); refreshChips(); apply(board);
  }
  function schedule() { clearTimeout(t); t = setTimeout(enhance, 60); }

  if (document.readyState !== 'loading') schedule();
  else document.addEventListener('DOMContentLoaded', schedule);

  new MutationObserver(function (muts) {
    if (applying) return;
    for (var i = 0; i < muts.length; i++) {
      var tg = muts[i].target;
      if (tg && (tg.id === 'bullBearBoard' || (tg.closest && tg.closest('#bullBearBoard')))) { schedule(); return; }
    }
  }).observe(document.body, { childList: true, subtree: true });
})();
