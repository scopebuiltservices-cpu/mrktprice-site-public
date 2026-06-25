# Lineage Forecasting Payload Schema (Phase 1 — Foundation)

Institutional cone upgrade per the *Institutional Upgrade Blueprint*. The cone stops being a
charting widget and becomes a **probability-lineage forecasting system**: for each horizon it
emits a calibrated distribution, top branches, touch odds, conditional volume, regime posteriors,
ranked drivers, and timestamped provenance.

Heavy fitting runs **server-side** (`tools/market_map/lineage.py`); the browser renders a
normalized payload using the mirror module (`lineage.js`). Both are unit-tested against planted
structure (`tools/market_map/test_lineage.py`, `tools/test_lineage.mjs`) and cross-checked to the
same decimals.

## Horizon set — INTRADAY-WEIGHTED (configured)

| label | trading-days | tier |
|---|---|---|
| intraday | 0.25 | primary |
| 1d | 1 | primary |
| 5d | 5 | primary |
| 10d | 10 | context |
| 20d | 20 | context |
| 63d | 63 | context |

Every pricing, path, and calibration metric is computed **separately by horizon** — no pretending
they are interchangeable. Primary tier drives the UI; context tier is shown but de-emphasized.

## Lineage node payload (`LineageNode`)

| field | meaning |
|---|---|
| `node_id`, `parent_id` | DAG lineage tracking |
| `forecast_ts`, `horizon_end_ts`, `horizon` | time provenance |
| `q10,q25,q50,q75,q90,q95` | quantile slice (the calibrated distribution) |
| `p_node` | posterior probability of this branch node |
| `p_touch_up`, `p_touch_down` | Brownian-bridge touch-before-finish odds to nominated levels |
| `expected_cum_volume` | forecast cumulative volume to node (sigma-volume matrix) |
| `sigma_equivalent` | move in z-units (1σ), distinct from the implied absolute move |
| `event_var_share` | portion of local variance from a discrete event |
| `regime_probs` | full posterior over regimes |
| `confidence_decomp` | branch vs diffusion vs calibration confidence (law of total variance) |
| `drivers_ranked` | ordered factor contributions, each labeled associated / event-linked / causal |
| `provenance` | which data sources + timestamps fed the node |
| `validation_snapshot` | rolling coverage, CRPS, PIT for this horizon×regime |
| `reasoning_text` | human-readable summary generated **from fields only** (no free-form guessing) |

## Driver label discipline

A factor contribution is labeled exactly one of:
- **associated** — predictive dependence only (default; the safe label),
- **event-linked** — tied to a scheduled catalyst (earnings/FOMC/CPI),
- **causal** — only when a Pearl/Rubin design justifies the word.

Anything unrecognized is coerced to `associated`. This prevents the dashboard drifting from honest
forecasting into cinematic storytelling.

## Core engine functions (Phase 1, both Python + JS)

| function | purpose | theorem/lineage |
|---|---|---|
| `viterbi` | MAP regime lineage (top branch) | Hamilton / Viterbi |
| `top_branches` | MAP + next-2 branches w/ branch probability | regime mass × transition × trajectory density |
| `branch_decomposition` | diffusive vs branching confidence | law of total variance |
| `bridge_touch_upper/lower` | touch-before-finish per level | Brownian-bridge boundary crossing |
| `sigma_volume_matrix` | E[cum volume \| kσ move, horizon] (**volume-ahead**) | conditional expectation |
| `conformal_pad` / `apply_symmetric_conformal` | finite-sample interval recalibration | split conformal (Vovk/Lei/Romano/Candès) |
| `hawkes_expected_count` | short-horizon volume burst forecast | exp-kernel Hawkes |
| `straddle_labels` | honest "implied absolute move" vs "sigma-equivalent move" | ATM straddle ≈ S₀σ√T·√(2/π) |
| `event_variance` | discrete-event variance extraction | Q-measure term-structure differencing |
| `house_blend` | unified P/Q/event variance (display only) | Girsanov P↔Q discipline |
| `driver_contributions` | ranked, label-disciplined drivers | cⱼ = π(z)\|βⱼ\|\|Δfⱼ\| / Σ |

## Roadmap status

- **Phase 1 — Foundation (this):** engine + payload schema + validation, server + browser, unit-tested. ✅
- Phase 2 — Forecast core: emit regime posteriors + top-3 branches + branch decomposition into per-ticker payload.
- **Phase 3 — Calibration (this):** split-conformal by regime×horizon; CRPS/interval-score/Wilson/PIT/DKW per ticker. ✅
- Phase 4 — Volume & impact: sigma-volume matrix + Hawkes RVOL + touch-before-finish per level.
- Phase 5 — UI: lineage ribbon + node scatter + sigma-volume heatmap + node card; honest P/Q panels.
- Phase 6 — Governance: FRTB/STANS/SPAN/SIMM/SR 11-7 cards + provenance + challenger backtests + release gate.


## Validation snapshot (Phase 3) — `lineage.valid[horizon]`

