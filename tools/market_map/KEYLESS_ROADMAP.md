# Keyless build paths for the "data-blocked" recommendations

The earlier status called 7 of the 16 "Omitted Strategies" recommendations *data-blocked*. Re-examined
against the repo's existing **keyless ethos** (FRED `fredgraph.csv`, SEC EDGAR `company_tickers.json`,
SEC 13F bulk, FINRA), **6 of the 7 have a FREE / keyless data path** — only borrow-fee data genuinely
needs a paid vendor. None of these depends on FMP. Each below gives the free source, the engine
interface, the wiring point, and effort. Verified-engine pattern applies (Python ref + planted tests +
JS port where it touches the browser).

---

## 1. Point-in-time ingestion & leakage control — KEYLESS ✅
**Free source:** SEC EDGAR filing dates (`filingDate`/`acceptedDate`, already pulled in
`fmp_history.quarterly_income` and derivable keyless from EDGAR `submissions/CIK##########.json`); FRED
series carry vintages via ALFRED (`fredgraph.csv?vintage_dates=`). The repo already emits `cik.json`.
**Engine:** add an `as_of` / `available_at` stamp to every feature row; a `leak_guard(feature_ts, decision_ts)`
that drops any feature with `available_at > decision_time`; delisting-return handling via the SEC ticker
history. **Wire:** `build_market_map` feature assembly + a `replay/leak test` in CI. **Effort:** L (data
discipline across the feature set), but no paid feed.

## 2. Factor / sector / style residualization — KEYLESS ✅
**Free source:** **Ken French Data Library** — the FF 5-factor daily/monthly returns are a public CSV
(`F-F_Research_Data_5_Factors_2x3_daily.CSV`), plus Momentum and (constructible) QMJ. Download + cache
nightly like FRED.
**Engine (verified, self-contained once factors are cached):**
`residualize(alpha, exposures, factor_returns) -> mu_resid = alpha - B·lambda_factor`; estimate `B` by
time-series regression of each name on the FF factors. **Wire:** new `factor_returns.py` (keyless CSV
fetch) + a `residualize()` in `rank_engine` consumed before ranking. **Effort:** M.

## 3. Regime-conditional IC — KEYLESS ✅ (self-data + time)
**Free source:** the board's OWN nightly logs — `factor_ic.jsonl` (per-factor IC history) + the HMM
`regimeNow` already in `lineage`. No external feed; it accrues over time.
**Engine:** `regime_ic(ic_history, regime_path) -> IC[state, factor]`; the board's
`mu = IC(state)·sigma·z` reads the state-conditioned IC. **Wire:** `factor_pipeline.py` (already
accumulates IC) + read in the board. **Effort:** M; mostly bookkeeping over existing logs.

## 4. Crowding / shortability — MOSTLY KEYLESS ✅ (borrow-fee is the only paid piece)
**Free source:** **FINRA short-interest** (biweekly, free bulk file), **SEC 13F** ownership concentration
(already in `flow_keyless.py`). Borrow *fee/availability* is the one genuinely paid signal — omit it or
proxy with utilization from SI/float.
**Engine:** `crowding_penalty(short_interest_pct, ownership_conc, float) -> penalty`; subtract from `mu`.
**Wire:** new keyless `short_interest.py` (FINRA) + the existing 13F flow. **Effort:** M.

## 5. Conformalized intervals (CQR) — NOT DATA-BLOCKED ✅ (method, buildable now)
No external data — it's a technique over our own returns. Quantile regression + **split-conformal**
calibration (we already do split-conformal in `lineage.calibrate_horizon`; CQR generalizes it to
quantile predictions). **Engine:** `cqr_interval(q_lo, q_hi, calib_residuals, alpha)` reusing the
existing conformal machinery. **Effort:** M; reclassify as buildable immediately.

## 6. Continuous calibration & drift monitoring — KEYLESS ✅ (self-data)
**Free source:** the board's own `health_log.jsonl`, `alpha_log.jsonl`, `trig_out.jsonl`. No external feed.
**Engine/job:** a nightly `monitoring.py` that computes decile calibration, 50/68/90/95% interval coverage,
rank-IC, gross-vs-net spread, predicted-vs-realized active risk, turnover, PBO/DSR (now in
`validation_engine` + `rank_engine.deflated_sharpe`), and PSI drift — emitting `monitoring/latest.json`
with alert thresholds (Great-Expectations-style checks, but stdlib). **Wire:** new CI job. **Effort:** M.

## 7. Per-name SE decomposition + bootstrap — KEYLESS ✅ (self-data)
Already shipping the **regression** SE (`alpha_forecast_se`). The 4-part decomposition
(`sigma^2 = model + resid + event + data`) and **bootstrap** intervals use only our own residual /
event / data-quality histories (the board already carries `dq` and `drift`). **Engine:**
`bootstrap_se(residuals, B)` + `combine_se(model, resid, event, data)`. **Effort:** M.

---

## The one genuinely paid item
**Borrow fees / locate availability** (part of #4) — needs a securities-lending vendor (e.g., S3/IHS).
Everything else above is free. Until then, proxy borrow cost from FINRA short-interest utilization.

## Recommended keyless build order
1. **#5 Conformal CQR** (no data, immediate) — extends the calibration we already trust.
2. **#6 Monitoring job** (self-data) — closes the loop, catches regressions, ships `monitoring/latest.json`.
3. **#2 FF residualization** (Ken French CSV) — removes hidden factor bets, the biggest signal-quality gain.
4. **#3 Regime-IC** (self-data) — state-aware skill from logs we already keep.
5. **#7 Bootstrap / SE decomposition** (self-data) — upgrades the LCB inputs.
6. **#4 Crowding** (FINRA SI + 13F) — keyless; borrow-fee deferred to a paid feed.
7. **#1 PIT discipline** (EDGAR/ALFRED) — largest, but the most important safety control.

All seven engines follow the verified pattern (Python ref + planted tests + JS parity where browser-facing),
and none requires FMP — so they proceed independently of the current FMP outage.
