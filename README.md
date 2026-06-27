# Multi-Day GB Energy Demand Forecasting

> A serverless, point-in-time-correct forecasting pipeline on AWS. Ingests live GB electricity demand, issued weather forecasts, carbon intensity, and Octopus Agile prices; builds a leakage-safe feature store; trains and walk-forward-validates a demand forecaster; and tracks forecast accuracy against reality as it arrives.

<!-- TODO: replace with a real screenshot of the dashboard's forecast-vs-actual view -->
<!-- ![Dashboard](docs/dashboard.png) -->

---

## What this is

Foresight forecasts GB electricity demand **1–7 days ahead** — at the horizon where no official forecast is yet published, so the prediction is a genuine unknown rather than a copy of someone else's answer. Demand is driven by weather, the calendar, and human behaviour, which makes this an honestly hard forecasting problem with a clean way to measure success: wait, and reality tells you exactly how good each forecast was.

The project is built to demonstrate **data-engineering judgement**, not just model accuracy. The interesting parts are the point-in-time-correct feature store (no peeking at the future) and the deliberate, defensible AWS service choices — including the services I *didn't* use.

<!-- TODO: one line on actual results once trained, e.g. "Beats a seasonal-naive baseline by X% MAPE at day-ahead, Y% at 7-day." -->

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

<!-- TODO: fill in once the model is trained and backtested -->

- **Baseline (seasonal-naive):** MAPE — TBD
- **Model (LightGBM):** MAPE by horizon — TBD
- **Validation:** walk-forward (expanding window) — no random splits, because that leaks the future into training

<!-- TODO: add the accuracy-over-time chart and an error-analysis note (where does it struggle — bank holidays? cold snaps? longer horizons?) -->

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
