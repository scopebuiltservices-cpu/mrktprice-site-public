# SEC-event mathematics (8-K / 13D / 13G / Form 3-4-5) — equations & wiring

How MrktPrice turns dated SEC filings into NUMBERS on the timeline, in the reports, in the
Considerations card, and in the board's expected-return tilt. All implemented in the verified
`event_engine` (Python ref + JS port, golden-fixture parity) and ingested keyless by `sec_forms.py`.

## Data (keyless)
`sec_forms.py` reads the free EDGAR submissions API `https://data.sec.gov/submissions/CIK##########.json`
and extracts the recent **event stream** per name: `{form, filingDate, items(8-K codes), accession}` for
8-K, SC 13D, SC 13D/A, SC 13G, SC 13G/A, and Forms 3/4/5. No key, no vendor.

## 1. Event-study abnormal return (market model; MacKinlay 1997)
Estimate the market model on a clean estimation window before the event:

    r_{i,t} = a + b·r_{m,t} + e_t              (OLS over the estimation window)
    AR_t    = r_{i,t} − (a + b·r_{m,t})        (abnormal return)
    CAR(τ1,τ2) = Σ_{t=τ1}^{τ2} AR_t            (cumulative abnormal return over the event window)
    SCAR    = CAR / ( σ_AR · √(τ2−τ1+1) ),   σ_AR = std(AR) on the estimation window

`SCAR` is ~N(0,1)/t under H0, so |SCAR| > 1.96 ⇒ a statistically significant reaction. Verified: a planted
+6% event-day jump is recovered with β≈1.26, CAR≈0.055, SCAR≈9.7; an event-free window gives |SCAR|<2.5.

## 2. Event intensity (self-exciting exponential decay; Hawkes-style)
A single number for "how much SEC activity, how recent, how severe":

    I(t) = Σ_{e : t_e ≤ t}  s(type_e) · exp( −(t − t_e) / τ )

`s(type)` = severity weight (below); `τ` = decay in trading days (default 10). Recent, severe clusters →
high `I`. (Calendar age is converted to trading days × 5/7.)

## 3. 8-K item-code severity  s ∈ [0,1]  (materiality)
Per the 8-K item number on the filing (a filing carries the **max** over its items):

    4.02 non-reliance/RESTATEMENT 0.95 · 1.03 bankruptcy 0.95 · 4.01 auditor change 0.85 ·
    2.06 impairment 0.80 · 2.01 M&A 0.70 · 5.01 control change 0.70 · 3.01 delisting 0.65 ·
    2.02 results 0.60 · 1.01/1.02 material agreement 0.55 · 5.02 officer departure 0.55 ·
    7.01 Reg FD 0.30 · 5.03 bylaws 0.30 · 8.01 other 0.25 · (unknown → 0.25 floor)
Non-8-K base severities: SC 13D 0.85, 13D/A 0.60, 13G 0.40, 13G/A 0.30, Form 3 0.35, Form 4 0.45, Form 5 0.30.

## 4. 13D / 13G stake signal  ∈ [−1,1]
A 13D (activist, >5%, intent to influence) is weighted higher than a passive 13G:

    stake = clamp( sign·( g(form)·Δpct/5 + 0.4·new·g(form) ), −1, 1 ),   g(13D)=1.0, g(13G)=0.45

Δpct (ownership change) needs the filing document; keyless we proxy via presence/recency of recent 13D vs
13G filings (a fresh activist 13D ⇒ positive ownership-interest prior).

## 5. Insider net ratio (Form 3/4/5)  ∈ [−1,1]
10b5-1 *planned* sells are down-weighted (they're scheduled, less informative) by ρ≈0.35:

    w_sell     = discSell + ρ·planSell
    netInsider = ( buyVal − w_sell ) / ( buyVal + w_sell + ε )

(Reuses the existing Form-4 parse already in the build: buy / discSell / planSell.)

## 6. Combined event tilt (the number added to expected return, in %)
    eventTilt = θ1·tanh(CAR/k1) + θ2·tanh(I/k2) + θ3·stake + θ4·netInsider,  clamped to ±cap
    θ = (0.6, 0.4, 0.5, 0.5),  k1=0.05, k2=2.0, cap=3.0
Bounded to ±3% and monotone in each input. Server-side (`event_board.py`) computes it with CAR=0 and writes
`n.ev = {intensity, n8k, n13d, n13g, nins, last, stake, netIns, tilt, events[]}`; the terminal fills the CAR
term client-side from price history (name vs SPY) via `event_engine.js`.

## Where it surfaces
- **Timeline / calendar:** every `n.ev.events[]` date is a dated vertical (8-K ◆, 13D/G ▣, insider ●) on the
  chart, beside the existing earnings/quarterly lines.
- **Considerations card:** the most material recent filings + `SCAR` and `eventTilt` are listed as "why".
- **Numbers:** `eventTilt` nets into the board's displayed alpha (factor-neutral α − costs + eventTilt).
- **Reports:** the research brief includes the event block (counts, last filing, intensity, tilt).
- **Status:** `fmp_health.json` (6-hourly probe) drives the FMP-status tile so data freshness is always visible.

## Verification
`event_engine` planted tests (CAR recovery, intensity decay, severity ranks, stake/insider signs, tilt
bounds) + Py↔JS golden parity; `sec_forms` planted submissions-JSON parse; `event_board` planted enrichment;
`fmp_healthcheck` injected-fetch verdicts (ok/degraded/down/no_key). All green.
