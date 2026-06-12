# Smart Charge: Flexible Load Optimisation Platform
### A Full Portfolio Data Engineering Project — Step by Step

---

## Overview

You're building a platform that answers: **"When is the best time to use electricity?"** — based on live carbon intensity and price data. EV charging is the first use case, but the architecture generalises to any flexible load.

By the end you will have touched: Python pipelines, PostgreSQL, dbt, Kafka (streaming), ML forecasting, MLflow, FastAPI, Streamlit, Airflow, Terraform, and AWS. Each phase builds on the last, so you're always learning in context rather than in isolation.

**Estimated time:** 4–6 weeks part-time, going deep.

---

## Phase 0 — Environment Setup (Days 1–2)

**What you'll learn:** Project hygiene, Docker, environment management.

### Tasks
1. Create a GitHub repo with a clear README from day one. Commit everything, even rough early work.
2. Set up a Python virtual environment (use `pyenv` + `venv` or `conda`).
3. Install Docker Desktop — you'll use it throughout.
4. Set up `pre-commit` hooks with `black`, `ruff`, and `isort` for code quality from the start.
5. Create a `.env` file for secrets and add it to `.gitignore` immediately.

### Project structure to start with
```
smart-charge/
├── ingestion/          # Raw API clients
├── dbt/                # Transformation layer
├── ml/                 # Forecasting models
├── api/                # FastAPI serving layer
├── dashboard/          # Streamlit app
├── orchestration/      # Airflow DAGs
├── infrastructure/     # Terraform
├── tests/
├── docker-compose.yml
└── README.md
```

### Why this matters for the interview
Starting with structure and tooling signals seniority. Many engineers build first and organise never.

---

## Phase 1 — Data Ingestion (Days 3–7)

**What you'll learn:** REST API clients, pagination, error handling, rate limiting, data contracts.

### Data sources (both free, no auth needed)

**Carbon Intensity API** — National Grid ESO
```
https://api.carbonintensity.org.uk/regional
```
Returns live and forecast carbon intensity (gCO₂/kWh) for 14 UK regions, updated every 30 minutes.

**Octopus Agile API** — Octopus Energy
```
https://api.octopus.energy/v1/products/AGILE-FLEX-22-11-25/electricity-tariffs/E-1R-AGILE-FLEX-22-11-25-C/standard-unit-rates/
```
Returns half-hourly electricity prices (p/kWh) for the next 24 hours. Updated daily at 4pm.

### Tasks
1. Write a Python client for each API using `requests`. Keep them as clean classes.
2. Add retry logic with exponential backoff — APIs go down, pipelines shouldn't.
3. Add logging throughout using Python's `logging` module, not `print()`.
4. Write unit tests with `pytest` and mock the HTTP calls with `responses` or `httpretty`.
5. Store raw responses as JSON locally first, before touching any database.

### Key concept to learn: Data contracts
Define a Pydantic model for each API response. This forces you to think about schema explicitly and catches upstream changes early — a very mature practice.

```python
from pydantic import BaseModel
from datetime import datetime

class CarbonReading(BaseModel):
    region: str
    timestamp: datetime
    intensity_actual: float | None
    intensity_forecast: float
    index: str  # "low", "moderate", "high", "very high"
```

---

## Phase 2 — Storage Layer (Days 8–12)

**What you'll learn:** PostgreSQL, SQLAlchemy, schema design, idempotent writes.

### Tasks
1. Run PostgreSQL locally in Docker:
```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: smartcharge
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
```

2. Design your schema. Think carefully about:
   - How will you handle late-arriving data?
   - How will you avoid duplicate inserts? (use `INSERT ... ON CONFLICT DO NOTHING`)
   - What indexes will you need for time-series queries?

3. Write SQLAlchemy models and a loader that writes your Pydantic-validated data to Postgres.
4. Make your writes **idempotent** — running the pipeline twice should produce the same result, not duplicate rows.

### Schema to aim for
```sql
-- Raw carbon intensity readings
CREATE TABLE carbon_intensity (
    id SERIAL PRIMARY KEY,
    region VARCHAR(50) NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    intensity_actual FLOAT,
    intensity_forecast FLOAT NOT NULL,
    index VARCHAR(20),
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(region, ts)
);

-- Raw Agile price data
CREATE TABLE agile_prices (
    id SERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    price_p_kwh FLOAT NOT NULL,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ts)
);
```

---

## Phase 3 — Transformation with dbt (Days 13–18)

**What you'll learn:** dbt fundamentals, the transformation layer, testing data, documentation.

### Setup
```bash
pip install dbt-postgres
dbt init smartcharge
```

Configure `profiles.yml` to point at your local Postgres.

### Tasks

