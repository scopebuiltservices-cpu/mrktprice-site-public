# Signal-mastery gate (from the evidence-based mastery framework)

The uploaded mastery-evaluation report (Bloom / Dreyfus / mastery-learning / IRT) explicitly notes that its
structure "mirrors how a system should separate **measurement, confidence, and advancement decisions**."
`mastery_engine.py` (+ `.js`, bit-exact parity) operationalizes that for MrktPrice: it decides whether a
forecast or strategy is **NOVICE / PROFICIENT / MASTERY (deployable)** instead of trusting a single score.

## The mapping (education → market signal)
| Mastery rubric component | Weight | MrktPrice metric |
| --- | --- | --- |
| prerequisite knowledge / concepts | 20% | data sufficiency (matured n, coverage breadth) |
| procedural execution | 25% | out-of-sample skill / rank-IC |
| explanation & reasoning | 20% | calibration (interval coverage near nominal, PIT) |
| transfer to novel cases | 25% | cross-regime / OOS Deflated-Sharpe |
| self-monitoring | 10% | stability (low PSI drift, stable folds) |

## The gates (report defaults on a 0–100 composite)
- **novice** — overall < 70, OR any critical component < 60, OR > 2 stable misconceptions.
- **proficient** — 70 ≤ overall < 85 and all criticals ≥ 60 (works on familiar tasks, transfer/stability gaps remain).
- **mastery** — overall ≥ 85 **and** all criticals ≥ 80 **and** no critical error **and** the **two-confirmation rule** passes.

## The three rules that stop "got lucky once" promotion
1. **Critical-component override** — a must-pass component below its floor (e.g. `noLeak`=PIT replay,
   `coverage`, `dsr`=not-overfit, `drift`) blocks the higher tier *regardless of the composite*. A signal
   with a 99 composite but a leakage flag is **NOVICE**, not deployable. (Mirrors the report's "one critical
   safety/ethics/compliance failure blocks mastery.")
2. **Two-confirmation rule** — mastery requires the criterion met on an **initial OOS** window **and** a
   **delayed/parallel (purged)** window — guarding against luck, leakage, coaching contamination, or a good day.
3. **IRT-style confidence bands** — `strong / moderate / insufficient` from matured-sample count + SE; a
   learner/signal near a cut score with little data is not the same as one well above it.

Plus **downward reclassification**: demote when the two most recent delayed checks both regress below the
maintenance threshold.

## How it composes
The critical inputs already exist as verified engines: `pit_engine` (no-leak), `conformal_engine`/`volterm`
(coverage), `validation_engine` (DSR/PBO = transfer/overfit), `monitoring` (drift/stability), `rank_engine`
(IC/skill). `mastery_engine` is the **advancement layer** on top — it consumes those component scores and
returns one honest tier + the explicit reason it didn't reach mastery. Verified: Python planted tests +
Py↔JS golden parity.

## Wiring (next)
Feed each board name's component scores in (data-sufficiency, OOS-IC, coverage, DSR, drift) → show a
**mastery tier badge** (novice/proficient/MASTERY) on the row, and gate "DEPLOYABLE" on `tier == mastery`
so the board only greenlights signals that cleared the evidence bar, not just a high score.
