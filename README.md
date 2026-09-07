# Multi-Day GB Energy Demand Forecasting

> A serverless, point-in-time-correct forecasting pipeline on AWS. Ingests live GB electricity demand, issued weather forecasts, carbon intensity, and Octopus Agile prices; builds a leakage-safe feature store; trains and walk-forward-validates a demand forecaster; and tracks forecast accuracy against reality as it arrives.

<!-- TODO: replace with a real screenshot of the dashboard's forecast-vs-actual view -->
<!-- ![Dashboard](docs/dashboard.png) -->

---

## What this is

Foresight forecasts GB electricity demand **1–7 days ahead** — at the horizon where no official forecast is yet published, so the prediction is a genuine unknown rather than a copy of someone else's answer. Demand is driven by weather, the calendar, and human behaviour, which makes this an honestly hard forecasting problem with a clean way to measure success: wait, and reality tells you exactly how good each forecast was.

The project is built to demonstrate **data-engineering judgement**, not just model accuracy. The interesting parts are the point-in-time-correct feature store (no peeking at the future) and the deliberate, defensible AWS service choices — including the services I *didn't* use.

Current results: the model beats a seasonal-naive baseline by **23–44%** at every horizon under walk-forward validation. See [Results](#results).

---

## Architecture

<!-- TODO: replace this ASCII sketch with a proper diagram (docs/architecture.png) -->

```
EventBridge (schedules)
   ├─▶ Lambda: ingest demand (NESO/Elexon)
   ├─▶ Lambda: ingest weather forecasts (Open-Meteo Previous Runs)
   ├─▶ Lambda: ingest weather actuals (ERA5 / Historical Forecast)
   ├─▶ Lambda: ingest carbon intensity
   └─▶ Lambda: ingest Agile prices
            │
            ▼
      S3 Bronze (raw, Parquet)  ──▶  Glue Crawler ──▶ Glue Data Catalog
            │
            ▼
      Athena + dbt  ──▶  S3 Silver (clean)  ──▶  S3 Gold (point-in-time feature store)
            │
   ┌────────┴─────────┐
   ▼                  ▼
Scheduled training   Scheduled BATCH inference ──▶ forecasts table (S3/Athena)
(Lambda/Fargate)                                          │
   │                                                      ▼
model artefact (S3, versioned)        Accuracy tracker ──▶ Streamlit dashboard

   Orchestrated by AWS Step Functions · provisioned with Terraform
```

---

## Key design decisions

| Decision | Choice | Why |
|---|---|---|
| Ingestion | Lambda + EventBridge | Small, frequent API pulls; serverless, scales to zero |
| Storage | S3 + partitioned Parquet | Cheap, columnar, queryable by Athena |
| Query | Glue Catalog + Athena | Serverless SQL, pay-per-scan, no idle cost (not Redshift — data is small) |
| Transform | dbt-athena | Tests + lineage; builds the feature store |
| ML serving | **Scheduled batch inference, not a live endpoint** | Forecasts are generated on a schedule, not on demand — an always-on endpoint would be cost for no benefit |
| Orchestration | Step Functions + EventBridge | AWS-native, serverless |
| Streaming | None | Data is half-hourly batch; streaming would be unjustified here |
| IaC | Terraform | All infra as code, with teardown discipline |

**The point-in-time problem (the core of the project):** at prediction time you only have a weather *forecast*, never tomorrow's actual weather. Every predictor feature therefore uses forecasts *as they were issued* (via Open-Meteo's Previous Runs API, at 1–7 day lead offsets), never reanalysis actuals. Training on actuals is the most common way to accidentally cheat at energy forecasting — it looks brilliant in backtest and fails in production. Avoiding it is the whole game.

---

## Data sources

All open, no paid access required.

- **GB electricity demand** — NESO / Elexon Insights (half-hourly)
- **Weather forecasts (predictors)** — Open-Meteo Previous Runs API (forecast-as-issued, 1–7 day lead offsets)
- **Weather actuals (targets)** — Open-Meteo Historical Forecast / ERA5
- **Carbon intensity** — Carbon Intensity API (api.carbonintensity.org.uk)
- **Agile prices** — Octopus Energy public API
- **Calendar** — UK bank holidays (gov.uk)

<!-- TODO: confirm exact endpoints/params you settled on and link them here -->

---

## Repository structure

```
foresight/
├── infra/              # Terraform (module per AWS service)
├── ingestion/          # Lambda handlers, one per source
├── dbt/                # Silver + Gold (feature store) models
├── ml/                 # training, walk-forward backtest, batch inference
├── orchestration/      # Step Functions + EventBridge definitions
├── dashboard/          # Streamlit app
├── docs/               # architecture diagram, teardown runbook
└── README.md
```

---

## Getting started

> **Prerequisites:** an AWS account, Terraform ≥ <!-- TODO version -->, Python ≥ <!-- TODO version -->, and AWS credentials configured.

