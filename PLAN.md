# PLAN.md — Foresight Build Roadmap

> This is the **execution tracker** for the project. It's a living checklist — we update the checkboxes as we go, so that at the start of any session we can see exactly where we are. Work top to bottom; don't jump ahead.

---

## How the project documents fit together (read once)

- **CLAUDE.md** — how we work together. The learning contract. *You (Claude Code) must follow it: navigator not driver, skeletons not full implementations, make me reason and explain things back.* Re-read it at the start of each session.
- **PLAN.md** (this file) — what we're doing, in order, with progress. This drives the session.
- **README.md** — the finished-project description and design rationale. Read it once for orientation and the architecture; it's the *destination*, not the route.
- **energy_forecasting_project_spec.md** — the detailed reference. When a step here needs deeper "why," that's where it lives. Don't read it cover-to-cover each session; consult the relevant phase when we reach it.

**Order of reading at session start:** CLAUDE.md (how we work) → PLAN.md (where we are) → consult the spec section for the phase we're on. Read the README once at the very start of the project for context.

---

## Session ritual (do this every time)

**At the start of a session:**
1. Re-read CLAUDE.md.
2. Find the first unchecked `[ ]` item below — that's where we are.
3. Briefly remind me what we did last session and what's next. Ask me if I want to continue there or revisit anything.

**At the end of a session:**
1. Update the checkboxes for what we actually completed.
2. Make sure I've committed with a meaningful message.
3. Note any open questions or decisions in the "Running notes" section at the bottom.

---

## How each step works (the rhythm)

Per the contract in CLAUDE.md, most steps follow this loop — hold me to it:
1. **I predict / propose** how it should work, before any code.
2. **You respond to my idea** — refine, poke holes, confirm. Skeleton or pseudocode at most.
3. **I implement.**
4. **You review** — correctness, leakage, security pass; point don't rewrite.
5. **Explain-back checkpoint** at the end of each component.

---

## Phase 0 — Foundations & Cost Guardrails

*Goal: make a surprise bill impossible and set up the repo. Spec: Phase 0.*

- [x] **Verify the critical data assumption first.** Before anything else, confirm Open-Meteo's Previous Runs API genuinely gives forecast-as-issued at 1–7 day lead offsets. The day-one test: pull a forecast at a 3-day offset for one past week, pull the actuals for that week, confirm the numbers *differ*. (If they're identical, stop and rethink the weather source.) — *Ask me to predict what I expect to see before I run it.*
- [x] Set an AWS billing alarm at £5 and £15; create a £20/month budget with alerts. *(Budget + multiple alert thresholds done; CloudWatch EstimatedCharges alarm deferred — us-east-1 gotcha.)*
- [x] Initialise the git repo; add CLAUDE.md, README.md, PLAN.md, and the spec.
- [x] **`.gitignore` before first commit** — ask me what must never be committed (`.env`, `*.tfstate`, credentials) and confirm they're ignored.
- [x] Create the folder structure (`infra/`, `ingestion/`, `dbt/`, `ml/`, `orchestration/`, `dashboard/`, `docs/`).
- [x] Set up the Terraform remote state backend (S3 bucket + ~~DynamoDB lock table~~ native S3 lockfile, `use_lockfile = true`). `terraform init` succeeded; `.terraform.lock.hcl` tracked.
- [x] Start `docs/TEARDOWN.md` and keep it current from here on.
- [x] **Explain-back:** why does Terraform need remote state and locking? *(remote state = portability + durability/orphaned-resource cost + secrets-at-rest; locking = serialise writers, prevent state-file corruption.)*

---

## Phase 1 — Data Model & the Point-in-Time Problem

*Goal: decide the S3 layout and nail the temporal design. This is the most important design phase. Spec: Phase 1.*

