# Auth hardening runbook — move session tokens out of `localStorage`

**Problem (from the security audit):** the Supabase session (access + refresh JWT) is persisted in
`localStorage`. Anything that can run JavaScript on the page — a compromised CDN script, an XSS bug,
a malicious browser extension — can read `localStorage` and exfiltrate the token, which is full
account access until it expires. `HttpOnly` cookies are **not** readable from JavaScript, so the same
XSS can no longer steal the session.

**Why it needs care:** this changes how every page authenticates to the data API. Done wrong it locks
you (and users) out. Do it on a branch, test the full login→data→logout loop, and keep the rollback
ready. **Do not skip the testing steps.**

You have two paths. Do the **Quick win** today (low risk, ~30 min). Do the **Full fix** when you can
spend a focused hour and test properly.

---

## Quick win (do this first — low risk, big XSS reduction)

The token is only stealable if attacker JavaScript runs on your origin. A strict
**Content-Security-Policy** blocks almost all injected/inline script, which is the actual attack path.
This does **not** change auth, so there's no lockout risk.

1. Add a CSP `<meta>` to the `<head>` of **every** protected page (`terminal.html`, `marketmap.html`,
   `account.html`, etc.). Start in report-only to find breakage, then enforce:

   ```html
   <!-- 1) First deploy in REPORT-ONLY: logs violations to console, blocks nothing -->
   <meta http-equiv="Content-Security-Policy-Report-Only"
         content="default-src 'self';
                  script-src 'self' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net;
                  connect-src 'self' https://YOUR-RENDER-API.onrender.com https://YOUR-PROJECT.supabase.co;
                  style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none';
                  base-uri 'self'; object-src 'none'">
   ```

2. Open each page, use it fully (load charts, log in, open every panel), and watch the console for
   `Content-Security-Policy` violation reports. Add any **legitimate** origins you actually use to the
   right directive (e.g. another CDN). Remove anything you don't.

3. When the console is clean, switch `Content-Security-Policy-Report-Only` → `Content-Security-Policy`
   (enforcing). Commit + push.

   - If you rely on inline `<script>` blocks (you do — the terminal has them), keep `script-src 'self'`
     working by either (a) moving inline code into external `.js` files (best), or (b) adding a per-build
     nonce. Simplest now: keep the big inline blocks but ensure no **user-derived** string is ever
     injected into the DOM as HTML (use `textContent`, not `innerHTML`, for anything dynamic).

4. Add **Subresource Integrity** to CDN scripts so a tampered CDN file can't run:

   ```html
   <script src="https://cdnjs.cloudflare.com/.../chart.min.js"
           integrity="sha384-..." crossorigin="anonymous"></script>
   ```
   (Get the hash from cdnjs's "copy SRI" button.)

This alone removes the realistic path to reading `localStorage`. The Full fix below closes it
architecturally.

---

## Full fix — HttpOnly cookie session brokered by your Render API (BFF pattern)

A static GitHub Pages site can't set `HttpOnly` cookies (no server). But you already run a data API on
Render — make **it** the auth broker. The browser holds an opaque `HttpOnly` cookie; the API holds/uses
the Supabase tokens server-side.

### Step 1 — API: add three auth endpoints (Express shown; adapt to your framework)

```js
// cookie options used everywhere
const COOKIE = {
  httpOnly: true,
  secure: true,                 // HTTPS only
  sameSite: 'none',             // site (Pages) and API (Render) are different origins -> 'none' + secure
  domain: undefined,            // leave host-only; set a parent domain only if you serve both from it
  path: '/',
  maxAge: 1000 * 60 * 60 * 24 * 7
};

// POST /auth/session  — body: { access_token, refresh_token }  (from supabase.auth on the client AFTER login)
app.post('/auth/session', (req, res) => {
  const { access_token, refresh_token } = req.body || {};
  if (!access_token || !refresh_token) return res.status(400).json({ error: 'missing tokens' });
  // Optionally verify access_token with the Supabase JWKS here before trusting it.
  res.cookie('sb_at', access_token, { ...COOKIE, maxAge: 1000 * 60 * 60 });        // short-lived
  res.cookie('sb_rt', refresh_token, COOKIE);                                       // longer-lived
  res.json({ ok: true });
});

// POST /auth/logout — clears the cookies
app.post('/auth/logout', (req, res) => {
  res.clearCookie('sb_at', COOKIE); res.clearCookie('sb_rt', COOKIE);
  res.json({ ok: true });
});
```

Update your existing **data gate** to read the JWT from the cookie instead of (or in addition to) the
`Authorization` header, and to refresh using `sb_rt` when `sb_at` is expired:

```js
function getJwt(req) {
  return req.cookies?.sb_at || (req.headers.authorization || '').replace(/^Bearer /, '');
}
```

### Step 2 — API: CORS must allow credentials from your exact origin

```js
import cors from 'cors';
app.use(cors({
  origin: 'https://mrktprice.com',   // your EXACT site origin (no wildcard allowed with credentials)
  credentials: true
}));
app.use(require('cookie-parser')());
```

`Access-Control-Allow-Origin` **cannot be `*`** when credentials are sent — it must echo the one origin.

### Step 3 — Frontend: stop persisting tokens; hand them to the API once, then rely on the cookie

In your Supabase client init, disable local persistence:

```js
const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: { persistSession: false, autoRefreshToken: false, storage: undefined }
});
```

Right after a successful sign-in, POST the tokens to the API to mint the cookie, then drop them:

```js
const { data, error } = await supabase.auth.signInWithPassword({ email, password });
if (!error) {
  await fetch(`${API}/auth/session`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      access_token: data.session.access_token,
      refresh_token: data.session.refresh_token
    })
  });
  // do NOT write tokens anywhere; the HttpOnly cookie is now the session
}
```

Every data fetch uses the cookie automatically — just add `credentials: 'include'`:

```js
const r = await fetch(`${API}/marketmap`, { credentials: 'include' });
```

Logout:

```js
await fetch(`${API}/auth/logout`, { method: 'POST', credentials: 'include' });
```

### Step 4 — Remove the old storage

Delete every `localStorage.setItem('sb-...')` / `supabase.auth.token` read/write in `account.html`
and the login page. Grep for `localStorage` and `access_token` and remove auth uses (keep unrelated UI
prefs like `mrkt.antidev.on`).

---

## Test before you trust it (do all of these on the branch)

1. **Login** → DevTools ▸ Application ▸ Cookies: `sb_at`/`sb_rt` present, `HttpOnly ✓ Secure ✓ SameSite=None`.
2. DevTools ▸ Application ▸ Local Storage: **no** access/refresh token keys remain.
3. Console: `localStorage.getItem('sb_at')` (or whatever the old key was) returns `null`, and
   `document.cookie` does **not** show `sb_at` (proves HttpOnly).
4. **Protected data loads** (board, terminal cone) while logged in.
5. **Logout** clears cookies and a subsequent data call returns 401 / bounces to login.
6. **Refresh path:** let `sb_at` expire (or set `maxAge` to 60s temporarily) and confirm the API
   refreshes via `sb_rt` without forcing re-login.
7. **Cross-origin:** confirm the Network tab shows `Access-Control-Allow-Credentials: true` and the
   request carries the cookie.

## Rollback

It's all on a branch. If anything misbehaves, `git checkout main` on the site and redeploy the previous
commit; revert the API to the prior deploy on Render. Because the change is isolated to the auth/login
files + the API gate, rollback is clean.

## Order of operations

Quick-win CSP today → then the Full fix on a branch when you have an hour → test the 7 checks → merge →
deploy API first, then the site (so the cookie endpoints exist before pages call them).
