# Foresight: Multi-Day Energy Demand & Price Forecasting
### A Data-Engineering-Heavy ML Portfolio Project, Right-Sized on AWS, Tailored for Octopus Energy

---

## The One-Paragraph Pitch

Forecast GB electricity demand — and, as a tailored extension, Octopus Agile prices — several days ahead, at the horizon where no official forecast exists yet. The project ingests live demand, weather forecasts, carbon intensity, and tariff data on a continuous schedule; builds a **point-in-time-correct feature store** (the engineering centrepiece); trains and walk-forward-validates a forecasting model; regenerates forecasts on a schedule via batch inference; and tracks forecast accuracy as reality arrives. The output is a live dashboard showing actuals against what the model predicted, with an accuracy-over-time view that proves the ML is real.

It runs on AWS, provisioned with Terraform, but every service is chosen because it's the *right* tool for the workload — not to tick a box. Notably, it uses **scheduled batch inference rather than a live ML endpoint**, because forecasts are generated on a schedule, not on demand. That single decision keeps the ML layer simple, cheap, and honest.

---

## Why This Project Survives Scrutiny

Every static-attribute prediction idea collapses into one of two traps: the target is a deterministic function of the features (too easy), or it's hopelessly confounded (not honestly measurable). **Forecasting is structurally immune to both:**

- **It can't be trivially easy.** The future genuinely isn't in your features. A model that forecasts demand three days out is doing real work, because the answer doesn't exist yet anywhere in the data.
- **It's honestly measurable.** Wait, and reality tells you exactly how good your forecast was. No confounding, no hand-waving — just error metrics against what actually happened.
- **It's the most DE-heavy form of ML there is.** The hard part isn't the model; it's building features that respect time correctly (no leakage from the future) across continuously-arriving data. That's genuine, non-trivial data engineering — and it's the part that levels you up.
- **It restores the real-time quality.** Data arrives continuously, forecasts regenerate every few hours, the dashboard is live. The thing is genuinely useful to watch.
- **It's directly Octopus's business.** Demand and price forecasting underpin grid balancing, tariff-setting, and flexibility products. This is what their data team actually does.

---

## The Core Target (and why it's honest)

**Primary target: GB electricity demand, forecast 1–7 days ahead.**

Short-term load forecasting is a classic, genuinely-hard problem — driven by weather, calendar, and human behaviour, with no closed-form answer. Crucially, **beyond the day-ahead horizon there's no published forecast to copy**, so the prediction is a real unknown.

**The leakage trap you must avoid (this is the whole game):** at prediction time you do *not* know tomorrow's actual weather — you only have a weather *forecast*. So your features must use **weather forecasts as they were issued at prediction time**, never actual weather. Training on actual weather is the single most common way people accidentally cheat at energy forecasting, and it makes the model look brilliant in backtest and useless in production. Getting this right is the core engineering challenge and the thing a sharp interviewer will probe.

**Tailored extension: Octopus Agile price, forecast beyond the published window.** Octopus publishes Agile prices for the next day around 4pm. So forecasting *within* 24h is copying a published answer (the carbon-forecast trap again). The honest, valuable target is **2–7 days ahead**, where no published price exists. Build demand forecasting as the solid core first; add price as the Octopus-specific extension once the core works.

---

## Architecture at a Glance

```
                          ┌─────────────────────────────────────────┐
                          │            Terraform (IaC)               │
                          │   S3 state backend + DynamoDB locking    │
                          └─────────────────────────────────────────┘

  EventBridge (schedules)
        │
        ├─▶ Lambda: ingest demand (NESO/Elexon)      ──┐
        ├─▶ Lambda: ingest weather FORECASTS          ──┤
        ├─▶ Lambda: ingest carbon intensity           ──┼─▶ S3 Bronze (raw, Parquet)
        └─▶ Lambda: ingest Agile prices               ──┘        │
                                                                  ▼
                                                    Glue Catalog ◀── Glue Crawler
                                                                  │
                                                                  ▼
                                              Athena + dbt ──▶ S3 Silver (clean)
                                                                  │
                                                                  ▼
                                          S3 Gold: point-in-time feature store
                                                                  │
                          ┌───────────────────────────────────────┤
                          ▼                                        ▼
              Scheduled training job                  Scheduled BATCH inference
              (Lambda / Fargate task)                 (Lambda / Fargate task)
                          │                                        │
                          ▼                                        ▼
              Model artefact + metadata               Forecasts table (S3/Athena)
              in S3 (versioned)                                    │
                                                                   ▼
                                          Accuracy tracker ──▶ Streamlit dashboard
                                          (forecast vs actual)

         Orchestrated by AWS Step Functions; scheduled by EventBridge
```

