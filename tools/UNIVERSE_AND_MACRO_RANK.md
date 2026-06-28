# Bull/Bear ranking: full macro complex + full Nasdaq/Dow universe

Two changes, answering "are rates/commodities factored completely and correctly?" and "why only ~155 names?".

## 1. Rates & commodities now FULLY factor into the rank

**Before:** the board's macro tilt dotted each name's betas against only **4** drivers
(`OIL, DXY, RATE, VIX`). Rate used a crude **TLT-price proxy**; ~26 other commodities (gold, copper,
nat-gas, silver, ags…) and the **real-rate curve** were computed but **display-only** — they never moved the rank.

**Now:** `macro_tilt.js` (verified port of `tools/market_map/macro_tilt.py`, locked by
`tools/test_macro_parity.mjs`) computes the full contribution:

- **All commodities + DXY + VIX** via each name's **partial multivariate-Lasso betas** `n.mb`
  (already computed in `build_market_map.py`) dotted against the latest move of **every** macro driver.
  The pipeline emits those moves as `marketmap.json.factorMoves` (one per macro factor, same units the
  betas were fit on).
- **Real-rate curve** via the Diebold-Li **level/slope/curvature duration betas** `n.rate` (from
  `rate_real.py`, fit against the **real** yields DFII5/10/30) dotted against the recent real-curve moves
  `marketmap.json.realCurve.{dL,dS,dC}`. When the real curve is present the nominal `RATE` factor is
  dropped so rates are counted once (no double-count); otherwise nominal RATE is the fallback.

The board calls `MrktMacro.combinedTilt(mb, factorMoves, n.rate, realCurve)`; it falls back to the legacy
4-factor dot only for old payloads without `factorMoves`. The tilt is then z-scored cross-sectionally and
enters alpha exactly as before, so every commodity and the real-rate curve now drive Bull/Bear placement.

Verified: `test_macro_tilt.py` (planted structure), `test_macro_parity.mjs` (Py↔JS 1e-9), and a board
behavioral check showing copper/gold/nat-gas/real-rate contributions that the legacy path ignored.

## 2. Universe = full Nasdaq Composite + Dow 30 (was a hardcoded 92-name SEED)

The "~155" was `len(SEED)=92` equities + 64 factor-ETF nodes; the index-constituent fetch was a dead stub.

`tools/market_map/universe_fetch.py` now builds the equity universe from:
- **FMP company-screener** (primary) — every actively-trading **NASDAQ** common stock, ETFs/funds
  excluded, returned **market-cap-sorted** with sector.
- **Nasdaq Trader `nasdaqlisted.txt`** (keyless fallback) if the screener is unavailable.
- **Dow 30** merged in (fixed list; many are NYSE-listed).

Wired into `real_universe()`; controlled by env:
- `UNIVERSE_MODE` = `nasdaq_full` (default) | `seed` (legacy 92).
- `UNIVERSE_LIMIT` = optional integer throttle (0/unset = the entire composite, ~3,000+ names; Dow always kept).
- `DOW30` = optional comma-separated override.

Any fetch failure falls back to SEED, so the build never breaks.

### Coverage & cost note (honest degradation)
Every name in the universe gets: price history → returns/vol/beta, **macro betas (rate + all
commodities)**, technicals, opportunity score, and a **Bull/Bear ranking**. That is the full analysis the
board ranks on.

The **enrichment** pulls stay capped to the most liquid names by market cap (they're supplementary, not
ranking inputs, and pulling them for 3,000 names nightly is impractical / rate-limited):
`OPT_LIMIT` (options chains, default 40), `twelvedata_ivol` (implied vol, 40), `finnhub_beat` (earnings
beats, 60). Raise via env if desired. Expect a longer nightly build and higher FMP usage at full size;
use `UNIVERSE_LIMIT` to throttle.

## Files
- `macro_tilt.js`, `tools/market_map/macro_tilt.py`, `tools/market_map/test_macro_tilt.py`,
  `tools/test_macro_parity.mjs`, `tools/macro_golden.json`
- `tools/market_map/universe_fetch.py`, `tools/market_map/test_universe_fetch.py`
- edits: `tools/market_map/build_market_map.py` (factorMoves emit + universe wiring), `terminal.html`
  (full-complex tilt + `macro_tilt.js` include)
