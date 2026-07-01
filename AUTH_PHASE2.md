# Auth Phase 2 — remove the credential from localStorage (the actual security win)

**Precondition: do NOT run this until Phase 1 cookies are verified live** (the 7-point test in
`AUTH_MIGRATION.md` passes: login sets `__Host-mrkt_sess` HttpOnly, `/auth/me` returns authenticated,
data loads, logout clears it). Until then the localStorage write is the working fallback — removing it
early logs everyone out.

Phase 1 (already applied) made the pages **cookie-ready** but still writes `mrkt.code` to localStorage so
nothing breaks before the backend exists. Phase 2 removes that write, so the access code lives **only** in
the HttpOnly cookie — which is the whole point (XSS can no longer read it).

## The three edits

### 1–2. Stop writing the code to localStorage (`index.html` + `login.html`)
In each file's `enter()`, the line currently is:
```js
try{localStorage.setItem('mrkt.code',c);localStorage.removeItem('mrkt.token');}catch(e){}
```
Change it to (drops the `setItem`, and clears any legacy code so old sessions migrate to the cookie):
```js
try{localStorage.removeItem('mrkt.token');localStorage.removeItem('mrkt.code');}catch(e){}
```
The cookie-mint `fetch('/auth/session',…)` line right below it stays — that's now the *only* thing that
authenticates. (The `.catch()` can be tightened to show an error on a non-200 if you want a hard failure
on a bad code; optional.)

One-liner (run from the repo root on your machine, in Git Bash / WSL):
```sh
sed -i "s/try{localStorage.setItem('mrkt.code',c);localStorage.removeItem('mrkt.token');}catch(e){}/try{localStorage.removeItem('mrkt.token');localStorage.removeItem('mrkt.code');}catch(e){}/" index.html login.html
```

### 3. Flip the security lint to blocking (`tools/run-checks.sh`)
Currently advisory:
```sh
echo "==> security   Web-storage auth lint (advisory ...)"
node tools/check-localstorage-auth.mjs || true
```
Make it a hard gate so a regression can never reintroduce a token/code in web storage:
```sh
echo "==> security   Web-storage auth lint (blocking: no auth credential in web storage)"
node tools/check-localstorage-auth.mjs --strict || fail=1
```

## Optional Phase-2 hardening (nice, not required)
- **Gate:** drop the localStorage fallback from the inline `/*mrkt-gate*/` on the protected pages and rely
  on the `mrkt_ui` hint cookie only (the `document.cookie.indexOf('mrkt_ui=')>=0` term stays; remove the
  `localStorage.getItem('mrkt.code')||localStorage.getItem('mrkt.ok')||` terms). Keeps the credential out
  of JS entirely.
- **Data fetch:** once no client relies on the header, remove the legacy `X-Access-Code`/`Bearer` branch
  from the API's `requireAuth` (auth_bff_reference.js) so only the cookie is accepted.
- **CSP quick-win:** add the `Content-Security-Policy` `<meta>` from `AUTH_HARDENING.md` to further shrink
  the XSS surface that the cookie already defends against.

## Verify after Phase 2
1. `sh tools/run-checks.sh` — the web-storage lint step now PASSES (0 offenders) and is blocking.
2. Live: log in, then in DevTools ▸ Application ▸ Local Storage there is **no** `mrkt.code` / `mrkt.token`;
   `document.cookie` does not show `__Host-mrkt_sess` (HttpOnly); the terminal still loads data.
3. Logout clears cookies and a data call 401s.