---

## The AWS Stack — and the Choices We Deliberately Made

This is the part you asked for: AWS where earned, the honest cheaper option everywhere else.

| Decision | Choice | Why (and why not the alternative) |
|---|---|---|
| Ingestion | **Lambda + EventBridge** | Small, frequent API pulls (half-hourly/daily). Lambda is serverless, scales to zero, free-tier-friendly. *Not Glue* — Glue Python-shell suited the EPC bulk pull, but it's overkill for tiny frequent payloads. |
| Storage | **S3, Parquet, partitioned** | Correct at any scale; cheap; queryable by Athena. |
| Query | **Glue Catalog + Athena** | Serverless SQL, pay-per-scan, zero idle cost. *Not Redshift* — data is small; a warehouse is unjustified. |
| Transform | **dbt-athena** | You know dbt; gives tests + lineage. Builds the feature store. |
| ML training | **Scheduled Lambda or Fargate task** | Tree-based forecaster trains in minutes on modest data. *Not SageMaker training* — managed training ceremony isn't warranted at this size. |
| ML serving | **Scheduled BATCH inference** (not an endpoint) | **The key decision.** Forecasts are generated on a schedule, not per user request — so you run a batch job that writes forecasts to a table. *No SageMaker endpoint, no always-on inference cost.* This is genuinely more correct for forecasting, not just cheaper. |
| Model registry | **S3 versioning + a metadata table** | Sufficient for one model family. *MLflow optional* if you want the experiment-tracking UI; run it locally to avoid hosting cost. |
| Orchestration | **Step Functions + EventBridge** | AWS-native, serverless, on the cert, new to you (vs. your day-job Prefect). |
| Streaming | **None** | Data is half-hourly batch. *Kinesis would be theatre.* Note in the README where it *would* be justified (e.g. live smart-meter feeds) — that's the honest forward-looking answer. |
| IaC | **Terraform** | All of the above, with least-privilege IAM, lifecycle rules, and `destroy` discipline. |

**The headline talking point:** *"I used scheduled batch inference instead of a live ML endpoint, because the use case generates forecasts on a schedule rather than on demand — so an always-on endpoint would have been pure cost for no benefit."* That sentence demonstrates exactly the judgement that separates associate from junior.

---

## Phase 0 — Setup & Cost Guardrails (Day 1)

Identical discipline to any serious AWS project — do this before any chargeable resource exists.

1. **Billing alarms** at £5 and £15; an **AWS Budget** at £20/month with alerts.
2. **Terraform remote state**: S3 bucket + DynamoDB lock table, encrypted.
3. **Repo structure**:
   ```
   foresight/
   ├── infra/              # Terraform (module per service)
   ├── ingestion/          # Lambda handlers per source
   ├── dbt/                # Silver + feature-store models
   ├── ml/                 # training, backtest, batch inference
   ├── orchestration/      # Step Functions + EventBridge
   ├── dashboard/          # Streamlit app
   ├── docs/               # architecture diagram, teardown runbook
   └── README.md
   ```
4. **Teardown runbook** (`docs/TEARDOWN.md`) — keep current from day one.
5. **Region**: `eu-west-2` (London) throughout.

---

## Phase 1 — Data Model & the Point-in-Time Problem (Days 2–5)

**This is the most important phase. Everything hinges on getting temporal correctness right.**

