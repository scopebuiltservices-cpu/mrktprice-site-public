/* auth_client.js — browser auth client for the cookie (BFF) migration. Pairs with auth_bff_reference.js.
 *
 * Replaces the localStorage credential model: the access code is POSTed ONCE to /auth/session to mint an
 * HttpOnly cookie, then never stored in JS. Page gating asks the SERVER (/auth/me) instead of trusting a
 * JS-readable token; an instant render hint comes from the non-secret `mrkt_ui` cookie. Data calls just add
 * credentials:'include' so the cookie rides along.
 *
 * SAFE MIGRATION: every method falls back to the legacy localStorage behavior when the backend /auth/* is
 * not deployed yet (404 / network error). So this can ship on a branch BEFORE the API has the cookie
 * endpoints without locking anyone out — and once the API is live, the cookie path takes over automatically.
 *
 * Usage on a protected page (replaces the inline /*mrkt-gate*\/):
 *     <script src="auth_client.js"></script>
 *     <script>MrktAuth.gate();</script>           // redirects to login if the server says not authenticated
 * On the login page enter():  MrktAuth.login(code).then(r => { if (r.ok) location.href='terminal.html'; });
 * Data calls:  MrktAuth.authedFetch(MRKT_API + '/history?ticker=' + t)
 * Logout:      MrktAuth.logout();
 */
(function () {
  "use strict";
  var API = (function () {
    try {
      var h = location.hostname;
      return (h === 'localhost' || h === '127.0.0.1') ? 'http://localhost:8000' : 'https://mrktprice-data.onrender.com';
    } catch (e) { return 'https://mrktprice-data.onrender.com'; }
  })();
  var LEGACY_KEYS = ['mrkt.token', 'mrkt.code', 'mrkt.ok', 'mrkt.email', 'mrkt.refresh'];
  var _meCache = null, _meAt = 0;

  function _cookie(name) {
    try {
      var m = ('; ' + document.cookie).match('; ' + name + '=([^;]*)');
      return m ? decodeURIComponent(m[1]) : null;
    } catch (e) { return null; }
  }
  function _ls(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function _legacyPresent() { return !!(_ls('mrkt.token') || _ls('mrkt.code') || _ls('mrkt.ok')); }
  function _clearLegacy() { try { LEGACY_KEYS.forEach(function (k) { localStorage.removeItem(k); }); } catch (e) {} }

  // POST the code ONCE to mint the HttpOnly cookie. Never store the code in JS afterwards.
  function login(code) {
    code = (code || '').toString().trim();
    if (!code) return Promise.resolve({ ok: false, status: 0, error: 'empty code' });
    return fetch(API + '/auth/session', {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: code })
    }).then(function (r) {
      if (r.status === 404) {                                  // backend not deployed yet -> safe legacy fallback
        try { localStorage.setItem('mrkt.code', code); } catch (e) {}
        return { ok: true, status: 200, via: 'legacy', subscribed: null };
      }
      return r.json().catch(function () { return {}; }).then(function (j) {
        return { ok: r.ok, status: r.status, subscribed: j && j.subscribed, error: j && j.error };
      });
    }).catch(function () {                                      // network error -> legacy fallback (no lockout)
      try { localStorage.setItem('mrkt.code', code); } catch (e) {}
      return { ok: true, status: 0, via: 'legacy-offline', subscribed: null };
    });
  }

  // Server truth for gating. Cached ~5s. Falls back to legacy presence if /auth/me is absent.
  function me(force) {
    if (!force && _meCache && (Date.now() - _meAt) < 5000) return Promise.resolve(_meCache);
    return fetch(API + '/auth/me', { credentials: 'include', cache: 'no-store' }).then(function (r) {
      if (r.status === 404) return { authenticated: _legacyPresent(), subscribed: null, via: 'legacy' };
      return r.json().catch(function () { return { authenticated: false }; });
    }).then(function (j) { _meCache = j; _meAt = Date.now(); return j; })
      .catch(function () { return { authenticated: _legacyPresent(), subscribed: null, via: 'legacy-offline' }; });
  }

  function logout(redirect) {
    return fetch(API + '/auth/logout', { method: 'POST', credentials: 'include' })
      .catch(function () {})
      .then(function () { _clearLegacy(); _meCache = null; location.replace(redirect || 'index.html'); });
  }

  // Page gate: instant optimistic render (mrkt_ui cookie OR legacy localStorage), then confirm with the
  // server and bounce to login if it says no. Avoids a flash while keeping the server as source of truth.
  function gate(opts) {
    opts = opts || {};
    var loginUrl = opts.loginUrl || 'login.html';
    var optimistic = !!_cookie('mrkt_ui') || _legacyPresent();
    if (!optimistic) { location.replace(loginUrl); return Promise.resolve(false); }
    return me(true).then(function (m) {
      var authed = m && (m.authenticated || (m.via && m.via.indexOf('legacy') === 0 && _legacyPresent()));
      if (!authed) { location.replace(loginUrl); return false; }
      return true;
    });
  }

  // Fetch that carries the cookie. During migration it ALSO re-sends legacy headers if a localStorage code
  // still exists, so the call authenticates whether the API has switched to cookies or not.
  function authedFetch(url, options) {
    var o = Object.assign({ credentials: 'include' }, options || {});
    o.headers = Object.assign({}, o.headers || {});
    var legacyTok = _ls('mrkt.token'), legacyCode = _ls('mrkt.code');
    if (legacyTok && !o.headers['Authorization']) o.headers['Authorization'] = 'Bearer ' + legacyTok;
    if (legacyCode && !o.headers['X-Access-Code']) o.headers['X-Access-Code'] = legacyCode;
    if ((o.method || 'GET').toUpperCase() !== 'GET') {        // CSRF double-submit on state-changing calls
      var csrf = _cookie('mrkt_csrf'); if (csrf) o.headers['X-CSRF-Token'] = csrf;
    }
    return fetch(url, o);
  }

  var root = (typeof window !== "undefined") ? window : {};
  root.MrktAuth = { API: API, login: login, me: me, logout: logout, gate: gate, authedFetch: authedFetch,
                    _cookie: _cookie, _legacyPresent: _legacyPresent, _clearLegacy: _clearLegacy };
  if (typeof module !== "undefined" && module.exports) module.exports = root.MrktAuth;   // node-testable
})();
