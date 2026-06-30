/* auth_bff_reference.js — REFERENCE backend for cookie-based auth (drop into the Render data API).
 *
 * Why: today the access code (mrkt.code) — the real credential — lives in localStorage and rides on an
 * `X-Access-Code` header. Anything that runs JS in the origin (XSS, a tampered CDN dep, an extension) can
 * read localStorage and steal it (OWASP: do NOT store auth in web storage). This Backend-For-Frontend
 * moves the credential into an HttpOnly cookie the browser JS can never read, and adds the things a naive
 * "put it in a cookie" misses: CORS-with-credentials, an Origin/CSRF defense (mandatory once cookies are
 * SameSite=None cross-site), a server-truth /auth/me gate, and DUAL-READ so nobody is locked out mid-rollout.
 *
 * Design (100x, no new infra): the session cookie is a short-lived HMAC-SIGNED token (tamper-proof,
 * stateless, server-verifiable) carrying only {codeHash, subscribed, exp} — the RAW code never sits in the
 * cookie. For revocation / "sign out everywhere", swap the signed token for an opaque id backed by a
 * sessions table (noted inline). A second, NON-secret, JS-readable hint cookie (mrkt_ui=1) lets the static
 * pages gate the UI instantly without exposing the credential.
 *
 * This file is FRAMEWORK-LIGHT (pure Node `crypto` + Express-style (req,res) handlers). Adapt validateCode/
 * subscriptionStatus to your EXISTING code-validation + Lemon Squeezy subscription logic (the API already
 * returns 401/402, so it has both). FastAPI equivalents are noted in comments. Nothing here is deployed by
 * this repo — it is a reference you copy into the API service and test per AUTH_MIGRATION.md.
 */
'use strict';
const crypto = require('crypto');

// ---- config (env) -----------------------------------------------------------------------------------
const SECRET = process.env.MRKT_SESSION_SECRET || '';            // REQUIRED: 32+ random bytes, set on Render
const SESS_TTL_SEC = parseInt(process.env.MRKT_SESSION_TTL || '86400', 10);   // session lifetime (default 24h)
const ALLOWED_ORIGINS = (process.env.MRKT_ALLOWED_ORIGINS ||
  'https://mrktprice.com,https://www.mrktprice.com,http://localhost:8000').split(',').map(s => s.trim());
const SESS_COOKIE = '__Host-mrkt_sess';   // __Host- prefix => must be Secure, Path=/, no Domain (host-locked)
const UI_COOKIE = 'mrkt_ui';              // NON-secret render hint (JS-readable). Carries NO credential.
const CSRF_COOKIE = 'mrkt_csrf';          // double-submit token for state-changing requests

// ---- signed-token core (HMAC-SHA256) --------------------------------------------------------------
function b64url(buf) { return Buffer.from(buf).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); }
function b64urlJSON(o) { return b64url(JSON.stringify(o)); }
function fromB64url(s) { return Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/'), 'base64'); }

function sign(payloadB64) {
  return b64url(crypto.createHmac('sha256', SECRET).update(payloadB64).digest());
}
function mintSession({ code, subscribed, email }) {
  const payload = {
    c: crypto.createHash('sha256').update(String(code)).digest('hex').slice(0, 32),  // code HASH, not the code
    s: !!subscribed,
    e: email || null,
    exp: Math.floor(Date.now() / 1000) + SESS_TTL_SEC,
  };
  const p = b64urlJSON(payload);
  return p + '.' + sign(p);
}
function verifySession(token) {
  if (!token || typeof token !== 'string' || token.indexOf('.') < 0) return null;
  const [p, sig] = token.split('.');
  const expect = sign(p);
  // timing-safe compare
  if (sig.length !== expect.length || !crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expect))) return null;
  let payload;
  try { payload = JSON.parse(fromB64url(p).toString('utf8')); } catch (e) { return null; }
  if (!payload || (payload.exp || 0) < Math.floor(Date.now() / 1000)) return null;   // expired
  return payload;
}