### Data sources (all open)
- **GB electricity demand** — NESO (National Energy System Operator) data portal / Elexon Insights. Half-hourly national demand, historical + near-real-time.
- **Weather forecasts (predictor features)** — Open-Meteo's **Previous Runs API** is the correct source. It serves each variable at fixed lead-time offsets (1, 2, 3 … up to 7 days ahead) — i.e. "the weather as forecast N days before its target." This maps directly onto your 1–7 day forecast horizons and is leakage-safe by construction. No API key. *History note: most models start January 2024; GFS goes back to March 2021. A couple of years is enough — it covers both winters (the dominant demand signal) and supports a real walk-forward backtest. Standardise on one model (GFS for more history, UK Met Office / ECMWF for resolution).*
- **Weather actuals (targets / lagged drivers)** — Open-Meteo's **Historical Forecast API** (a stitched best-estimate series, close to actuals from ~2021) or the **Historical Weather API** (ERA5 reanalysis). Use one of these for ground-truth/target values and for *known-past* weather features. Do NOT use these as forward predictor features — that's the leakage trap.
- **Why not `forecast_hours`/`past_hours`?** Those parameters only window the response relative to a reference point; they cannot select a forecast *issue date*. The Previous Runs API (fixed lead-time offsets) or the Single Runs API (`run=` initialisation time) are the mechanisms for issued-forecast retrieval.
- **Carbon intensity** — `api.carbonintensity.org.uk`, regional, with forecast + actual.
- **Agile prices** — Octopus Energy public API, half-hourly.
- **Calendar** — UK bank holidays (gov.uk open JSON), plus derived day-of-week/season features.

### The core design decision: forecast issue time vs. target time
Every feature row must be tagged with **two timestamps**: the time the forecast is *for* (`target_ts`) and the time the information was *known* (`issue_ts`). A weather feature for `target_ts = Thursday 6pm` must come from a forecast whose `issue_ts` is *before* your prediction moment — never from Thursday's actual weather.

### S3 layout
```
s3://foresight-data/
├── bronze/                         raw pulls, by source
│   ├── demand/ingest_date=.../
│   ├── weather_prevruns/issue_offset=.../    # Previous Runs: forecast-as-issued (predictors)
│   ├── weather_actuals/date=.../             # Historical Forecast/ERA5: actuals (targets)
│   ├── carbon/ingest_date=.../
│   └── agile/ingest_date=.../
├── silver/                         cleaned, typed (Parquet)
└── gold/feature_store/             point-in-time features
    └── target_date=.../
```

Keep the two weather streams physically separate: the Previous Runs predictors are tagged by lead-time offset (so you always know how far ahead each forecast was issued), while actuals are keyed only by date. That separation is what makes the point-in-time join downstream both correct and easy to reason about. Get this layout right and the rest of the temporal logic becomes tractable.

---

## Phase 2 — Continuous Ingestion (Days 6–10)

**Service: Lambda + EventBridge.** One Lambda per source, each on its own schedule.

### Tasks
1. Write a Lambda handler per source: fetch → validate (Pydantic) → write Parquet to the right Bronze prefix.
2. **Critically, for weather: capture forecasts as issued.** Going forward, pull the live forecast each day and store it stamped with its `issue_date`. To bootstrap a training history immediately, backfill from the **Previous Runs API** — it returns weather at fixed lead-time offsets (1–7 days ahead), which is exactly "forecast as issued N days before target." That backfill is what lets you train and backtest from day one rather than waiting weeks to accumulate live captures.
3. Schedule with EventBridge: demand/carbon every 30–60 min, weather forecasts daily, Agile daily after the ~4pm release.
4. Make every write idempotent (overwrite by date key, no duplicate appends).
5. Define Lambdas, schedules, and tightly-scoped IAM roles in Terraform.

> **Cost note:** Lambda + EventBridge at this frequency sits comfortably in the free tier. Nothing idles.

---

## Phase 3 — Catalog & Athena (Days 11–12)

**Glue Crawler + Catalog + Athena**, as in the EPC project.

1. Crawl Bronze, register schemas in the Glue Catalog.
2. Use **partition projection** on the date-partitioned prefixes to avoid constant re-crawling.
3. Set the Athena query-result location with a lifecycle rule.
4. Sanity-check the data with SQL before building anything on top.

---

## Phase 4 — The Point-in-Time Feature Store with dbt (Days 13–20)

**The data-engineering centrepiece.** This is where you spend your difficulty budget.

### Silver models
- `stg_demand`, `stg_weather_forecast`, `stg_carbon`, `stg_agile` — cleaned, typed, half-hourly-aligned, deduplicated.

