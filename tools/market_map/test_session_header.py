"""Regression guard for the InvalidHeader bug (deploy-degrading, silent).

A prior build did  `session.headers.update({"User-Agent": UA})`  where UA was ALREADY the dict
{"User-Agent": "..."} -> the header VALUE became a dict -> urllib3 raised InvalidHeader on every
request through that session -> the FMP price source, the EOD probe, universe_fetch and macro_keyless
all silently fell back to yfinance / committed seeds (this is what produced the "FMP Ultimate NOT
pulling" banner and the stale map). The correct pattern is `.update(UA)`.

This test locks the fix two ways: a static scan of the build for the dict-wrap anti-pattern, and a
runtime check that the canonical pattern yields a plain-string User-Agent header.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def test_no_dict_wrapped_user_agent_in_build():
    src = open(os.path.join(HERE, "build_market_map.py"), encoding="utf-8").read()
    # Flag  headers.update({"User-Agent": <bare identifier>})  -- a bare name here is a variable
    # (in this codebase UA is a dict), i.e. the double-wrap bug. A string literal value starts with
    # a quote and is NOT matched, so the correct inline `{"User-Agent": "..."}` form is allowed.
    bad = re.findall(r'headers\.update\(\s*\{\s*["\']User-Agent["\']\s*:\s*([A-Za-z_]\w*)', src)
    assert not bad, "dict-wrapped User-Agent header in build_market_map.py (InvalidHeader regression): %r" % bad
    print("  PASS  no dict-wrapped User-Agent header in build_market_map.py")


def test_canonical_pattern_yields_str_user_agent():
    try:
        import requests
    except Exception:
        print("  SKIP  requests not installed"); return
    UA = {"User-Agent": "MrktPrice marketmap/1.0 (research; contact scopebuiltservices@gmail.com)"}
    s = requests.Session()
    s.headers.update(UA)                       # the CORRECT pattern (not {"User-Agent": UA})
    assert isinstance(s.headers["User-Agent"], str), type(s.headers["User-Agent"])
    print("  PASS  canonical .update(UA) yields a plain-string User-Agent")


if __name__ == "__main__":
    test_no_dict_wrapped_user_agent_in_build()
    test_canonical_pattern_yields_str_user_agent()
    print("ALL test_session_header PASS")
