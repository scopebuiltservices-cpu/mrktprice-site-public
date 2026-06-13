#!/usr/bin/env python3
"""Build reports/index.html (the Opportunity News list page) from the report files in ./reports/.

Each report is a self-contained .html file with a metadata block near the top:

    <script type="application/json" id="report-meta">
    {"title":"...","date":"YYYY-MM-DD","summary":"...","tags":["a","b"],"author":"Marc Jones"}
    </script>

Run after adding/editing a report:   python build_reports.py
(The GitHub Pages workflow also runs this automatically on every push.)
No network, no dependencies, no fetch(): the list is baked in, so it works on the live site and locally.
"""
from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path

REPORTS = Path(__file__).resolve().parent / "reports"
SKIP = {"index.html", "report-template.html"}
META_RE = re.compile(
    r'<script[^>]*id=["\']report-meta["\'][^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)


def _fmt_date(iso: str) -> str:
    try:
        return date.fromisoformat(iso[:10]).strftime("%B %d, %Y").replace(" 0", " ")
    except Exception:
        return iso


def collect() -> list[dict]:
    items = []
    for f in sorted(REPORTS.glob("*.html")):
        if f.name in SKIP:
            continue
        m = META_RE.search(f.read_text(encoding="utf-8", errors="replace"))
        if not m:
            print(f"  skip {f.name}: no report-meta block")
            continue
        try:
            meta = json.loads(m.group(1).strip())
        except Exception as exc:
            print(f"  skip {f.name}: bad JSON ({exc})")
            continue
        meta["file"] = f.name
        meta.setdefault("date", "")
        meta.setdefault("title", f.name)
        meta.setdefault("summary", "")
        meta.setdefault("tags", [])
        meta.setdefault("author", "Marc Jones")
        items.append(meta)
    items.sort(key=lambda m: m.get("date", ""), reverse=True)
    return items


def card(m: dict) -> str:
    tags = "".join(f'<span class="tag">{html.escape(str(t))}</span>' for t in m.get("tags", []))
    return f"""      <a class="card" href="{html.escape(m['file'])}">
        <div class="card-date">{html.escape(_fmt_date(m.get('date','')))}</div>
        <div class="card-title">{html.escape(m.get('title',''))}</div>
        <div class="card-sum">{html.escape(m.get('summary',''))}</div>
        <div class="tags">{tags}</div>
      </a>"""


def render(items: list[dict]) -> str:
    cards = "\n".join(card(m) for m in items) if items else (
        '      <div class="empty">No reports yet. Copy <code>report-template.html</code>, '
        'fill it in, and run <code>python build_reports.py</code>.</div>')
    built = date.today().isoformat()
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Opportunity News · MrktPrice</title>
<meta name="description" content="Opportunity News — general, impersonal market-analysis notes from MrktPrice. Not investment advice.">
<style>
  :root{{--bg:#0a0d12;--panel:#111721;--line:#27313f;--ink:#eef3f8;--muted:#97a4b3;
        --faint:#646e7c;--accent:#16c79a;--brand:#16c79a;--gold:#f5c451;}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--ink);
       font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}}
  .wrap{{max-width:820px;margin:0 auto;padding:30px 22px 64px}}
  .top{{display:flex;align-items:center;justify-content:space-between;gap:12px;
       border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:8px}}
  .brand{{font-weight:800;font-size:19px;letter-spacing:.2px}}
  .brand b{{color:var(--brand)}} .brand span{{color:var(--muted);font-weight:600}}
  a.back{{color:var(--muted);text-decoration:none;font-size:13px;border:1px solid var(--line);
         padding:6px 11px;border-radius:7px}}
  a.back:hover{{color:var(--ink);border-color:var(--accent)}}
  .lead{{color:var(--muted);font-size:14.5px;margin:18px 0 26px;max-width:60ch}}
  .grid{{display:flex;flex-direction:column;gap:14px}}
  a.card{{display:block;text-decoration:none;color:inherit;background:var(--panel);
         border:1px solid var(--line);border-radius:12px;padding:18px 20px;transition:border-color .15s}}
  a.card:hover{{border-color:var(--accent)}}
  .card-date{{color:var(--faint);font-size:12px;text-transform:uppercase;letter-spacing:.6px}}
  .card-title{{font-size:19px;font-weight:700;margin:5px 0 7px;color:var(--ink)}}
  .card-sum{{color:var(--muted);font-size:14.5px;line-height:1.55}}
  .tags{{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}}
  .tag{{font-size:11px;color:var(--accent);border:1px solid var(--line);border-radius:20px;padding:2px 9px;
       text-transform:uppercase;letter-spacing:.5px}}
  .empty{{color:var(--muted);background:var(--panel);border:1px dashed var(--line);border-radius:12px;
         padding:26px;text-align:center}}
  .empty code{{color:var(--accent)}}
  .disclaimer{{margin-top:36px;padding:15px 18px;background:var(--panel);border:1px solid var(--line);
              border-radius:10px;font-size:12.5px;color:var(--muted);line-height:1.6}}
  footer{{margin-top:22px;color:var(--faint);font-size:12px}}
</style>
</head>
<body>
<div class="wrap">

  <div class="top">
    <div class="brand"><b>Mrkt</b><span>Price</span> · Opportunity&nbsp;News™</div>
    <a class="back" href="../index.html">← Dashboard</a>
  </div>

  <p class="lead">General, impersonal market-analysis notes — results and observations from the
  MrktPrice research engine. Newest first. <strong>Not investment advice.</strong></p>

  <div class="grid">
{cards}
  </div>

  <div class="disclaimer">
    <strong>Not investment advice.</strong> Opportunity News is a general, impersonal market-analysis
    publication for research and educational purposes only — not financial, investment, legal, or tax
    advice, and not a recommendation to buy or sell any security. Data may be delayed, incomplete, or
    inaccurate.
  </div>
  <footer>© 2026 MrktPrice™ / Marc Jones. All rights reserved. · Built {built} · {len(items)} report(s).</footer>

</div>
</body>
</html>
"""


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    items = collect()
    (REPORTS / "index.html").write_text(render(items), encoding="utf-8")
    print(f"Built reports/index.html with {len(items)} report(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
