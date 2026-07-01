"""auth_bff_fastapi.py — FastAPI drop-in for the cookie (BFF) auth migration. Python port of
auth_bff_reference.js. Copy into your Render data-API service and wire the two TODO functions.

Moves the access code out of the browser's localStorage (readable by any XSS) into an HttpOnly cookie.
Adds the things a naive cookie swap misses: CORS-with-credentials, an Origin/CSRF defense (mandatory once
cookies are SameSite=None cross-site: Pages ↔ Render), a server-truth /auth/me gate, and DUAL-READ so
already-logged-in users (still on localStorage) aren't locked out during rollout.

The session cookie is a short-lived HMAC-SIGNED token {codeHash, subscribed, exp} — the RAW code never
enters the cookie (only its hash), so it's tamper-proof, stateless, and needs no DB. For instant revocation
/ "sign out everywhere", swap the signed token for an opaque id + a sessions table (see the note at bottom).

MOUNT (in your FastAPI app):
    from auth_bff_fastapi import router as auth_router, require_auth, add_cors
    add_cors(app)                       # CORS with credentials, exact-origin echo
    app.include_router(auth_router)     # POST /auth/session, GET /auth/me, POST /auth/logout
    # protect data routes (dual-read cookie OR legacy header):
    @app.get("/history", dependencies=[Depends(require_auth)])
    async def history(...): ...
    # (or) async def history(auth = Depends(require_auth)):  # auth = {"ok":True,"subscribed":...,"via":...}

ENV on Render:
    MRKT_SESSION_SECRET   = openssl rand -base64 32     (REQUIRED)
    MRKT_ALLOWED_ORIGINS  = https://mrktprice.com,https://www.mrktprice.com
    MRKT_SESSION_TTL      = 86400                        (optional, seconds)

The crypto core is pure stdlib and unit-tested (test_auth_bff_fastapi.py) without needing FastAPI installed.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

# ---- config -----------------------------------------------------------------------------------------
SECRET = os.environ.get("MRKT_SESSION_SECRET", "")
TTL = int(os.environ.get("MRKT_SESSION_TTL", "86400"))
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get(
    "MRKT_ALLOWED_ORIGINS", "https://mrktprice.com,https://www.mrktprice.com,http://localhost:8000").split(",") if o.strip()]
SESS_COOKIE = "__Host-mrkt_sess"   # __Host- => must be Secure, Path=/, no Domain (host-locked)
UI_COOKIE = "mrkt_ui"              # non-secret render hint (JS-readable); carries NO credential
CSRF_COOKIE = "mrkt_csrf"


# ---- signed-token core (HMAC-SHA256) — pure stdlib, testable without FastAPI ------------------------
def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64u_dec(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload_b64):
    return _b64u(hmac.new(SECRET.encode(), payload_b64.encode(), hashlib.sha256).digest())


def mint_session(code, subscribed=False, email=None, ttl=None):
    payload = {
        "c": hashlib.sha256(str(code).encode()).hexdigest()[:32],   # code HASH, not the code
        "s": bool(subscribed),
        "e": email or None,
        "exp": int(time.time()) + (ttl or TTL),
    }
    p = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    return p + "." + _sign(p)


def verify_session(token):
    if not token or "." not in token:
        return None
    p, sig = token.split(".", 1)
    if not hmac.compare_digest(sig, _sign(p)):    # timing-safe
        return None
    try:
        payload = json.loads(_b64u_dec(p).decode())
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


# ---- CSRF / Origin defense (SameSite=None cookies are auto-sent cross-site) -------------------------
def origin_allowed(origin, referer=""):
    if origin:
        return origin in ALLOWED_ORIGINS
    if referer:
        return any(referer.startswith(a) for a in ALLOWED_ORIGINS)
    return False


def auth_from_request_headers(cookies, x_access_code=None, authorization=None):
    """Dual-read: new cookie OR legacy X-Access-Code / Bearer (so nobody is locked out mid-rollout).
    Returns {ok, subscribed, via, code?, token?}. Subscription re-checked downstream for legacy paths."""
    p = verify_session(cookies.get(SESS_COOKIE) if hasattr(cookies, "get") else None)
    if p:
        return {"ok": True, "subscribed": bool(p.get("s")), "via": "cookie", "email": p.get("e")}
    if x_access_code:
        return {"ok": True, "subscribed": None, "via": "legacy-code", "code": x_access_code}
    if authorization and authorization.startswith("Bearer "):
        return {"ok": True, "subscribed": None, "via": "legacy-bearer", "token": authorization[7:]}
    return {"ok": False}


# ============================================================================================
#  TODO — replace these two with your EXISTING code-validation + subscription logic (the same
#  logic that already makes data calls return 401/402 today).
# ============================================================================================
async def validate_code(code):
    """Return True if `code` is a valid access code."""
    return bool(code)


async def subscription_status(code):
    """Return {'subscribed': bool, 'email': str|None} for a valid code."""
    return {"subscribed": True, "email": None}


# ---- FastAPI wiring (optional import so the crypto core stays testable without FastAPI) -------------
try:
    from fastapi import APIRouter, Request, Response, HTTPException, Depends  # noqa: F401
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel

    router = APIRouter()

    class _SessionBody(BaseModel):
        code: str

    def _set_cookies(resp, token):
        common = dict(max_age=TTL, secure=True, samesite="none", path="/")
        resp.set_cookie(SESS_COOKIE, token, httponly=True, **common)        # credential (JS can't read)
        resp.set_cookie(UI_COOKIE, "1", httponly=False, **common)           # render hint only
        resp.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(18), httponly=False, **common)

    def _clear_cookies(resp):
        for n in (SESS_COOKIE, UI_COOKIE, CSRF_COOKIE):
            resp.delete_cookie(n, path="/")

    def _origin_ok(req):
        return origin_allowed(req.headers.get("origin", ""), req.headers.get("referer", ""))

    @router.post("/auth/session")
    async def post_session(body: _SessionBody, request: Request, response: Response):
        if not _origin_ok(request):
            raise HTTPException(status_code=403, detail="bad origin")
        code = (body.code or "").strip()
        if not code or not await validate_code(code):
            raise HTTPException(status_code=401, detail="invalid code")
        sub = await subscription_status(code)
        _set_cookies(response, mint_session(code, sub.get("subscribed"), sub.get("email")))
        return {"ok": True, "subscribed": bool(sub.get("subscribed")), "email": sub.get("email")}

    @router.get("/auth/me")
    async def get_me(request: Request):
        p = verify_session(request.cookies.get(SESS_COOKIE))
        if p:
            return {"authenticated": True, "subscribed": bool(p.get("s")), "email": p.get("e")}
        return {"authenticated": False, "subscribed": False}

    @router.post("/auth/logout")
    async def post_logout(response: Response):
        _clear_cookies(response)      # (opaque-session variant: also delete the session row here)
        return {"ok": True}

    async def require_auth(request: Request):
        """Gate for data endpoints. 401 = no auth, 402 = no subscription (unchanged contract)."""
        if not _origin_ok(request):
            raise HTTPException(status_code=403, detail="bad origin")
        a = auth_from_request_headers(request.cookies,
                                      request.headers.get("x-access-code"),
                                      request.headers.get("authorization"))
        if not a["ok"]:
            raise HTTPException(status_code=401, detail="sign in required")
        if a.get("subscribed") is False:
            raise HTTPException(status_code=402, detail="subscription required")
        return a

    def add_cors(app):
        app.add_middleware(
            CORSMiddleware,
            allow_origins=ALLOWED_ORIGINS,      # exact list — never "*" with credentials
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token", "Authorization", "X-Access-Code"],
        )

except ImportError:      # FastAPI not installed (e.g. running the stdlib crypto tests) — router is optional
    router = None
    require_auth = None
    add_cors = None

# Opaque-session upgrade (for instant revocation / sign-out-all-devices): instead of the signed token,
# store secrets.token_urlsafe() as the cookie value, keyed to a `sessions` row {token, code_hash,
# subscribed, exp, created_at}; verify by lookup, and DELETE the row on /auth/logout.