1. **Staging models** — clean and rename the raw tables:
   - `stg_carbon_intensity.sql`
   - `stg_agile_prices.sql`

2. **Intermediate models** — join and enrich:
   - `int_combined_signals.sql` — join carbon and price on timestamp, one row per half-hour slot

3. **Mart models** — business-ready outputs:
   - `mart_hourly_averages.sql` — hourly rollups per region
   - `mart_charging_windows.sql` — ranked half-hour slots by a combined "cheapness + greenness" score

4. **Add dbt tests** to every model:
```yaml
models:
  - name: stg_carbon_intensity
    columns:
      - name: region
        tests:
          - not_null
      - name: ts
        tests:
          - not_null
          - unique
      - name: intensity_forecast
        tests:
          - not_null
```

5. **Generate dbt docs**: `dbt docs generate && dbt docs serve` — screenshot this for your portfolio. It looks impressive and shows operational maturity.

### Key concept to learn: The medallion architecture
Your raw tables are the **Bronze** layer. Staging models are **Silver** (clean, typed, renamed). Mart models are **Gold** (business-ready). Mention this explicitly in your README — it's an industry-standard pattern.

---

## Phase 4 — Streaming with Kafka (Days 19–24)

**What you'll learn:** Event streaming concepts, producers, consumers, Kafka in Docker.

### Why add streaming?
The APIs update every 30 minutes. Polling every 30 mins is fine for batch, but streaming lets you react instantly to changes — e.g. carbon suddenly spikes, trigger an alert. It also means you're not dependent on scheduled jobs; consumers process events as they arrive.

### Setup — Kafka in Docker
```yaml
# Add to docker-compose.yml
  zookeeper:
    image: confluentinc/cp-zookeeper:7.4.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  kafka:
    image: confluentinc/cp-kafka:7.4.0
    depends_on:
      - zookeeper
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
```