Walk-forward (no-lookahead) calibration of the per-horizon predictive, scored honestly and
attached per ticker. Validation lives on the chart, not a hidden notebook.

| field | meaning |
|---|---|
| `coverage`, `wilsonLo/Hi`, `target` | empirical band coverage + Wilson score CI vs the (1-α) target |
| `crps` | mean CRPS of the Gaussian predictive (Gneiting–Raftery closed form) |
| `intervalScore` | mean Winkler/Gneiting interval score (lower = sharper-given-calibrated) |
| `pitKS`, `pitUniformP` | PIT KS distance from Uniform + p (uniform PIT ⇒ calibrated) |
| `conformalPad`, `coveragePadded` | split-conformal pad needed + the coverage it restores |
| `dkw` | Dvoretzky–Kiefer–Wolfowitz empirical-CDF band half-width |
| `byRegime` | coverage split by the Viterbi-decoded regime (where n ≥ 15) |
| `calibrated` | boolean: |coverage − target| ≤ 0.05 |

Computed for all six horizons (intraday/1d/5d collapse to the 1-step bucket on weekly data;
the browser recomputes short horizons on daily/intraday series via the `lineage.js` mirror).

## Options-implied P/Q layer (Phase 5.5) — `lineage.pq`

Honest separation of the **physical (P)** and **risk-neutral (Q)** measures (Girsanov discipline).
Q comes from the ATM implied vol (`gex.atmIV`, annualized) sqrt-time-scaled to each horizon
(CME convention); P is the per-horizon unconditional σ (`horizons[h].totVol`).

Top level: `ivAnnual`, `ivDays` (IV tenor), `omegaQ` (Q weight, shrunk to 0 with no IV),
`modellable` (IV present). Per horizon (`pq.horizons[h]`):

| field | meaning |
|---|---|
| `sigP` | physical-measure σ over the horizon (model) |
| `sigQ` | risk-neutral σ = IV·√(days/252) |
| `sigHouse` | √(ω_Q·σ_Q² + (1−ω_Q)·σ_P²) — blended display vol |
| `impliedAbsMove` | σ_Q·√(2/π) = the ATM straddle ≈ **E\|move\|** (NOT the 1σ move) |
| `sigmaEquiv` | σ_Q = the **1σ-equivalent** move |
| `eventShare` | max(0, σ_Q²−σ_P²)/σ_Q² — implied-over-realized excess (VRP proxy) |
| `evtIn` | true when an earnings date falls inside the horizon (event-linked) |

UI: a dotted violet **Q-envelope** on the lineage ribbon (q50 ± z·σ_Q), and a **P vs Q panel**
in the node card (σ_P / σ_Q / σ_House, implied-\|move\| vs σ-equivalent labels, event-variance
share, IV/ω_Q, modellability badge). Absent IV → P-measure only, panel/envelope hidden.

*Phase 5.5 closes the two open Phase-5 gaps (P/Q + straddle labels, and event_var_share).*

## Governance & release gate (Phase 6) — `lineage.gov` + top-level `governance`

Every framework badge maps to a **genuinely-computed** number (honest proxy labels where data is
thin), not regulatory theater.

Per name (`lineage.gov`):

| field | framework | meaning |
|---|---|---|
| `es975` | Basel FRTB | Expected Shortfall at 97.5% (VaR + mean of the worst tail) over the gov horizon |
| `stressedES` | FRTB / OCC STANS | ES recomputed over the highest-variance trailing window |
| `challenger` | SR 11-7 | walk-forward CRPS for model vs **random-walk**, **EWMA**, **options-Q**; `winner`, `coverage`+Wilson, `calibrated`, `beatsRW` |
| `scanRisk` | CME SPAN | worst-case loss over a price-move × vol-scenario grid (scan array) |
| `simm` | ISDA SIMM | delta (dominant learned factor, genuine), vega (σ_Q−σ_P, genuine), curvature = `null` (honestly — needs option gamma) |
| `releaseGate` | SR 11-7 | **deployable** (beats random-walk on CRPS **and** calibrated) / **research-only** (miscalibrated or no edge) / **blocked** (insufficient history) |
| `gateReason` | — | plain-English verdict |
| `provenance` | audit | data sources + timestamps + `modelVersion` + `histWeeks` |

Top-level `governance` = `{counts:{deployable, research-only, blocked}, modelVersion, builtAt, asof}`
powers the SR 11-7 model-status banner.

The gate is honest: on noise it refuses "deployable" ("no CRPS edge over a driftless random walk"),
which is the blueprint's anti-data-snooping discipline. UI: a governance card with the gate badge,
universe counts, ES/stressed-ES/scan-risk/vega/Δ chips, a challenger CRPS scorecard (winner ★),
the five framework badges, and provenance.

*Phase 6 complete — the full institutional roadmap (Foundation → Forecast core → Calibration →
Volume → UI → Governance, plus the options-implied P/Q layer) is built, unit-tested, and emitted.*