// ---- cookie helpers ---------------------------------------------------------------------------------
function setCookie(res, name, value, opts) {
  const o = Object.assign({ Path: '/', Secure: true, SameSite: 'None' }, opts || {});
  let c = name + '=' + value;
  if (o.HttpOnly) c += '; HttpOnly';
  if (o.Secure) c += '; Secure';
  c += '; SameSite=' + o.SameSite + '; Path=' + o.Path;
  if (o['Max-Age'] != null) c += '; Max-Age=' + o['Max-Age'];
  // append (don't clobber other Set-Cookie headers)
  const prev = res.getHeader('Set-Cookie');
  res.setHeader('Set-Cookie', prev ? [].concat(prev, c) : [c]);
}
function setSessionCookies(res, token, subscribed) {
  setCookie(res, SESS_COOKIE, token, { HttpOnly: true, 'Max-Age': SESS_TTL_SEC });   // credential (JS can't read)
  setCookie(res, UI_COOKIE, '1', { HttpOnly: false, 'Max-Age': SESS_TTL_SEC });      // render hint only
  const csrf = b64url(crypto.randomBytes(18));
  setCookie(res, CSRF_COOKIE, csrf, { HttpOnly: false, 'Max-Age': SESS_TTL_SEC });   // double-submit token
}
function clearCookies(res) {
  for (const n of [SESS_COOKIE, UI_COOKIE, CSRF_COOKIE]) setCookie(res, n, '', { HttpOnly: n === SESS_COOKIE, 'Max-Age': 0 });
}
function readCookies(req) {
  const out = {}; const raw = req.headers && req.headers.cookie;
  if (!raw) return out;
  raw.split(';').forEach(p => { const i = p.indexOf('='); if (i > 0) out[p.slice(0, i).trim()] = decodeURIComponent(p.slice(i + 1).trim()); });
  return out;
}

// ---- CORS (credentials) + CSRF/Origin defense ------------------------------------------------------
function applyCors(req, res) {
  const origin = req.headers && req.headers.origin;
  if (origin && ALLOWED_ORIGINS.indexOf(origin) >= 0) {
    res.setHeader('Access-Control-Allow-Origin', origin);     // echo the EXACT origin (never * with credentials)
    res.setHeader('Access-Control-Allow-Credentials', 'true');
    res.setHeader('Vary', 'Origin');
    res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type,X-CSRF-Token,Authorization,X-Access-Code');
  }
}
function originAllowed(req) {
  // SameSite=None cookies are auto-sent cross-site, so verify Origin/Referer against the allowlist (CSRF defense).
  const o = (req.headers && (req.headers.origin || '')) || '';
  if (o) return ALLOWED_ORIGINS.indexOf(o) >= 0;
  const ref = (req.headers && (req.headers.referer || '')) || '';
  return ALLOWED_ORIGINS.some(a => ref.indexOf(a) === 0);
}
function csrfOk(req) {
  // double-submit: the readable CSRF cookie must equal the X-CSRF-Token header (only same-origin JS can read both)
  const c = readCookies(req)[CSRF_COOKIE];
  const h = req.headers && (req.headers['x-csrf-token'] || req.headers['X-CSRF-Token']);
  return !!c && !!h && c === h;
}

// ---- the API surface the dashboard calls (adapt validateCode/subscriptionStatus to your logic) -----
// REPLACE these two with your EXISTING checks (the same logic that makes data calls return 401/402 today).
async function validateCode(code) { /* return true/false */ return !!code; }
async function subscriptionStatus(code) { /* return {subscribed:boolean, email?:string} */ return { subscribed: true }; }

