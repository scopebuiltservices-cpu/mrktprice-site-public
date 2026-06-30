# Auth migration — `localStorage` → HttpOnly cookie (the 100x version)

This supersedes the auth section of `AUTH_HARDENING.md`, which assumed a Supabase email/password login that
**isn't actually implemented**. The recon of the live pages found the real model:

- The credential users actually hold is an **access code** (`mrkt.code`), typed on `index.html` / `login.html`,
  written to `localStorage`, and sent to the Render data API as an `X-Access-Code` header.
- A Supabase access token (`mrkt.token`) path exists in `account.html` but is **vestigial** — `account.html`
  only *reads* a session that nothing ever creates, so `mrkt.token` is rarely/never populated.
- Page gates are **presence-only**: `if (mrkt.token || mrkt.ok || mrkt.code) showPage(); else → login`. Any
  non-empty string passes; real enforcement is the API returning **401** (no auth) / **402** (no subscription).

**So the thing in web storage that an XSS can steal is the access code itself.** Moving it to an HttpOnly
cookie is the fix — but a naive "put it in a cookie" opens three new holes (CSRF, CORS-with-credentials, and a
gate that can no longer read the token). The design below closes all of them.

Three bugs the recon also surfaced (all resolved by this migration): `mrkt.ok` is read by gates but never
written (dead key); logout doesn't clear `mrkt.code` (a "signed-out" code user still passes the gate);
`splash.html` ignores `mrkt.code` so code users don't auto-route to the terminal.

---

## The design (and why each piece)

| Concern | Decision | Why |
|---|---|---|
| Where the credential lives | **HttpOnly, Secure, SameSite=None** cookie `__Host-mrkt_sess` | JS (XSS/extension/CDN) can't read it. `__Host-` locks it to the host + Path=/. SameSite=None is required because the site (Pages) and API (Render) are different origins. |
| What's in the cookie | A short-lived **HMAC-signed** token `{codeHash, subscribed, exp}` | Tamper-proof, stateless, server-verifiable, no DB. The **raw code never enters the cookie** (only its hash). |
| Revocation / "sign out everywhere" | Optional upgrade to an **opaque session id + `sessions` table** | Signed tokens can't be revoked before expiry; if you need instant revocation or device management, swap the signed token for an opaque id keyed to a row (noted in `auth_bff_reference.js`). Start signed; upgrade later. |
| Instant page gating without exposing the credential | A second, **non-secret JS-readable** cookie `mrkt_ui=1` | Lets the gate render instantly ("a session exists") then confirm with the server. Carries no credential. |
| Source of truth for "am I in?" | **`GET /auth/me`** (server decides) | The old presence check trusted the client. The server now answers `{authenticated, subscribed}`. |
| CSRF (cookies auto-send cross-site) | **Origin/Referer allowlist on every request** + double-submit `mrkt_csrf` token for non-GET | Mandatory once cookies are SameSite=None. The data API is read-mostly, so the Origin check carries most of the load; the token covers any state-changing call. |
| CORS with cookies | Echo the **exact** origin + `Access-Control-Allow-Credentials: true` + `Vary: Origin` | `Access-Control-Allow-Origin: *` is illegal with credentials. |
| No lockout during rollout | **Dual-read**: the API accepts the new cookie **OR** the legacy `X-Access-Code`/`Bearer` header | Already-logged-in users (still on localStorage) keep working while the cookie path rolls out. The frontend client falls back to legacy behavior if `/auth/*` returns 404. |
| XSS reduction (defense in depth) | Strict **CSP** + SRI on CDN scripts (the `AUTH_HARDENING.md` quick-win) | The cookie defends even if XSS occurs; CSP reduces the chance of XSS at all. |

