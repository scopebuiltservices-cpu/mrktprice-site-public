# Forecast & Ranking Upgrade Roadmap (from the 3 research PDFs)

Digest of three advisory reports + what is now SHIPPED vs NEXT. All engines follow the verified pattern
(pure-stdlib Python reference + planted tests + 1:1 JS port + golden-fixture parity), keyless.

---

## SHIPPED THIS ROUND

### #2 Fama-French residualization — strip hidden factor bets (PDF 1, item 5) ✅
- **`factor_returns.py`** — keyless fetch+cache+parse of the public **Ken French** FF5 + Momentum daily
  CSVs (`parse_ff_csv` offline-tested on a fixture; network fetch runs only in CI). Cache: `data/ff_factors.csv`.
- **`residualize_engine.py` / `residualize_engine.js`** (bit-exact parity) — `factor_betas` (multivariate
  OLS of name EXCESS returns on the 6 factors), `factor_premia` (mean or EWMA), `residualize` →
  `mu_resid = alpha_raw − H·Σ βₖλₖ`. Planted test recovers betas (R²≈0.9) and strips a pure factor bet to 0
  while keeping idiosyncratic edge.
- **`residualize_board.py`** — post-build enrichment (no monolith surgery): regresses each name's hist
  returns on the cached factors, writes `n.fac = {b:{6 betas}, r2, expPct, n}` into `marketmap.json`.
- **`factor_neutral.js`** — external board module; nets `fac.expPct` out of each row's displayed alpha and
  shows an **`fnα`** chip (factor-neutral expected return) + betas/R² tooltip. Zero monolith surgery.
- **Wiring:** `pages.yml` fetches the FF cache + runs `residualize_board.py` after the build; `data/ff_factors.csv`
  committed for persistence; `<script src="factor_neutral.js">` added.

### PDF 3 √t-replacement vol layer — `volterm_engine.py` / `.js` (parity) ✅
Retires `σ_H = σ₁·√H`. `hv_term_structure` (direct H-step HV), `variance_ratio` (Lo-MacKinlay with
homoskedastic z **and** heteroskedasticity-robust z*+95% CI), `ewma_vol` (RiskMetrics), `studentize`,
`blended_scale`. Planted tests: random walk → VR≈1 & HV≈√; mean-reverting → VR<1 & HV<√ (z*=−22);
persistent → VR>1 & HV>√ (z*=+24). Composes with the already-shipped `conformal_engine` (CQR) for the
studentized asymmetric bands PDF 3 prescribes.

---

## NEXT (prioritized, all keyless / verified-pattern)

**PDF 3 (finish the band replacement) — HIGH.** Wire `volterm_engine` σ_H into the cone in place of √H,
then feed studentized residuals to `conformal_engine.cqr_*` for asymmetric rolling bands; maturity-aware
calibration with embargo ≥ H. Acceptance: per-horizon coverage inside Wilson CI of 90%, regime-sliced.
Calibration counts: 500 (H≤10), 750 (H=30), 1000 (H=90).

**PDF 2 Fibonacci multi-horizon projection + accuracy — HIGH.** Build `proj_engine` (Py+JS):
`cumulative_decay_multiplier M(H,τ)=(1−φ^H)/(1−φ)`, `build_fallback_projection`, `expected_path_price`
(normalized so path(e=H)=stored forecast), `score_accuracy` (signedLogError/zError, skill-vs-naive).
Golden unit fixture from the report (AAPL H=21, 199.50→205.80, actual 203.90 ⇒ zErr −0.092). Feed σ_H from
`volterm_engine` instead of √H. Publishing gates: ≥60 non-overlapping resolved, calibration gap <7pp, SPA/White-RC/MCS, HAC overlap.

**PDF 1 remaining production layers — MEDIUM (safety-first order):**
1. PIT discipline (`available_at` ≤ decision_time leak guard) + replay test — *the report's top safety item*.
2. Net-of-cost LCB already partly shipped; add Almgren-Chriss impact later.
3. Per-name SE 4-part decomposition + bootstrap (regression SE already shipped) — composes with `conformal_engine`.
4. HMM regime-conditional IC (self-data; `factor_ic.jsonl` + regime).
5. Holdings-aware transition utility + hysteresis (portfolio_engine already has turnover_blend).
6. Crowding penalty (FINRA SI + 13F; borrow-fee is the one paid signal).

---

## Cross-PDF synthesis
Build order that maximizes reuse: **volterm σ_H → conformal CQR bands (PDF 3)** → **Fibonacci projection/scoring
on top (PDF 2)** → **PDF 1 production discipline (PIT, regime-IC, crowding)**. Common threads: maturity-aware
leakage-free calibration, overlap-aware (HAC/embargo) evaluation, conformal over Gaussian, PIT/CRPS only with a
true predictive CDF, and Python↔JS parity as a hard gate.
