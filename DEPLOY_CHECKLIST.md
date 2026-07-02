# Go‑live checklist — push this session's fixes in the right order

Everything below is already in your working tree. Follow in order; do not skip the `verify` gate.

## 0. (optional) Local sanity — one command
```
bash tools/verify_all.sh
```
Expect all green (py_compile + every test). No local env? Skip — CI runs the same gate in step 2.

## 1. Commit — ALL changed files, in ONE commit (GitHub Desktop)
Stage every changed/new file. **Critical pairing:** the new root scripts must be committed *together with* `terminal.html`, or the `<script src>` tags 404 on the live site:
- New (root): `fib_engine.js`, `fib_panel.js`, `macro_tilt.js`, `harq_engine.js`
- Edited: `terminal.html`, `bullbear_controls.js`, `tools/market_map/build_market_map.py`
- **Calibration upgrade — commit TOGETHER (the terminal calls the engine; a half-commit mixes old+new):**
  `lineage.js` (root), `tools/market_map/lineage.py`, `tools/market_map/test_lineage.py`.
  These replace the interval calibration with studentized **asymmetric split-conformal** coverage under an
  **H-embargo** (purged train/test), add **GARCH + empirical-HV** challenger arms, and route the terminal
  cone scorecard through `MrktLineage.calibrateHorizon` so the band coverage-tested is the asymmetric band drawn.
- New (tools): `universe_fetch.py`, `macro_keyless.py`, `macro_tilt.py`, `drift_calib.py/2/3`,
  `flow_keyless.py`, `price_cache.py`, `universe_smoke.py`, `harq_regime.py`, plus their `test_*.py`,
  the `tools/*_golden.json` fixtures and `tools/test_*_parity.mjs`.

**Commit message must contain `[rebuild]`** so the data build runs, e.g.:
```
Drift cone + HARQ rebuild + full universe + keyless macro/flow + freshness fixes [rebuild]
```

## 2. Push → watch GitHub → Actions
1. **`verify`** job → must be **GREEN** (compiles the monolith + runs all tests on a clean FS). If red, open the failing test name, fix, re‑push. This is the authoritative check.
2. **`Build + publish MrktPrice`** (pages.yml) → regenerates `marketmap.json` + `hist/` + publishes the site.

## 3. Secrets / variables (one‑time, repo Settings → Secrets and variables → Actions)
- **Secret `FMP_ULTIMATE_API_KEY`** — required for the full universe + prices + earnings/valuation.
- Optional secrets: `FRED_API_KEY`, `EODHD_API_KEY`, `ALPACA_*` (macro/flow/short already work keyless).
- **First rebuild only:** set a **variable `UNIVERSE_LIMIT=1200`** so the ~4–5k‑name build finishes inside the
  Action time budget. Confirm it completes green, then remove it (or raise) for the full set.
- `UNIVERSE_MODE` already defaults to `all` (S&P 500 + full Nasdaq + Dow + Russell 2000).

## 4. Confirm the data is current + complete
Run `tools/market_map/universe_smoke.py` (via Actions, or locally with the key):
```
python3 tools/market_map/universe_smoke.py
```
Expect **CORE RANKING DATA: READY ✓**. If S&P/Dow constituents show MISS, your FMP plan doesn't include
those endpoints — tell me and I'll switch them to a keyless source.

## 5. See the changes live
After the build + Pages deploy finish (a few minutes):
- **Hard‑refresh** the site: **Ctrl+Shift+R** (drops the cached old HTML).
- Click the **⟳ refresh** button to freshen any saved watchlist tickers.

## 6. Verify on the live site
- **Cone tilts** (no longer flat at spot); the **Central drift** tile shows OU/EMA blend or `calibrated` mode.
- **Regime tile** sits in its own box **below the chart** (no longer overlapping the price line); panes are
  larger; **VOL · RVOL** is bold.
- **Bull/Bear** shows "**showing X of Y companies**"; if a HIGH conviction filter is hiding rows, click that
  indicator to show all.
- **Header "as of"** is green/fresh; the **Macro‑betas** and **Flow** coverage tiles are populated.

## 7. (optional governance) make `verify` a required check
Settings → Branches → branch protection → Require status checks → select **verify**
(see `tools/BRANCH_PROTECTION.md`). Then a red gate physically blocks a bad merge.

---
### If `verify` fails on the integrity tripwire (hash drift from this session's edits)
Re‑seed the manifest once and commit it:
```
python3 tools/market_map/integrity_manifest.py --write
```
This is a SOFT drift (expected after editing tracked files), not a code defect.
