#!/usr/bin/env python3
"""Tests for auth_bff_fastapi.py crypto core (signed session cookie) — no FastAPI needed.
Run: python3 test_auth_bff_fastapi.py"""
import os, sys
os.environ.setdefault("MRKT_SESSION_SECRET", "test-secret-0123456789abcdef0123456789ab")
os.environ.setdefault("MRKT_ALLOWED_ORIGINS", "https://mrktprice.com,http://localhost:8000")
# module lives at the repo root (it's copied into the Render API); import it from three levels up.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import auth_bff_fastapi as A

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# signed-token round-trip
tok = A.mint_session("ABC123", subscribed=True, email="a@b.c")
p = A.verify_session(tok)
ok("valid token verifies", p is not None and p["s"] is True and p["e"] == "a@b.c", p)
ok("raw code is NOT in the token (only its hash)", "ABC123" not in tok, tok)
ok("tampered signature -> None", A.verify_session(tok[:-3] + "xxx") is None)
ok("garbage -> None", A.verify_session("not.a.token") is None and A.verify_session("") is None and A.verify_session(None) is None)
ok("expired token -> None", A.verify_session(A.mint_session("X", ttl=-10)) is None)
ok("codeHash differs for different codes", A.verify_session(A.mint_session("AAA"))["c"] != A.verify_session(A.mint_session("BBB"))["c"])

# origin / CSRF defense
ok("allowed origin accepted", A.origin_allowed("https://mrktprice.com") is True)
ok("evil origin rejected", A.origin_allowed("https://evil.com") is False)
ok("no origin, allowed referer prefix accepted", A.origin_allowed("", "https://mrktprice.com/terminal.html") is True)
ok("no origin, no referer rejected", A.origin_allowed("", "") is False)

# dual-read auth (cookie OR legacy header)
class _CK(dict):
    pass
ck = _CK(); ck[A.SESS_COOKIE] = tok
a = A.auth_from_request_headers(ck)
ok("cookie path -> ok via cookie, subscribed", a["ok"] and a["via"] == "cookie" and a["subscribed"] is True, a)
a2 = A.auth_from_request_headers(_CK(), x_access_code="LEGACY9")
ok("legacy X-Access-Code accepted (dual-read)", a2["ok"] and a2["via"] == "legacy-code", a2)
a3 = A.auth_from_request_headers(_CK(), authorization="Bearer xyz")
ok("legacy Bearer accepted (dual-read)", a3["ok"] and a3["via"] == "legacy-bearer", a3)
a4 = A.auth_from_request_headers(_CK())
ok("no cookie/header -> not ok (401)", a4["ok"] is False, a4)

print("\n" + ("ALL AUTH-BFF-FASTAPI TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