- [x] Talk through the two weather streams (Previous Runs = predictors; ERA5/Historical Forecast = actuals/targets). *Ask me to explain why they must stay separate before we design the layout.*
- [x] Decide which weather model to standardise on (GFS for history depth vs. Met Office/ECMWF for resolution). **Chose GFS** — deep multi-year archive matters more than local resolution, because (a) ML + walk-forward validation need multiple years/seasons, and (b) target is *national aggregate* demand, so fine spatial resolution is the dimension we need least.
- [x] Design the S3 Bronze/Silver/Gold prefix layout and partitioning. **Layout:** `s3://…/<layer>/<source>/…` — each source its own dataset/prefix; partition *inside* each. Single-timestamp sources (demand, weather_actuals, carbon, agile_price) partition on observation date. **weather_forecast Bronze partitions on `issue_date`** (one Lambda pull = one issue date → many target dates = one clean idempotent partition; Bronze = "what we knew when"). Gold reorganises around `target_date` for serving. Bank holidays = tiny static lookup, no date partition.
- [x] Sketch the feature-store schema: the two timestamps (`target_ts`, `issue_ts`) and why both are needed. **Row = keys (`target_ts` = half-hour predicted, `issue_ts` = when predicted) + target (actual demand at `target_ts` from NESO/Elexon, joined after the fact) + feature families (weather forecast-as-issued, calendar, demand lags).** Governing rule: every feature must be knowable as of `issue_ts`. Key subtlety: **demand lags anchor to `issue_ts`, not `target_ts`** (no forecast of future demand exists) — and "as of `issue_ts`" means "what was *published* by then" (feed has a reporting lag, handle in ingestion).
- [x] **Explain-back:** walk through how a single feature row guarantees no future leakage. *(`issue_ts` = the wall; all features drawn from ≤ wall (weather forecast-as-issued, calendar, demand lags published by then); only the target sits past the wall as the label. Structural guarantee → same inputs in backtest & production.)*

---

## Phase 2 — Continuous Ingestion

*Goal: live data flowing into Bronze via scheduled Lambdas. Spec: Phase 2.*

