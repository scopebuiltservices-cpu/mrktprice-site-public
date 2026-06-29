# Runbook — Sector-Rotation / data-collapse / deploy-lag

This documents the **2026-06-28 failure** (the universe collapsed to the Dow-30, every equity sector became
`Unknown`, `sectorCorr` went empty → the Sector × factor grid drew no rows) and the **defense-in-depth mesh**
that now prevents it from shipping silently.

## What "healthy" means
A published `marketmap.json` must have: ≥80 names, ≥8 GICS-sectored equities, a non-empty `sectorCorr`,
fresh `asof`, a non-SAMPLE source, and no >30% name-count drop vs the previous published build.
The single source of truth for these checks is `tools/market_map/sector_integrity.py`.

## The layers (each independently catches the failure)
1. **Universe collapse-seed** (`universe_fetch.py`): if the live index fetch yields < `UNIVERSE_MIN` (60)
   equities, the committed `data/universe_seed.json` is substituted — the build never shrinks to ~30 names.
2. **Sector seed** (`data/profile.json` + `sector_seed.py`): authoritative GICS sectors applied at build
   start, keyless, so sectors resolve even with FMP down.
3. **Producer gate 1 — publish_guards.py**: blocks publish on collapse/regression/SAMPLE/thin/stale.
4. **Producer gate 2 — validate_payload.py** (V7/V8): the contract gate, same invariants.
5. **Producer gate 3 — qa_signoff.py** (`sector-integrity` hard check): the release gate.
6. **Self-refreshing seeds** (`make_seeds.py`): after each *healthy* build, regenerates `universe_seed.json`
   and gap-fills `profile.json` so the fallback never goes stale. Refuses to write from an unhealthy build.
7. **Live monitor** (`healthcheck.yml`): daily, fails (red-X email) if the *deployed* file has no sectors
   or an empty `sectorCorr` — even if a bad build somehow slipped through.
8. **Deploy-staleness** (`deploy_staleness.py` in `healthcheck.yml`): fails if the deployed `asof` lags the
   repo by >1 day (a push that did not deploy).
9. **Graceful UI** (`marketmap.html`): the grid/correlation views show "Sector data unavailable — awaiting
   a fresh build" instead of a silent blank, and can no longer crash on a missing `sectorCorr`.

## If the grid is empty on the live site
1. `curl -s https://www.mrktprice.com/marketmap.json | python3 -c "import json,sys; d=json.load(sys.stdin); \
   print('asof',d['asof'],'names',len(d['names']),'sectored',sum(1 for n in d['names'] if n.get('sec') in \
   {'Technology','Financials','Health Care','Consumer Disc.','Communication','Industrials','Consumer Staples', \
   'Energy','Utilities','Materials','Real Estate'}),'corr',len((d.get('sectorCorr') or {}).get('order') or []))"`
2. If `asof` is old → the deploy is stale: re-run the **pages** workflow (or push with `[rebuild]`).
3. If `sectored` is 0 on a *fresh* build → the seeds are missing/stale: confirm `data/universe_seed.json`
   and `data/profile.json` are committed, then re-run.
4. If FMP is the root cause → `python tools/market_map/fmp_healthcheck.py` prints the exact reason; refresh
   the `FMP_API_KEY` repo secret if it says the key is invalid. The grid does **not** depend on FMP.

## Run all guardrail tests
`bash tools/market_map/verify_guardrails.sh`
