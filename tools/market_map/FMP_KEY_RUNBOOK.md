# FMP Ultimate key — diagnose & fix runbook

The live site currently reports **"FMP Ultimate NOT pulling (last OK: never this run) — serving yfinance
backup."** That means the paid FMP price path is failing on the first call. This runbook pinpoints *why*
in minutes and tells you exactly what to change. (The board keeps working on the free yfinance backup the
whole time — nothing is down, the *paid* feed is just not being used.)

## Step 1 — Run the probe (no full rebuild needed)
GitHub repo → **Actions** tab → left sidebar **"FMP Ultimate health probe (6-hourly)"** → **Run workflow**
→ green **Run workflow** button. It finishes in ~1 minute and prints an `>>> ACTION:` line in the log and
commits/ships **`fmp_health.json`** (also viewable at `https://mrktprice.com/fmp_health.json`).

## Step 2 — Read the verdict
Open `fmp_health.json`. The top-level `action` field is the headline. Each entry in `endpoints[]` has
`{name, ok, reason, status, fix}`. The `reason` is one of:
`ok · invalid_key · rate_limited · plan_or_endpoint · empty · http_error · network`.

## Step 3 — Decision tree (match the `action` / `reason`)

| What you see | Meaning | Fix |
| --- | --- | --- |
| `overall: "no_key"` | The `FMP_API_KEY` secret is **not set** in this repo. | Add it (Step 4). |
| `action` starts **"KEY INVALID"** (any endpoint `reason: invalid_key`) | The key is wrong/expired/typo'd. | Replace the secret value with a fresh key (Step 4). |
| `action` **"KEY VALID but the HISTORICAL-EOD price endpoint is not in your plan tier"** (quote/income OK, `eod` `reason: plan_or_endpoint`) | **Most likely case.** The key authenticates, fundamentals work, but the historical-EOD/chart endpoint isn't in this key's plan. | The key is a *lower tier than the one with charts/EOD*. In your FMP dashboard confirm the plan includes **Charts / Historical EOD** (Ultimate does), or paste the **Ultimate-tier** key into the secret. |
| `action` **"RATE-LIMITED"** (`reason: rate_limited`, HTTP 429) | Daily/throughput quota hit. The key is fine. | Wait for reset, or upgrade the plan, or trim the universe. Re-run the probe later. |
| `reason: network` everywhere | CI couldn't reach FMP. | Re-run; if it persists, check Actions egress. |
| `overall: "ok"` | All endpoints pass. | Nothing to do — trigger a nightly `[rebuild]` to repopulate FMP prices. |

## Step 4 — Set / update the secret (only you can do this)
Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret** (or edit the
existing one) → Name **`FMP_API_KEY`** → paste the key value → **Save**. (The build also accepts
`FMP_ULTIMATE_API_KEY`.) Never put the key in a URL, file, or commit — secrets only.

## Step 5 — Confirm the fix
1. Re-run **"FMP Ultimate health probe"** → `fmp_health.json` `overall` should read **`ok`**.
2. Trigger a fresh nightly: push any commit whose message contains **`[rebuild]`** (or run the
   **"Build + publish MrktPrice"** workflow). After it finishes, `marketmap.json` `source` should change
   from the "⚠ FMP Ultimate NOT pulling…" banner to the live-FMP string, and `dataHealth.fmpPriceProbe`
   should read `ok` with `priceSrc: "FMP"`.

## What I (the agent) verified for you
- The endpoint the code calls — `https://financialmodelingprep.com/stable/historical-price-eod/full?symbol=…`
  — is the **current, correct** FMP endpoint (checked against FMP's live docs). So this is **not** a code
  bug; it's a key/plan/quota issue, which the probe now classifies and the table above resolves.
- The probe is **self-diagnosing**: it writes the exact `fix` per endpoint and the headline `action` into
  `fmp_health.json` and the workflow log, so the answer is in front of you the moment it runs.