> ⚠️ **Cost first.** Set a billing alarm before provisioning anything. This stack is serverless by design and costs a few £/month with disciplined teardown, but always `terraform destroy` when you're not actively working.

```bash
# 1. Provision infrastructure
cd infra
terraform init
terraform apply

# 2. Run the pipeline
# TODO: the actual command(s) — e.g. trigger the Step Functions state machine

# 3. View the dashboard
# TODO: how to launch Streamlit and point it at the data

# 4. Tear down when done
terraform destroy
```

<!-- TODO: flesh out each step with real commands once built. See docs/TEARDOWN.md for full teardown. -->

---

## Results

**Validation:** walk-forward, expanding window — 12 monthly folds over Jul 2025 – Jun 2026, with a **7-day purge** between each fold's training cutoff and its test window. The purge exists because a model fitted at `train_end` is used to predict targets up to 7 days beyond it; without it, the last week of training would contain labels that had not been published yet at the fold's earliest prediction time. No random splits.

**Baseline:** seasonal-naive — demand at the same hour on the most recent *legal* same-weekday anchor (`lag_7d`, or `lag_14d` at lead 7, where the publication lag makes a 7-day anchor unknowable).

Error is RMSE as a percentage of mean demand. Both rows are scored on identical target timestamps.

| Lead (days) | Baseline | LightGBM | Improvement |
|---|---|---|---|
| 0 | 10.96% | **5.53%** | −49.5% |
| 1 | 10.96% | **6.73%** | −38.6% |
| 2 | 10.96% | **6.66%** | −39.2% |
| 3 | 10.96% | **6.99%** | −36.2% |
| 4 | 10.96% | **7.21%** | −34.2% |
| 5 | 10.96% | **7.58%** | −30.8% |
| 6 | 10.96% | **7.94%** | −27.6% |
| 7 | 12.33% | **8.64%** | −29.9% |

The baseline is identical across leads 0–6 because `lag_7d` for a given target hour does not depend on how far ahead you are standing; lead 7 differs only because the publication gate forces the fallback to `lag_14d`. Model error, by contrast, degrades with the horizon — which is the behaviour you want to see, and a useful check that nothing is leaking.

The model is given the baseline's own anchors as features, so the baseline is a degenerate case of the model rather than a competitor with different information. Beating it means the remaining features carry *signal* beyond the anchor.

### What the weather forecast is worth

Removing the four weather features (`temperature_2m`, the HDD/CDD hinges, and `shortwave_radiation`) and re-running:

| Lead (days) | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| ablation gap before radiation was added | −0.47 | +0.15 | +0.52 | +0.67 | +0.68 | +0.82 | +0.87 | +0.86 |
| ablation gap now | +0.11 | +1.28 | +1.80 | +1.70 | +1.77 | +1.67 | +1.41 | +1.28 |

Beyond day 0 the weather block is worth between 1.3 and 1.8pp — roughly a fifth of the model's total error at those leads. The benefit is close to flat across the horizon rather than growing with it: error growth from lead 1 to lead 6 is +1.21pp with weather and +1.33pp without. Weather is buying a level shift, not a slower decay.

That is what justifies the point-in-time pipeline. If the forecast only mattered once the recent demand reading went stale, it would be a late-horizon top-up and a sloppier weather source would cost little. Instead it carries a fifth of the accuracy at *every* horizon the model serves — so it has to be the forecast **as issued**, at every lead, or the number above is measuring information the model will never have at prediction time.

The two rows above are the same measurement taken before and after `shortwave_radiation` was added; neither is an absolute error. One irradiance feature more than doubled what the whole weather block is worth — the error analysis below explains why.

At lead 0 the effect all but vanishes (+0.11pp): with a demand reading two hours old, weather adds little the lag does not already carry. Before radiation the pooled model was measurably *worse* with weather at lead 0; that penalty is now gone.

### Is any of this noise?

The model is fitted with LightGBM's bagging and column sampling left off, which makes the fit fully deterministic — so `random_state` is inert and repeated runs are byte-identical. That is good for reproducibility but proves nothing about stability, so the seed sweep was re-run with bagging *enabled* to get a genuine noise floor: run-to-run standard deviation is **0.01–0.03pp**, with a total spread across five seeds of at most 0.07pp.

Against that floor, the weather effects are real. The lead-2 gain never drops below +1.80pp across the five seeds and the lead-6 gain never below +1.39pp — same sign every time, roughly a hundred times the run-to-run spread. Lead 0 is the only marginal case: +0.13 to +0.21pp under bagging, or +0.11pp in the deterministic headline run above. Small, but positive in every seed.

Hyperparameters are deliberately untuned. Enabling bagging measured ~0.05pp better at every lead, but adopting it would mean selecting a hyperparameter by reading the walk-forward scores, at which point those scores stop being an unbiased estimate of generalisation. The 0.05pp is not worth that.

### A data-quality bug worth recording

