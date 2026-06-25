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
- Phase 3 — Calibration: split-conformal/CQR by regime×horizon; CRPS/interval-score/Wilson/PIT on-chart.
- Phase 4 — Volume & impact: sigma-volume matrix + Hawkes RVOL + touch-before-finish per level.
- Phase 5 — UI: lineage ribbon + node scatter + sigma-volume heatmap + node card; honest P/Q panels.
- Phase 6 — Governance: FRTB/STANS/SPAN/SIMM/SR 11-7 cards + provenance + challenger backtests + release gate.
