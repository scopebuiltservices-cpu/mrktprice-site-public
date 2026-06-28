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

## 2. Universe = S&P 500 + full Nasdaq + Dow 30 + Russell 2000 (was a hardcoded 92-name SEED)

The "~155" was `len(SEED)=92` equities + 64 factor-ETF nodes; the index-constituent fetch was a dead stub.

`tools/market_map/universe_fetch.py` now unions the **real membership of all four indices**, each from its
best free/credible source, and tags every name with the indices it belongs to (`S`/`ND`/`D`/`R` →
NDX/DOW/SPX/RUT via `membership()`), so a name in several indices accumulates several tags (e.g. AAPL = `S ND D`):

- **S&P 500** — FMP `sp500-constituent` (stable; v3 `sp500_constituent` fallback). This is what adds the
  ~400 **NYSE-listed** S&P members the Nasdaq screener can't see.
- **Nasdaq (full Composite)** — FMP `company-screener` exchange=NASDAQ (market-cap-sorted, ETFs/funds
  excluded) + `nasdaq-constituent` for guaranteed Nasdaq-100 sectors; **keyless** `nasdaqlisted.txt` fallback.
- **Dow 30** — FMP `dowjones-constituent` (v3 fallback); hardcoded DOW30 fallback.
- **Russell 2000** — **keyless** iShares **IWM** daily holdings CSV (`parse_iwm_csv`).

Wired into `real_universe()`; the legacy yfinance Russell path is now a SEED-only fallback (no double-add).
Controlled by env:
- `UNIVERSE_MODE` = `all` (default; all four) | `seed` (legacy 92).
- `UNIVERSE_INDEXES` = comma list of `{sp500,nasdaq,dow,russell2000}` to include (default all four).
- `UNIVERSE_LIMIT` = optional integer throttle (0/unset = the entire union, ~4–5k names; **S&P + Dow always kept**, Russell/Nasdaq tail trimmed first).
- `DOW30` = optional comma-separated override.

Every source is fail-soft and the whole thing falls back to SEED on total failure, so the build never breaks.

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