### Gold: the feature store
- `feature_store` — one row per `target_ts`, where **every feature respects `issue_ts ≤ prediction_time`**. Features include:
  - **Lagged demand** (demand at t-48 half-hours, t-1 week — these are known at prediction time)
  - **Weather forecast** for `target_ts` *as issued* before prediction time (temperature, wind, solar radiation, cloud)
  - **Calendar** (half-hour of day, day of week, month, bank holiday flag)
  - **Rolling statistics** of demand computed only over the known past

### The hard part, made explicit
Building lag and rolling features that never peek into the future requires careful window logic keyed on both timestamps. This is exactly the kind of temporal correctness that distinguishes someone who has *used* a feature store from someone who understands *why* point-in-time correctness matters. Document your approach prominently — it's the most impressive engineering in the project.

### dbt tests
- No-future-leakage assertions (e.g. test that no feature's `issue_ts` exceeds its allowed prediction time)
- `not_null` / `accepted_range` on demand and weather features
- Freshness tests on the source tables

Generate `dbt docs` and screenshot the lineage graph.

---

## Phase 5 — The Forecasting Model & Honest Evaluation (Days 21–28)

### 5.1 — Baselines first (mandatory)
- **Seasonal naive:** "demand at target_ts = demand at the same half-hour one week ago." This is a genuinely strong baseline for energy demand — beating it convincingly is the bar.
- Report MAE / MAPE for the baseline. Every model must beat it.

### 5.2 — The model
- **LightGBM** with the point-in-time features, predicting each half-hour out to 7 days. Tree models handle the mixed calendar/weather/lag feature set well and train in minutes — no GPU, no cluster.
- Forecast all horizons (multi-output, or one model per horizon — discuss the trade-off in your README).

### 5.3 — Walk-forward validation (the time-series-correct evaluation)
**Never random-split time-series data** — it leaks future into training. Use walk-forward (expanding-window) backtesting: train on data up to time T, predict T+1…T+7, roll forward, repeat. This mirrors how the model would actually be used and is the honest way to report accuracy. Being able to explain *why* random k-fold is wrong here is a strong interview signal.

### 5.4 — Error analysis
Where does the model struggle? Bank holidays, cold snaps, the further horizons? This analysis is more impressive than a single headline metric and shows genuine ML maturity.

---

## Phase 6 — Batch Inference & Accuracy Tracking (Days 29–33)

**The honest serving pattern — no live endpoint.**

### 6.1 — Scheduled batch inference
A scheduled job (Lambda if it fits the time/memory limits, else a small Fargate task) that:
1. Loads the current model artefact from S3.
2. Pulls the latest point-in-time features.
3. Generates forecasts for the next 7 days.
4. Writes them to a `forecasts` table (Parquet on S3, queryable via Athena), stamped with the `issue_ts`.

Because forecasts are produced on a schedule and stored, **there's no need for an always-on inference endpoint** — the dashboard just reads the latest stored forecast. This is the architectural decision that keeps the ML layer cheap and correct.

### 6.2 — Accuracy tracking (the honest, visual payoff)
A second scheduled job that, as actuals arrive, joins them to the forecasts that predicted them and computes rolling error metrics. This gives you:
- A live "forecast vs. actual" record
- Accuracy-over-time, broken down by horizon
- The foundation for drift detection / retraining triggers

This is genuine MLOps content *and* the most credible possible demonstration that the model works.

### 6.3 — Retraining loop
A scheduled training job that retrains on the latest data and promotes the new model only if it beats the incumbent on recent walk-forward error (champion/challenger). Versioned artefacts in S3 with a metadata table.

---

## Phase 7 — Orchestration (Days 34–37)

**Step Functions + EventBridge.**

- **EventBridge** triggers the scheduled pipelines (ingestion, daily feature refresh, batch inference, accuracy update, periodic retraining).
- **Step Functions** sequences the multi-step flows with error handling and retries, e.g. the retraining state machine: `refresh features → backtest candidate → compare to champion → promote if better → regenerate forecasts → SNS alert on failure`.
- Wire SNS for failure alerts.

> Step Functions + EventBridge + Lambda are effectively free at this scale. Nothing runs between executions.

---

## Phase 8 — The Live Dashboard (Days 38–42)

**Streamlit**, reading stored forecasts and actuals (run locally, or on a small instance only when demoing).

- **Live view:** current GB demand against the latest forecast, updating as data arrives — this gives the real-time quality you wanted.
- **Forecast view:** the next 7 days of predicted demand (and, if built, Agile price), with uncertainty if you add it.
- **Accuracy view:** rolling forecast error over time, by horizon — the honesty centrepiece. "Day-ahead MAPE is X%; 7-day is Y%."
- **Optional Octopus framing:** "given the price forecast, here's the cheapest predicted charging window beyond the published horizon."

---

## Phase 9 — Polish, README & Teardown (Days 43–47)

### README
1. Plain-English pitch + why forecasting is a genuinely hard ML problem.
2. Architecture diagram.
3. Quick start (`terraform apply` → run → tear down).
4. **The service-choice rationale** — especially batch inference over a live endpoint, Lambda over Glue, no streaming, no Redshift. The rejections are the story.
5. **The point-in-time correctness section** — explain the leakage trap and how you avoided it. This is your strongest engineering signal.
6. The Octopus framing, with honest boundaries.
7. "What I'd do differently at scale" — feature store → managed (e.g. SageMaker Feature Store) if data grew; live smart-meter feed → streaming; etc.

### Teardown runbook + portfolio screenshots
- Step Functions execution graph (all green)
- dbt lineage graph
- The walk-forward backtest results
- The live dashboard with the accuracy-over-time view

---

## How This Maps to the Job Spec & the Cert

| Job spec / cert area | Where demonstrated |
|---|---|
| AWS (S3, Lambda, Glue, Athena, Step Functions, EventBridge) | The whole spine — serverless, right-sized |
| Terraform | All infra as code, with teardown discipline |
| Pipelines from diverse sources / APIs | Four continuous ingestion streams |
| Monitoring, testing, data quality | dbt tests incl. no-leakage assertions, SNS alerts, accuracy tracking |
| ML infrastructure / MLOps | Walk-forward validation, batch inference, champion/challenger retraining, drift tracking |
| Distributed processing | *Deliberately omitted — explain why* |
| Governance | Least-privilege IAM, lifecycle rules, cost guardrails |
| Decarbonisation mission | Better forecasting → less spinning reserve → lower emissions |

---

## Interview Talking Points

- *"Why batch inference, not an endpoint?"* → Forecasts are scheduled, not on-demand; an always-on endpoint would be cost for no benefit.
- *"How did you avoid data leakage?"* → Point-in-time feature store using weather forecasts as issued, never actuals; no-leakage dbt tests; walk-forward validation.
- *"Why is random k-fold wrong here?"* → It trains on the future to predict the past; walk-forward mirrors real use.
- *"How do you know the model works?"* → Accuracy tracked against actuals as they arrive, by horizon, beating a seasonal-naive baseline.
- *"Why no SageMaker / Kinesis / Redshift?"* → The workload didn't justify them; I'd rather not run infrastructure I can't defend.
- *"How does this matter to Octopus?"* → Demand and price forecasting underpin balancing, tariff-setting, and flexibility — and better forecasts cut both cost and carbon.

---

## Honest Risks to Manage

1. **The point-in-time logic is the hard part — and the most valuable.** Budget real time for it; it's where the project earns its DE credibility.
2. **Bootstrapping weather-forecast history — now confirmed viable.** You need *issued* forecasts, not actuals. Open-Meteo's **Previous Runs API** provides exactly this (fixed 1–7 day lead-time offsets), with history from Jan 2024 for most models (GFS from Mar 2021). A couple of years is sufficient — it spans both winters and supports walk-forward validation. Day-one sanity check: pull a Previous Runs forecast at a 3-day offset for one past week, pull the actuals for that week, and confirm the numbers genuinely differ (they should — forecasts are imperfect). If they're identical, something's misconfigured; investigate before building on it.
3. **Lambda limits for training/inference.** If the job exceeds Lambda's time/memory, move it to a small scheduled Fargate task — cheap, still serverless-ish, no always-on cost.
4. **Scope discipline.** Build demand forecasting end-to-end first. Add Agile price, uncertainty intervals, and the Octopus charging-window layer only once the core loop works.

---

*Build it in public on GitHub from day one. The point-in-time feature store and the deliberate service choices — including the ones you rejected — are the story.*