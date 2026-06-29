#!/usr/bin/env python3
"""sec_forms.py — KEYLESS SEC EDGAR event ingestion (8-K, 13D/13G, Form 3/4/5).

Reads the free EDGAR submissions API (https://data.sec.gov/submissions/CIK##########.json) for each
universe CIK, extracts the recent filing EVENT STREAM (form type, filing date, 8-K item codes, accession),
scores each event's severity (event_engine), and computes a current event-intensity per name. The dated
events feed the terminal CALENDAR/timeline + the research brief; the intensity + severities feed the
numeric event tilt. Network fetch runs ONLY in CI; parsers are pure + offline-tested. Research only.

Emits sec_events.json:  {ticker: {events:[{form,date,items,sev}], intensity, last:{...}, n8k, n13d, n13g, nins}}
"""
import argparse, json, os, sys, datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import event_engine as EV

UA = {"User-Agent": "MrktPrice marketmap/1.0 (research; contact scopebuiltservices@gmail.com)"}
TRACKED = {"8-K", "SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A", "3", "4", "5"}
# per-form base severity for non-8-K forms (8-K uses item-code severity)
FORM_SEV = {"SC 13D": 0.85, "SC 13D/A": 0.6, "SC 13G": 0.4, "SC 13G/A": 0.3, "3": 0.35, "4": 0.45, "5": 0.3}


def _items_list(s):
    """EDGAR 8-K items field is a comma/newline list like '2.02,9.01' or 'Item 2.02, Item 9.01'."""
    if not s:
        return []
    out = []
    for tok in str(s).replace("\n", ",").split(","):
        tok = tok.replace("Item", "").strip()
        if tok:
            out.append(tok)
    return out


def events_from_submissions(sub, since=None, today=None):
    """Parse the EDGAR submissions JSON -> list of events (newest first) within `since` days.
    Each: {form, date 'YYYY-MM-DD', dateInt yyyymmdd, items[list], sev, accession}."""
    today = today or dt.date.today()
    rec = (sub.get("filings") or {}).get("recent") or {}
    forms = rec.get("form") or []
    dates = rec.get("filingDate") or []
    items = rec.get("items") or [""] * len(forms)
    accs = rec.get("accessionNumber") or [""] * len(forms)
    out = []
    for i in range(len(forms)):
        f = (forms[i] or "").strip()
        if f not in TRACKED:
            continue
        try:
            d = dt.date.fromisoformat(dates[i][:10])
        except Exception:
            continue
        if since is not None and (today - d).days > since:
            continue
        it = _items_list(items[i] if i < len(items) else "")
        sev = EV.eightk_severity(it) if f == "8-K" else FORM_SEV.get(f, 0.3)
        out.append({"form": f, "date": d.isoformat(), "dateInt": int(d.strftime("%Y%m%d")),
                    "items": it, "sev": round(sev, 3),
                    "accession": (accs[i] if i < len(accs) else "")})
    out.sort(key=lambda e: e["dateInt"], reverse=True)
    return out


def summarize(events, today=None, tau=10.0):
    """Roll the event stream into the per-name summary block (counts + decayed intensity)."""
    today = today or dt.date.today()
    if not events:
        return {"events": [], "intensity": 0.0, "last": None, "n8k": 0, "n13d": 0, "n13g": 0, "nins": 0}
    # intensity uses trading-day-ish age in days/ (7/5) to approximate trading days
    pairs = []
    for e in events:
        try:
            age_cal = (today - dt.date.fromisoformat(e["date"])).days
        except Exception:
            continue
        age_td = age_cal * 5.0 / 7.0
        pairs.append((-age_td, e["sev"]))      # t_e = -age (relative), t_now=0
    intensity = EV.event_intensity(pairs, 0.0, tau=tau)
    n8k = sum(1 for e in events if e["form"] == "8-K")
    n13d = sum(1 for e in events if e["form"].startswith("SC 13D"))
    n13g = sum(1 for e in events if e["form"].startswith("SC 13G"))
    nins = sum(1 for e in events if e["form"] in ("3", "4", "5"))
    return {"events": events[:20], "intensity": round(intensity, 4), "last": events[0],
            "n8k": n8k, "n13d": n13d, "n13g": n13g, "nins": nins}


def fetch_company(cik, sess=None, timeout=20):
    """CI-only: GET the EDGAR submissions JSON for a zero-padded 10-digit CIK."""
    import requests
    s = sess or requests.Session()
    url = "https://data.sec.gov/submissions/CIK%010d.json" % int(cik)
    r = s.get(url, headers=UA, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError("submissions %s -> %s" % (url, r.status_code))
    return r.json()


def build(cik_map, since=400, sleep=0.12):
    """cik_map: {ticker: cik}. Returns {ticker: summary}. CI-only (network)."""
    import requests, time
    s = requests.Session()
    out = {}
    for tk, cik in cik_map.items():
        if not cik:
            continue
        try:
            sub = fetch_company(cik, s)
            out[tk] = summarize(events_from_submissions(sub, since=since))
        except Exception as ex:
            sys.stderr.write("sec_forms: %s (cik %s) failed: %s\n" % (tk, cik, str(ex)[:70]))
        time.sleep(sleep)                      # be polite to EDGAR (<10 req/s)
    return out


def _load_cik_map(path, marketmap):
    """Prefer cik.json {ticker:cik}; else read CIKs embedded in marketmap names."""
    if path and os.path.exists(path):
        d = json.load(open(path))
        if isinstance(d, dict):
            return {k: v for k, v in d.items() if not k.startswith("_")}
    cm = {}
    try:
        mm = json.load(open(marketmap))
        for n in mm.get("names", []):
            if n.get("t") and n.get("cik"):
                cm[n["t"]] = n["cik"]
    except Exception:
        pass
    return cm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cik", default="cik.json")
    ap.add_argument("--marketmap", default="marketmap.json")
    ap.add_argument("--out", default="sec_events.json")
    ap.add_argument("--since", type=int, default=400)
    a = ap.parse_args()
    cm = _load_cik_map(a.cik, a.marketmap)
    if not cm:
        sys.stderr.write("sec_forms: no CIK map (need cik.json or marketmap names with cik) — skipped\n")
        return 0
    res = build(cm, since=a.since)
    res["_meta"] = {"asof": dt.date.today().isoformat(), "names": len([k for k in res if not k.startswith("_")]),
                    "source": "SEC EDGAR submissions (free)", "since_days": a.since}
    tmp = a.out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(res, f, separators=(",", ":"))
    os.replace(tmp, a.out)
    sys.stderr.write("sec_forms: wrote %s for %d names\n" % (a.out, res["_meta"]["names"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