### Tasks
1. Write a **producer** that polls the carbon intensity API every 30 minutes and publishes events to a `carbon-intensity` topic.
2. Write a **consumer** that reads from the topic and writes to Postgres.
3. Add a second topic `agile-prices` for price events.
4. Test what happens when the consumer is down — do events queue up and replay when it restarts? (They should. This is one of Kafka's key properties.)

### Key concept to learn: At-least-once vs exactly-once delivery
Understand why Kafka's default is at-least-once (you might get a duplicate), and why your idempotent DB writes from Phase 2 protect you from that.

---

## Phase 5 — ML Forecasting (Days 25–32)

**What you'll learn:** Time-series forecasting, feature engineering, MLflow experiment tracking, model serialisation.

### The problem
Predict carbon intensity and electricity price for the **next 12 hours**, per region, so the system can recommend optimal windows before they arrive.

### Tasks

**5.1 — Feature engineering**
From your dbt mart layer, build a feature table:
- Hour of day, day of week, month
- Rolling 3hr / 6hr / 24hr averages of carbon and price
- Regional dummy variables
- Lag features (what was the value 1hr, 2hr, 24hr ago?)

**5.2 — Baseline model first**
Before anything fancy, build a naive baseline: "tomorrow's carbon intensity = today's at the same time." Measure its MAE. Every subsequent model must beat this. This is good ML practice.

**5.3 — Train a real model**
Use `LightGBM` for price forecasting and `Prophet` for carbon intensity (it handles daily/weekly seasonality well out of the box). Train separate models per region.

**5.4 — Track everything with MLflow**
```python
import mlflow

with mlflow.start_run():
    mlflow.log_params({"model": "lightgbm", "region": "South West", "horizon_hrs": 12})
    mlflow.log_metric("mae", mae)
    mlflow.log_metric("rmse", rmse)
    mlflow.sklearn.log_model(model, "model")
```

Run MLflow locally: `mlflow ui` — screenshot the experiment comparison view for your portfolio.

**5.5 — Model registry**
Promote your best model to "Production" in the MLflow model registry. Your serving layer (Phase 6) loads from here.

**5.6 — Nightly retraining job**
Write a script that retrains the model on the latest 90 days of data and promotes it if it beats the current production model's metrics. This is the core of MLOps.

---

## Phase 6 — Serving Layer (Days 33–37)

**What you'll learn:** FastAPI, REST API design, loading ML models, async Python.

### Build a FastAPI app

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Smart Charge API")

class ChargeRecommendation(BaseModel):
    region: str
    best_windows: list[dict]
    current_carbon: float
    current_price: float

@app.get("/recommend/{region}", response_model=ChargeRecommendation)
async def get_recommendation(region: str):
    # Load model from MLflow registry
    # Run forecast
    # Rank windows by combined score
    # Return top 3 windows
    ...
```

### The scoring function
This is where it gets interesting. Combine carbon and price into a single "greenness score":

```python
def score_window(carbon_forecast: float, price_forecast: float,
                 carbon_weight: float = 0.5, price_weight: float = 0.5) -> float:
    """Lower score = better time to charge."""
    carbon_normalised = carbon_forecast / 500  # UK max ~500 gCO2/kWh
    price_normalised = price_forecast / 35     # Agile max ~35p/kWh
    return (carbon_weight * carbon_normalised) + (price_weight * price_normalised)
```

Making the weights configurable is a nice touch — different users care more about cost vs carbon.

### Tasks
1. Build the `/recommend/{region}` endpoint
2. Add a `/current` endpoint showing live carbon and price
3. Add a `/forecast` endpoint returning the raw 12hr forecast
4. Add basic input validation and error handling
5. Write a `Dockerfile` for the API

---

## Phase 7 — Dashboard (Days 38–42)

**What you'll learn:** Streamlit, data visualisation, connecting a frontend to a backend API.

### Build a Streamlit dashboard with three views:

**View 1 — Live Now**
- Current carbon intensity by UK region (choropleth map using `folium`)
- Current Agile price
- Simple traffic light: Green / Amber / Red for "charge now?"

**View 2 — 12hr Forecast**
- Line chart of forecast carbon + price (use `plotly`)
- Highlighted optimal charging windows

**View 3 — Historical**
- Rolling 7-day chart of carbon and price patterns
- "If you'd charged at the optimal window every day this week, you'd have saved X% vs always-on"

The dashboard calls your FastAPI endpoints — it doesn't touch the database directly. This separation of concerns is worth explaining in your README.

---

## Phase 8 — Orchestration with Airflow (Days 43–47)

**What you'll learn:** DAG design, task dependencies, scheduling, monitoring.

### Run Airflow in Docker
```bash
# Use the official docker-compose from Airflow docs
curl -LfO 'https://airflow.apache.org/docs/apache-airflow/stable/docker-compose.yaml'
docker compose up airflow-init
docker compose up
```

### DAGs to build

**DAG 1 — `ingest_carbon_intensity`**
Schedule: every 30 minutes
Tasks: `fetch_api` → `validate_schema` → `publish_to_kafka` → `check_row_count`

**DAG 2 — `ingest_agile_prices`**
Schedule: daily at 4:30pm (prices drop at 4pm)
Tasks: `fetch_api` → `validate_schema` → `write_to_postgres` → `run_dbt_models`

**DAG 3 — `retrain_models`**
Schedule: nightly at 2am
Tasks: `extract_features` → `train_models` → `evaluate_vs_production` → `promote_if_better` → `alert_on_failure`

### Key thing to add: alerting
Wire up email or Slack alerts when a DAG fails. Even a stub implementation shows you think about operations, not just development.

---

## Phase 9 — Infrastructure with Terraform (Days 48–55)

**What you'll learn:** Infrastructure as code, AWS core services, state management, cost governance.

### AWS services to provision

```
infrastructure/
├── main.tf
├── variables.tf
├── outputs.tf
├── modules/
│   ├── networking/     # VPC, subnets, security groups
│   ├── compute/        # EC2 for Airflow + API
│   ├── storage/        # S3 buckets (raw, processed, models)
│   ├── database/       # RDS Postgres
│   └── iam/            # Roles and policies
```

### Work through these in order:

**Step 1 — State backend**
Before writing any resources, set up remote state in S3:
```hcl
terraform {
  backend "s3" {
    bucket = "smartcharge-terraform-state"
    key    = "prod/terraform.tfstate"
    region = "eu-west-2"
  }
}
```

**Step 2 — Networking**
VPC with public and private subnets across two availability zones. Your RDS goes in the private subnet; only your EC2 can reach it.

**Step 3 — Storage**
Three S3 buckets: `raw-data`, `processed-data`, `ml-models`. Add lifecycle rules to expire raw data after 90 days — shows cost thinking.

**Step 4 — Compute**
A single `t3.small` EC2 instance running your Docker Compose stack. Use a `user_data` script to bootstrap Docker and pull your repo on launch.

**Step 5 — Database**
RDS Postgres `db.t3.micro`. Enable automated backups. Store the password in AWS Secrets Manager and reference it in Terraform — never hardcode credentials.

**Step 6 — IAM**
Least-privilege roles: your EC2 instance should only have permission to read/write its specific S3 buckets and read from Secrets Manager. Nothing more.

---

### Step 7 — Migrating from Local Docker to RDS

This is the step that ties Phases 1–8 to Phase 9 together. You've been running Postgres locally in Docker throughout development — now you're promoting the same schema and data to AWS.

**7.1 — Export your local schema**
Dump just the schema (no data) from your local Postgres:
```bash
docker exec -t smartcharge-postgres pg_dump \
  --schema-only \
  --no-owner \
  -U postgres smartcharge > infrastructure/schema.sql
```
Commit this file to your repo. It becomes the source of truth for your database structure.

**7.2 — Apply the schema to RDS**
Once Terraform has provisioned RDS, connect to it via a bastion or SSM session (your EC2 instance) and apply the schema:
```bash
psql -h <rds-endpoint> -U postgres -d smartcharge < infrastructure/schema.sql
```

**7.3 — Seed historical data**
Export your local data as a CSV and load it into RDS so you're not starting cold:
```bash
# Export from local
docker exec -t smartcharge-postgres psql -U postgres -d smartcharge \
  -c "\COPY carbon_intensity TO '/tmp/carbon.csv' CSV HEADER"

# Import to RDS
psql -h <rds-endpoint> -U postgres -d smartcharge \
  -c "\COPY carbon_intensity FROM '/tmp/carbon.csv' CSV HEADER"
```

**7.4 — Update your connection string**
Your app reads the database URL from an environment variable. On EC2, this should come from AWS Secrets Manager rather than a `.env` file:
```python
import boto3, json

def get_db_url() -> str:
    client = boto3.client("secretsmanager", region_name="eu-west-2")
    secret = client.get_secret_value(SecretId="smartcharge/db")
    creds = json.loads(secret["SecretString"])
    return f"postgresql://{creds['username']}:{creds['password']}@{creds['host']}/smartcharge"
```
This is a meaningful step up in security maturity from a `.env` file and worth explaining explicitly in your README.

**7.5 — Smoke test**
Run your Airflow DAGs against the RDS instance and confirm data is flowing end-to-end in the cloud environment. Check that your dbt models run cleanly against the new host. If anything breaks here, it's almost always a networking or IAM permissions issue — check your security group rules and IAM role policies first.

**The key thing to articulate in an interview:** Your local Docker Postgres and your RDS instance are identical in schema — the only differences are where they run and how credentials are managed. This means your code never needed to change, just configuration. That's good software design.

### Cost governance habit to build
Add this to your README:
```bash
# Spin up
terraform apply

# Tear down when not using
terraform destroy
```
Mention in interviews that you always `terraform destroy` when not actively developing. It shows you think about cost, not just capability.

---

## Phase 10 — Polish and Documentation (Days 56–60)

**What you'll learn:** How to present technical work to non-technical stakeholders.

### README structure
Your README is as important as your code. It should contain:

1. **One-paragraph plain English description** — what it does, why it matters
2. **Architecture diagram** — use `diagrams` (Python library) or draw.io
3. **Quick start** — someone should be able to run `docker compose up` and see something working in under 10 minutes
4. **Component breakdown** — one paragraph per layer explaining the technical choice and why
5. **What I'd do differently at scale** — Kafka → AWS MSK, local Airflow → MWAA, dbt → dbt Cloud, single model → model ensemble. This section shows you can think beyond a portfolio project.
6. **Limitations and known issues** — be honest. Interviewers respect self-awareness.

### Things to screenshot for your portfolio
- The Airflow DAG graph view with all tasks green
- MLflow experiment comparison showing multiple model runs
- dbt docs lineage graph (the DAG of your transformation models)
- The Streamlit dashboard with live data
- Terraform plan output showing all your AWS resources

---

## Learning Resources by Phase

| Phase | Best resource |
|-------|--------------|
| dbt | dbt Learn (free, official, excellent) |
| Kafka | Confluent's free Kafka 101 course |
| MLflow | Official MLflow docs + this tutorial: mlflow.org/docs/latest/tutorials |
| Airflow | Astronomer's free learning platform (astronomer.io/learn) |
| Terraform | HashiCorp's official tutorials (developer.hashicorp.com/terraform/tutorials) |
| FastAPI | Official FastAPI docs (the best framework docs in Python) |
| AWS | AWS free tier — just build, the docs are good |

---

## Interview Talking Points This Project Gives You

- **"Tell me about a streaming pipeline you've built"** → Kafka producer/consumer, at-least-once delivery, idempotent writes
- **"How do you ensure data quality?"** → Pydantic contracts at ingestion, dbt tests on every model, Airflow alerting on failure
- **"Tell me about your ML infrastructure experience"** → MLflow tracking, model registry, automated nightly retraining
- **"How do you manage infrastructure?"** → Terraform, remote state, least-privilege IAM, lifecycle rules for cost governance
- **"How would this scale?"** → MSK for Kafka, MWAA for Airflow, partitioned S3, read replicas on RDS — you already know the answer because you designed for it

---

*Good luck. Build it in public on GitHub from day one.*