// POST /auth/session  — body {code}. Validates, sets the HttpOnly session cookie, returns status.
async function postSession(req, res, body) {
  applyCors(req, res);
  if (!originAllowed(req)) { res.statusCode = 403; return res.end(JSON.stringify({ error: 'bad origin' })); }
  const code = (body && body.code || '').toString().trim();
  if (!code || !(await validateCode(code))) { res.statusCode = 401; return res.end(JSON.stringify({ error: 'invalid code' })); }
  const sub = await subscriptionStatus(code);
  setSessionCookies(res, mintSession({ code, subscribed: sub.subscribed, email: sub.email }), sub.subscribed);
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify({ ok: true, subscribed: !!sub.subscribed, email: sub.email || null }));
}

// GET /auth/me  — server truth for the page gate. {authenticated, subscribed, email}.
function getMe(req, res) {
  applyCors(req, res);
  const tok = readCookies(req)[SESS_COOKIE];
  const p = verifySession(tok);
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify(p ? { authenticated: true, subscribed: !!p.s, email: p.e || null }
                            : { authenticated: false, subscribed: false }));
}

// POST /auth/logout — clears cookies. (With an opaque-session store, also DELETE the session row here.)
function postLogout(req, res) {
  applyCors(req, res);
  clearCookies(res);
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify({ ok: true }));
}

// ---- DUAL-READ auth for the existing data endpoints (no-lockout migration) -------------------------
// During the migration window, accept EITHER the new cookie OR the legacy X-Access-Code / Bearer header,
// so already-logged-in users (still on localStorage) keep working while the cookie path rolls out.
function authFromRequest(req) {
  const p = verifySession(readCookies(req)[SESS_COOKIE]);
  if (p) return { ok: true, subscribed: !!p.s, via: 'cookie', email: p.e || null };
  const legacyCode = req.headers && (req.headers['x-access-code'] || req.headers['X-Access-Code']);
  const bearer = req.headers && (req.headers.authorization || '');
  if (legacyCode) return { ok: true, subscribed: null, via: 'legacy-code', code: legacyCode };   // subscription re-checked downstream
  if (/^Bearer\s+/.test(bearer)) return { ok: true, subscribed: null, via: 'legacy-bearer', token: bearer.replace(/^Bearer\s+/, '') };
  return { ok: false };
}
// Gate middleware for the data endpoints: 401 = no auth, 402 = no subscription (unchanged contract).
function requireAuth(req, res, next) {
  applyCors(req, res);
  if (req.method === 'OPTIONS') { res.statusCode = 204; return res.end(); }    // CORS preflight
  if (!originAllowed(req)) { res.statusCode = 403; return res.end(JSON.stringify({ error: 'bad origin' })); }
  const a = authFromRequest(req);
  if (!a.ok) { res.statusCode = 401; return res.end(JSON.stringify({ error: 'sign in required' })); }
  if (a.subscribed === false) { res.statusCode = 402; return res.end(JSON.stringify({ error: 'subscription required' })); }
  req.mrktAuth = a;
  return next();
}

// ---- Express mount example (adapt to your router) -------------------------------------------------
// const express = require('express'); app.use(express.json()); app.use(require('cookie-parser')());
// app.options('*', (req,res)=>{ applyCors(req,res); res.sendStatus(204); });
// app.post('/auth/session', (req,res)=>postSession(req,res,req.body));
// app.get ('/auth/me',      getMe);
// app.post('/auth/logout',  postLogout);
// app.use('/history','/fundamentals','/estimates','/macro','/auth-protected...', requireAuth);
//
// FastAPI: Response.set_cookie(key, value, httponly=True, secure=True, samesite='none', path='/'); read via
// request.cookies; CORSMiddleware(allow_origins=ALLOWED, allow_credentials=True). Same signed-token logic.

module.exports = {
  mintSession, verifySession, setSessionCookies, clearCookies, readCookies,
  applyCors, originAllowed, csrfOk, authFromRequest,
  postSession, getMe, postLogout, requireAuth,
  SESS_COOKIE, UI_COOKIE, CSRF_COOKIE, ALLOWED_ORIGINS,
};