An early version of these numbers was computed on a mart where lead 0 had 29% fewer rows than lead 7. The cause was in ingestion, not modelling: the backfill fetched Open-Meteo Previous Runs in chunks of **target** dates, but landed Bronze partitioned by **issue** date — and a single issue date's records span the following 8 target days. Any issue date near a chunk boundary was therefore split across two fetches, each writing its own half to the same key, last write winning. The result was a recurring multi-day hole affecting short leads hardest, with no error raised anywhere: the deterministic-key overwrite that makes re-runs idempotent quietly assumes one key's data comes from one fetch.

The fix constrains each chunk to write only the issue dates it can complete (`lo … hi − 7`) and advances the window so those *writable* ranges tile contiguously. Row counts per lead are now flat to within the expected one-day-per-lead boundary effect, and every landed partition carries all eight lead offsets.

### Where the model struggles

Error is not spread evenly. Four slices, in descending order of what they cost.

**Embedded solar — the largest, and now partly fixed.** Error concentrates in daylight: hours 10–14 run 9.6–10.4% against 5.0% at hour 20, and the signed error is *negative* right through the middle of the day, meaning the model was over-predicting. April was the worst month at 10.32%, with a mean signed error of −912 MW.

The cause is a metering boundary, not anything in the model. GB "national demand" is measured at the **transmission** boundary. Almost all GB solar is *embedded* — sited on the **distribution** network, downstream of that meter. Its output never crosses the boundary, so it never appears as generation; it appears as demand that failed to arrive. With no feature that could see irradiance, the model predicted the demand that would have existed without it.

That gave a falsifiable prediction, written down before the fix: adding irradiance should close the April-vs-rest gap **in daylight hours only**. A feature that improved every hour equally would be proxying for season or time of day, not for solar.

| April-vs-rest RMSE gap (pp) | hour 0 | hour 3 | hour 6 | hour 12 | hour 13 | hour 14 | hour 23 |
|---|---|---|---|---|---|---|---|
| before `shortwave_radiation` | −0.89 | +0.50 | −1.68 | +11.22 | +11.77 | +11.83 | −0.44 |
| after | −0.72 | +0.77 | −1.47 | **+9.42** | **+9.69** | **+9.21** | −0.11 |

The prediction held: midday moved, overnight did not. April as a whole fell 12.09% → 10.32%, and hour 20 was unchanged at 5.00% → 4.99%.

The honest reading is that embedded solar is a **confirmed contributor, not the whole cause** — roughly a fifth of the midday gap closed and some 9pp of it remains. One candidate for the rest: irradiance is taken at a single London grid point, a poor proxy for GB-wide sunshine when the solar fleet is spread across the country. That is a hypothesis for next time, not a conclusion.

**Bank holidays.** 13.52% against 7.05% on ordinary days, with a signed error of −1,397 MW — the model consistently expects more demand than arrives. Holidays are 2.2% of rows (1,536 of 70,080), and with `min_child_samples=20` there are too few of them to earn many splits of their own, so `is_holiday` cannot outvote the weekday pattern it competes with. The lag features actively work against it: `lag_7d` for a bank holiday is an ordinary working day.

**Sub-zero temperatures.** Below 0°C the model **under**-predicts by +990 MW on average — by far the largest signed bias of any temperature band, where the next largest is +207 MW. This is a bias rather than a magnitude problem: at 7.31%, RMSE in the cold tail is actually *lower* than the 0–5°C band's 8.23%. A tree predicts a constant within each leaf and so cannot extrapolate; the coldest leaf is fitted mostly on rows warmer than the extreme, and its flat prediction falls short of what genuinely cold weather does to demand. There are 523 such rows, 0.7% of the set — which makes this a case for more data in the tail rather than more model.

**Day of week — a null result worth stating.** RMSE spans 6.66% to 7.77% across the seven days and the signed error stays within ±202 MW. That is a negative control passing: weekly seasonality is already being carried by the calendar features, and the residual structure lives in weather and in the holiday calendar instead. It is recorded here because it redirected effort — the next thing to investigate was not a day-of-week interaction.

<!-- TODO: add the accuracy-over-time chart -->

---

## Relevance to Octopus Energy

Demand (and price) forecasting underpins grid balancing, tariff-setting, and flexibility products. Better short-term forecasts mean less spinning reserve held in readiness, which cuts both cost and carbon. This is a simplified, public-data version of a problem an energy data team works on directly.

**Honest boundary:** this uses open national/regional data. A production version would draw on internal half-hourly metering, settlement data, and proprietary signals — out of scope here, and the README says so deliberately.

---

## What I'd do differently at scale

<!-- TODO: keep this honest and specific as the project teaches you things -->

- Feature store → a managed offline/online store if data volume grew
- A genuine high-frequency source (e.g. live smart-meter feeds) would justify a streaming layer; the current half-hourly data does not
- Multi-region / probabilistic forecasts (prediction intervals, not just point forecasts)

---

## Licence

<!-- TODO: choose one, e.g. MIT -->

---

*Built as a portfolio project. The point-in-time feature store and the deliberate service choices — including the ones rejected — are the parts worth reading the code for.*