- [x] Decide the ingestion pattern: one Lambda per source, EventBridge schedules. **Lambda over Glue** — tiny non-streaming JSON pulls, seconds of Python, no distributed compute; Lambda's sub-second start + per-ms billing beats Spark's minutes-long cluster spin-up + DPU-hour floor. (Glue only right for GB+ distributed transforms.) **One Lambda per source** — independent schedules, failure isolation, and least-privilege IAM (each role scoped to its one API + one S3 prefix).
- [ ] Write the demand ingestion client (Python — I've got this; you review edge cases).
- [ ] Write the weather **Previous Runs** ingestion (predictors), stamped by lead offset.
- [ ] Write the weather **actuals** ingestion (targets).
- [ ] Write carbon intensity + Agile price ingestion.
- [ ] Add Pydantic validation / data contracts to each. *Ask me what should happen when validation fails.*
- [ ] Backfill historical data to bootstrap training (Previous Runs archive).
- [ ] Write the Lambda + EventBridge + IAM in Terraform. *I write the HCL; you correct syntax. Security pass on the IAM roles — make me justify each permission.*
- [ ] **Explain-back:** why is each ingestion write idempotent, and how?

---

## Phase 3 — Catalog & Athena

*Goal: query the raw data with SQL, serverlessly. Spec: Phase 3.*

- [ ] Set up the Glue Crawler + Catalog in Terraform.
- [ ] Configure partition projection on the date-partitioned prefixes.
- [ ] Set the Athena query-result location with a lifecycle rule.
- [ ] Explore the data in Athena; sanity-check it. *I write the queries.*
- [ ] **Explain-back:** why Athena over Redshift for this data size?

---

## Phase 4 — The Point-in-Time Feature Store (dbt)

*Goal: the engineering centrepiece — leakage-safe features. Spec: Phase 4. Go slow here.*

- [ ] Set up the dbt-athena project. *(I use dbt at work — light help.)*
- [ ] Build Silver staging models (clean, typed, half-hourly-aligned, deduplicated). *I write the SQL; you review.*
- [ ] Build the Gold feature store. **This is the hard part.** *I design the point-in-time join logic myself; you only review for leakage. Do NOT write this for me.*
- [ ] Engineer lag features and rolling stats that never peek into the future. *Make me reason through each one's `issue_ts` constraint.*
- [ ] Add dbt tests, including no-future-leakage assertions.
- [ ] Generate dbt docs; screenshot the lineage graph.
- [ ] **Explain-back:** pick any feature and make me prove it can't leak.

---

## Phase 5 — Forecasting Model & Honest Evaluation

*Goal: a model that beats baseline, validated correctly. Spec: Phase 5. This is the core ML learning — least help here.*

- [ ] Build the seasonal-naive baseline FIRST. *Don't let me skip this. Make me predict roughly how hard it'll be to beat.*
- [ ] Measure baseline MAE/MAPE.
- [ ] Implement walk-forward (expanding-window) validation. *If I reach for `train_test_split`, stop me and ask why it's wrong.*
- [ ] Build the LightGBM forecaster on the point-in-time features. *I write the modelling code; you review for leakage and correctness.*
- [ ] Compare to baseline by horizon.
- [ ] Error analysis: where does it struggle (holidays, cold snaps, longer horizons)?
- [ ] **Explain-back:** why is random k-fold wrong here, and what does walk-forward simulate?

---

## Phase 6 — Batch Inference & Accuracy Tracking

*Goal: scheduled forecasts + honest accuracy-over-time. Spec: Phase 6.*

- [ ] Decide the serving pattern. *Ask me why batch inference beats a live endpoint here.*
- [ ] Write the scheduled batch-inference job (Lambda or Fargate). *I implement; you review.*
- [ ] Write forecasts to a table (Parquet/Athena), stamped with `issue_ts`.
- [ ] Build the accuracy tracker: join forecasts to actuals as they arrive, compute rolling error by horizon.
- [ ] Build the champion/challenger retraining logic. *I design the promotion rule.*
- [ ] **Explain-back:** how does the accuracy tracker prove the model works honestly?

---

## Phase 7 — Orchestration

*Goal: tie it together with Step Functions + EventBridge. Spec: Phase 7.*

- [ ] Design the Step Functions state machine for the retraining flow. *I sketch the states; you review.*
- [ ] Wire EventBridge schedules for ingestion, feature refresh, inference, accuracy update.
- [ ] Add error handling, retries, and SNS failure alerts.
- [ ] Write it all in Terraform. *I write HCL; you correct.*
- [ ] **Explain-back:** why Step Functions over re-using the orchestration I know from work?

---

## Phase 8 — The Live Dashboard

*Goal: the visual payoff. Spec: Phase 8.*

- [ ] Build the Streamlit app: live demand vs. latest forecast.
- [ ] Add the 7-day forecast view.
- [ ] Add the accuracy-over-time view (the honesty centrepiece).
- [ ] (Optional) Octopus framing: cheapest predicted window beyond the published horizon.

---

## Phase 9 — Polish, README & Teardown

*Goal: make it presentable and defensible. Spec: Phase 9.*

- [ ] Fill in the README TODOs with real commands, numbers, and screenshots.
- [ ] Create the architecture diagram.
- [ ] Finalise `docs/TEARDOWN.md`.
- [ ] Capture portfolio screenshots (Step Functions graph, dbt lineage, backtest, dashboard).
- [ ] Write the "what I'd do differently at scale" section honestly.
- [ ] **Final explain-back:** could I whiteboard this whole architecture and defend every service choice in an interview? If not, which parts are still shaky?

---

## Running notes

*(Decisions made, open questions, things to revisit — update as we go.)*

- **Scope confirmed:** core model forecasts *national GB-aggregate* demand (ESO is the clean labelled target). Regional = harder/noisier (later); household (dad's Octopus) = analysis stretch, not a forecast.
- **Weather model = GFS.** Deep history > local resolution for a national target + walk-forward backtest. Multi-city weather = *feature sources* blended into one national signal, not separate targets.
- **TO VERIFY (don't assume):** how far back the GFS Previous Runs archive actually reaches on Open-Meteo — confirm it gives enough years/seasons before committing to a training window. (Same discipline as the Phase 0 data-premise check.)
- 

---

## Definition of done (first pass)

Don't gold-plate. The first pass is **done** when: demand forecasting runs end-to-end, beats the seasonal-naive baseline, is validated walk-forward, deploys and tears down cleanly on AWS, and the README is honest and complete. The Agile-price extension, uncertainty intervals, and the Octopus charging-window layer are **stretch goals** — mention them as "next steps," don't let them block a finished first pass.

### Stretch goal: household tariff analysis (real consumption data)

Using my dad's Octopus account (with his permission), pull the house's half-hourly smart-meter consumption via the authenticated Octopus API and join it against Agile half-hourly prices to answer: *what would this house have paid on Agile vs. the current tariff, and what would load-shifting save?* Notes to hold me to when we get here:

- [ ] Confirm permission with my dad first; treat this as his data, not mine.
- [ ] The consumption feed is lagged (typically yesterday's reads), NOT real-time — verify the actual lag against the API docs, and don't use it to justify a streaming layer.
- [ ] Credentials handled properly (never committed; Secrets Manager / env vars) — this is the security section of CLAUDE.md meeting a real authenticated source.
- [ ] Raw consumption data stays out of the public repo: gitignored locally or anonymised; code public, data private.
- [ ] Keep it an *analysis* (tariff comparison, savings estimate), not a household *forecast* — single-home demand is noisy and would make an ugly accuracy story; if I want to attempt a household forecast anyway, frame it explicitly as "here's why this is much harder than national."
- [ ] Interview framing: "my family's real consumption, used with permission" — the value is realness, not exclusivity.