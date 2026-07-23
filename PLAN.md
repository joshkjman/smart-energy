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
- [x] Write the demand ingestion client (Python — I've got this; you review edge cases). *(Elexon `initialDemandOutturn`; range-capable via `fetch_demand_outturn(from, to)`, 28-day API cap handled by chunking; writes one file per settlement date.)*
- [~] Write the weather **Previous Runs** ingestion (predictors), stamped by lead offset. *(Client + `reshape_to_long` written; write-loop + `validate()` still commented out, and it's not yet range-capable (`past_days` relative to today). Deferred until backfill.)*
- [ ] Write the weather **actuals** ingestion (targets).
- [ ] Write carbon intensity + Agile price ingestion.
- [ ] Add Pydantic validation / data contracts to each. *Ask me what should happen when validation fails.*
- [~] Backfill historical data to bootstrap training (Previous Runs archive). *(Only a 32-day demand sliver (2026-06-10 → 07-11) pulled locally to unblock the Gold join. Full 12–24 month weather + demand backfill still to do — the real blocker before baseline/validation.)*
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

> **Note — intentional reorder:** the dbt modelling was built **first, locally on DuckDB**, ahead of the Phase 2/3 AWS ingestion + Athena wiring. This let the leakage-critical logic get proven and understood without waiting on infra. The models are portable SQL; porting the project to `dbt-athena` (adapter + sources pointing at the Glue catalog instead of local files) is still outstanding and belongs with Phase 3.

- [~] Set up the dbt project. *(Done on **dbt-duckdb** locally, not dbt-athena yet — see note above.)*
- [x] Build Silver staging models (clean, typed, half-hourly-aligned, deduplicated). *3 models: `stg_demand`, `stg_weather_forecast` (pivoted long→wide), `stg_bank_holidays` (E&W + Scotland unioned). Tests: not-null/unique on keys, temp validity bounds, holiday grain.*
- [x] Build the Gold feature store. **This is the hard part.** *`fct_demand_features`, grain `(target_ts, lead_days)`. Weather rides the grain (`issue_ts = target − lead`) for free point-in-time correctness; label joined at target (demand aggregated half-hourly→hourly).*
- [x] Engineer lag features and rolling stats that never peek into the future. *`demand_lag_mw` via ASOF join at `cutoff = target − lead − publication_lag`. (Rolling stats not yet added — single lag for now.)*
- [~] Add dbt tests, including no-future-leakage assertions. *Compound-grain uniqueness + not-nulls on keys/label done. The leakage guard is currently proven **structurally** (grain enforces it) rather than by an explicit assertion test — worth adding one.*
- [ ] Generate dbt docs; screenshot the lineage graph.
- [x] **Explain-back:** pick any feature and make me prove it can't leak. *(Done — weather-vs-demand asymmetry: forecast legal-at-target vs actual forbidden-at-target; demand's sliding cutoff + ASOF.)*

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
- **TO VERIFY (don't assume):** how far back the GFS Previous Runs archive actually reaches on Open-Meteo — confirm it gives enough years/seasons before committing to a training window. (Same discipline as the Phase 0 data-premise check.) *(Checked: archive reaches ~Jan 2024 for most models, GFS 2m-temp back to Mar 2021 — 2+ years available, not the binding constraint.)*
- **`publication_lag_hours` is a placeholder (`24`) in `dbt_project.yml`.** It directly sets the demand-lag leakage cutoff. Elexon publishes `initialDemandOutturn` well under a day after each settlement period — verify the real lag and document the justification in DESIGN before trusting the guard.
- **Ownership rule resolved (DESIGN §5):** live vs backfill weather writes collide at the file level (identical `issue_date` path, last-writer-wins). Defence = disjoint ranges by construction + per-client write-once guard (weather fail-closed; demand permissive since outturn gets revised) + delete-to-correct as the deliberate escape hatch. The grain uniqueness test is **not** the backstop (collision resolves before dbt reads).
- **`is_holiday` is all-`false` in the current window** — no E&W bank holiday falls in 10 Jun–11 Jul 2026. Expected, not a bug; the column exercises once the data window spans a real holiday. Division decision: filtered to `eng&wales` (dominates GB demand).
- **Local dev tip:** DuckDB is a single file (`dbt/foresight.duckdb`); can browse in DBeaver (read-only driver prop to coexist with `dbt run`), or `dbt compile` + open `target/compiled/.../fct_demand_features.sql` to step through CTEs.
- **Next-session fork:** either (a) do the deferred weather+demand **backfill** (unblocks everything downstream — 12–24 months), or (b) keep building **baseline + walk-forward** logic against the small local set and backfill later. Baseline/validation only become *meaningful* with ≥12 months (annual cycle), so the backfill is the more honest next step.
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