Files delivered in this repo (reference — adapt + deploy, don't expect them to run as-is):
- **`auth_bff_reference.js`** — the backend: sign/verify, cookie helpers, CORS+Origin+CSRF, `POST /auth/session`,
  `GET /auth/me`, `POST /auth/logout`, and the **dual-read `requireAuth`** for the existing data endpoints.
  Adapt `validateCode()` + `subscriptionStatus()` to your existing code-validation + Lemon Squeezy logic.
- **`auth_client.js`** — the browser client: `login(code)`, `me()`, `logout()`, `gate()`, `authedFetch()`, with
  the **legacy fallback** so it's safe to ship before the backend has the endpoints.

---

## Order of operations (deploy backend FIRST, frontend on a branch)

1. **API (Render) — deploy the cookie endpoints first, with dual-read still accepting the legacy header.**
   - Set env on Render: `MRKT_SESSION_SECRET` (32+ random bytes — generate with `openssl rand -base64 32`),
     `MRKT_ALLOWED_ORIGINS=https://mrktprice.com,https://www.mrktprice.com`, optional `MRKT_SESSION_TTL`.
   - Mount `POST /auth/session`, `GET /auth/me`, `POST /auth/logout`, and an `OPTIONS *` preflight handler.
   - Wrap the data endpoints (`/history`, `/fundamentals`, `/estimates`, `/macro`, …) with `requireAuth`
     (cookie **or** legacy header). **Verify legacy `X-Access-Code` still works** before touching the frontend.
2. **Frontend — on a branch (`auth-cookies`), do NOT merge to `main` until step 3 passes.**
   Apply the four edits below, include `auth_client.js`, and test against the deployed API.
3. **Test the 7 checks (below). Only then merge.** After a week of clean cookie traffic, remove the legacy
   header path from `requireAuth` and the localStorage fallbacks from `auth_client.js`, then flip the lint.

---

## Exact frontend edits (apply on the branch)

Add to the `<head>` of `index.html`, `login.html`, `terminal.html`, `marketmap.html`, `live.html`, `account.html`:
```html
<script src="auth_client.js"></script>
```

**(a) Login — `index.html` `enter()` and `login.html` `enter()`** — stop writing the code to storage; mint the cookie:
```js
// BEFORE:
//   try{localStorage.setItem('mrkt.code',c);localStorage.removeItem('mrkt.token');}catch(e){}
//   setTimeout(function(){location.href='terminal.html';},320);
// AFTER:
MrktAuth.login(c).then(function(r){
  if(r.ok){ msg('Welcome — opening your terminal…','ok'); location.href='terminal.html'; }
  else { msg(r.status===401?'That access code wasn’t recognized.':'Sign-in failed, try again.','err'); $('code').focus(); }
});
```

**(b) Page gate** — replace the inline `/*mrkt-gate*/` presence check on every protected page with:
```html
<script src="auth_client.js"></script><script>MrktAuth.gate();</script>
```
(`gate()` renders instantly off the `mrkt_ui` hint, then confirms with `/auth/me` and bounces to `login.html`
if the server says no. Pre-backend it falls back to the old localStorage presence check, so it's safe to ship.)

**(c) Data calls — `_hdrs()` / fetch in `terminal.html` + `live.html`** — let the cookie ride along:
```js
// BEFORE: function fetchJSON(url){return fetch(url,{headers:_hdrs()})...}
// AFTER:  function fetchJSON(url){return MrktAuth.authedFetch(url)...}   // adds credentials:'include' (+ legacy headers during migration)
```
Keep the existing 401→`needAuth('signin')` / 402→`needAuth('subscribe')` handling unchanged.

**(d) Logout — `account.html`** — revoke server-side and clear everything (fixes the "code user can't sign out" bug):
```js
document.getElementById('signout').onclick=function(){ MrktAuth.logout('index.html'); };
```

Also: delete the **vestigial Supabase block** in `account.html` (the hardcoded `SUPABASE_URL`/`SUPABASE_ANON`,
the `createClient`, and the `getSession()` token-write) unless you intend to implement email login — it writes
`mrkt.token` to localStorage and currently does nothing useful. If you keep Supabase email login later, route it
through the same `/auth/session` BFF (post the Supabase tokens to mint the cookie) rather than persisting them.

---

## The 7 tests (do all, on the branch, before merge)

1. **Login** → DevTools ▸ Application ▸ Cookies: `__Host-mrkt_sess` present, `HttpOnly ✓ Secure ✓ SameSite=None`.
2. **No credential in web storage** → Application ▸ Local Storage shows no `mrkt.code` / `mrkt.token`; console
   `document.cookie` does **not** show `__Host-mrkt_sess` (proves HttpOnly).
3. **Protected data loads** while logged in (board, cone) via the cookie.
4. **`/auth/me`** returns `{authenticated:true, subscribed:…}`; the gate keeps you on the page.
5. **Logout** → cookies cleared, a subsequent data call returns 401 and the page bounces to login.
6. **401 / 402** still behave (invalid session → 401 prompt; valid but unsubscribed → 402 prompt).
7. **Cross-origin credentials** → Network tab shows `Access-Control-Allow-Credentials: true` and the request
   carries the cookie; an off-allowlist `Origin` is rejected (403).

## Rollback
It's all on a branch + an isolated set of API endpoints. If anything misbehaves: revert the site branch (the
old localStorage gate returns), and the API keeps serving via the legacy header path (dual-read) so nobody is
locked out. Roll the API back to the prior deploy if needed.

## After it's stable (1–2 weeks of clean cookie traffic)
- Remove the legacy `X-Access-Code`/`Bearer` branch from `requireAuth` and the localStorage fallbacks from
  `auth_client.js`.
- Flip the security lint to blocking: `node tools/check-localstorage-auth.mjs --strict` (wire it into
  `run-checks.sh` without the `|| true`) so a regression can never reintroduce a token in web storage.
- (Optional) upgrade the signed-token session to an opaque-session table for instant revocation + "sign out
  all devices".
