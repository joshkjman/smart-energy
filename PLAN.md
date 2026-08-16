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

## Build strategy (revised mid-project) — prove the core locally, then productionize

The phases below are numbered in a logical dependency order, but we are **not** executing them as a strict infra-first waterfall. The leakage-critical dbt modelling was (correctly) built first on **local DuckDB**, and we're leaning into that. Two tracks:

- **Track A — the analytical core, all local (DuckDB):** backfill 12–24 months → seasonal-naive baseline → walk-forward validation → model that beats baseline → a simple accuracy-by-horizon result. This is the entire interview-defining story and needs **zero AWS**. Finish this first so that even in the worst case there's a complete, defensible ML result.
- **Track B — productionization onto AWS:** ingestion Lambdas + EventBridge, Glue/Athena catalog, `dbt-athena` port, batch inference, Step Functions. This *wraps* a known-working core and is narrated as "how I'd operationalize it" — a strength, not a prerequisite.

**Rule:** don't sink sessions into Track B (Glue crawlers, Step Functions, IAM) until Track A produces a model that beats baseline. An unfinished analytical core showcases nothing; a local-but-complete one showcases everything. Map to phases: Track A ≈ finish 2 (backfill only) → 4 → 5. Track B ≈ rest of 2 → 3 → 6 → 7. Then 8/9.

> **✅ Gate cleared (2026-08-10).** Track A is done: 24-month backfill, leakage-safe mart, seasonal-naive baseline, walk-forward validation, and a LightGBM model beating baseline 23–45% at every horizon — with the effect sizes checked against a measured noise floor. **We are now on Track B.** Remaining Track A items (error analysis, the two explain-backs, dbt docs) are polish and can be picked up alongside.

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
- [x] Write the weather **Previous Runs** ingestion (predictors), stamped by lead offset. *(Client + `reshape_to_long` + `validate()` + per-`issue_date` write loop all live. Range-capable via `daterange_chunks(start, end, chunk_days)` — absolute dates, no `past_days`.)*
- [ ] Write the weather **actuals** ingestion (targets).
- [ ] Write carbon intensity + Agile price ingestion.
- [~] Add Pydantic validation / data contracts to each. *(Hand-rolled `validate()` tripwires exist — non-empty + required columns — but no Pydantic/contract layer. Note: the 2026-08 ingestion bug proved these tripwires are too weak; a truncated group passes every check.)*
- [x] Backfill historical data to bootstrap training (Previous Runs archive). *(Weather + demand backfilled 2024-07-01 → 2026-07-11 — 24 months, two full annual cycles. Weather re-run after the chunk/partition fix below; 734 issue_date partitions, all carrying leads 0–7.)*
- [ ] Write the Lambda + EventBridge + IAM in Terraform. *I write the HCL; you correct syntax. Security pass on the IAM roles — make me justify each permission.*
- [x] **Explain-back:** why is each ingestion write idempotent, and how? *(Deterministic key: same input date → same S3 key → re-runs overwrite. **Caveat learned the hard way:** that only holds when one key's data comes from one fetch. Weather chunks on target date but keys on issue date, so two fetches owned the same key and last-write-wins silently truncated it — see Running notes.)*

---

## Phase 3 — Catalog & Athena

*Goal: query the raw data with SQL, serverlessly. Spec: Phase 3.*

- [x] Provision the S3 data lake bucket in Terraform and upload the local backfill. *(`smart-energy-lake` — private, SSE-S3, versioned, per-prefix lifecycle retention. 1490 objects / 28.5MB synced to `bronze/`, key layout preserved from local so DuckDB and Athena provably read the same bytes.)*
- [x] **Decide: Glue Crawler vs. partition projection. → partition projection, no crawler.** A crawler's job is *discovering* a schema you don't already know; I wrote both writers, so there's nothing to discover — the schema is fixed and the partitions are strictly generable Hive-style `settlement_date=YYYY-MM-DD` / `issue_date=YYYY-MM-DD`, one per day. Projection is free and resolves at query time; a crawler is $0.44/DPU-hour with a 1-minute minimum per run, and new partitions only appear after the next crawl. **What I'm giving up:** the crawler would have caught schema drift — with projection, an upstream field rename silently becomes nulls in a hand-declared column. I own that risk now, which is an argument for hardening the ingestion `validate()` tripwires. **When I'd use a crawler instead:** data whose producer I don't control, or irregular partition values that can't be generated from a pattern.
- [x] Define the Glue Catalog database + tables in Terraform (`aws_glue_catalog_database`, `aws_glue_catalog_table`) — schema declared explicitly, no crawler. *(`infra/glue.tf` — db `bronze` + 3 tables. A catalog table is just a saved `CREATE EXTERNAL TABLE`: `columns`→the col list, `partition_keys`→`PARTITIONED BY`, `ser_de_info`→`ROW FORMAT SERDE`, `input_format`/`output_format`→the Hadoop classes, `location`→`LOCATION`, `parameters`→`TBLPROPERTIES`. **Timestamps typed `string`, not `timestamp`** — Hive wants `yyyy-MM-dd HH:mm:ss` and silently nulls ISO8601; bronze lands as-it-came, the cast belongs in dbt. bank_holidays needs `mapping.<col>` SerDe params because gov.uk uses hyphens, illegal in column names — and `ignore.malformed.json = false` set explicitly, since dropping the crawler means a corrupt file should fail loudly rather than become a row of nulls.)*
- [x] Configure partition projection on the date-partitioned prefixes (`projection.enabled`, `projection.<col>.type = date`, `storage.location.template`). *(The five projection props are a `for` loop: `type` picks the generator, `range` is start/end, `interval` + `interval.unit` the step, `format` renders each value — a Java `DateTimeFormatter` pattern, so `yyyy-MM-dd`, and capital `MM` is months where lowercase `mm` is minutes. **Ranges bounded tightly to the real data**: weather starts `2024-06-24`, seven days before demand, because of forecast lead — an over-tight range hides partitions silently, with zero rows and no error. `$${...}` in the template escapes Terraform's own interpolation.)*
- [x] Set the Athena query-result location with a lifecycle rule. *(`infra/athena.tf` — workgroup `foresight_queries`, results to `s3://smart-energy-lake/athena-results/` with SSE-S3, expiring after 14 days via the plain `expiration` rule as predicted. `bytes_scanned_cutoff_per_query = 100MB` is the cost guardrail — ~3.5× headroom over a full-lake scan, so it catches a runaway cross join without tripping on growth. **`enforce_workgroup_configuration` is `false`, deliberately** — it was `true`, and that silently broke the dbt-athena port: the adapter omits `external_location` from its CTAS when the workgroup enforces configuration (`create_table_as.sql:123`), so Athena defaulted table data to `athena-results/tables/<query-id>/` — inside the 14-day expiry. Silver and gold would have deleted themselves. Enforcement was buying little here anyway: the bucket already sets AES256 default encryption and full public-access block, and the scan cutoff is a separate control that still applies.)*
- [x] Explore the data in Athena; sanity-check it against the DuckDB mart. *I write the queries. (**Bronze-to-bronze cross-engine check — every measure matched exactly**: demand 35,568 records / 929,529,560 sum / 741 partitions; weather 142,272 records / 1,817,394.17 sum / 748 partitions. Float sums agreeing to 2dp across two engines rules out precision loss from the declared types. Also confirmed physically plausible: 26,134 MW mean demand, 12.77 °C mean temp. Gotchas: one row = one file on JSON-envelope tables, so use `cardinality(data)` not `count(*)`; Athena/Trino needs `CROSS JOIN UNNEST(data) AS t(r)` with fields as `r.value`, where DuckDB just does `unnest(data)` in the select list — every staging model needs that rewrite for the dbt-athena port.)*
- [x] **Explain-back:** why Athena over Redshift for this data size? *(**The axis is latency, not size.** Athena pays a fixed ~1–3s plan/spin-up per query but zero when idle; Redshift keeps a cluster warm and pays rent for it. More data, more tables, or more complex SQL do **not** flip it — Athena scales into TB fine and Trino's SQL is genuinely good. What flips it: someone waiting on a sub-second dashboard at sustained concurrency; big-table joins where dist keys colocate rows instead of shuffling over the wire; or needing `UPDATE`/`MERGE`/transactions. Also: Redshift is a database with its own storage, so it needs a `COPY` — a second copy of the truth that can drift — where Athena reads S3 in place. **Best version of the answer:** even with a user-facing dashboard the fix isn't Redshift, it's pre-aggregating the gold layer small, which is what it already is. Caveat to carry: Serverless killed the always-on-cost argument and Iceberg closed much of the mutability gap, so lead with latency, not price.)*

---

## Phase 4 — The Point-in-Time Feature Store (dbt)

*Goal: the engineering centrepiece — leakage-safe features. Spec: Phase 4. Go slow here.*

> **Note — intentional reorder:** the dbt modelling was built **first, locally on DuckDB**, ahead of the Phase 2/3 AWS ingestion + Athena wiring. This let the leakage-critical logic get proven and understood without waiting on infra. That bet paid off, and the port to `dbt-athena` is now complete — DuckDB has been removed entirely rather than kept as a second target, because running two engines is what let the timezone bug hide.

- [x] Set up the dbt project. *(Ported DuckDB → **dbt-athena**; all 5 models rebuilt against Trino and verified digit-for-digit against the DuckDB baseline — 141,584 mart rows, `sum(demand_lag_mw)` 3,702,244,356.5, `sum(temperature_2m)` 1,805,828.498 on both. Dialect notes: `cross join unnest(data) as t(r)` replaces DuckDB's `select unnest(data)`; Trino won't resolve a `group by` name onto a select-list alias, so staging uses ordinals; `date_add('day', -lead_days, ts)` because an interval can't be multiplied by a column. **The one silent semantic change:** `day_of_week()` is 1–7 Monday-first where DuckDB's `extract('dow')` was 0–6 Sunday-first — nothing errors, but the `day` splits mean different days, so the model needs a retrain not a re-point.)*
- [x] Build Silver staging models (clean, typed, half-hourly-aligned, deduplicated). *3 models: `stg_demand`, `stg_weather_forecast` (pivoted long→wide), `stg_bank_holidays` (E&W + Scotland unioned). Tests: not-null/unique on keys, temp validity bounds, holiday grain.*
- [x] Build the Gold feature store. **This is the hard part.** *`fct_demand_features`, grain `(target_ts, lead_days)`. Weather rides the grain (`issue_ts = target − lead`) for free point-in-time correctness; label joined at target (demand aggregated half-hourly→hourly).*
- [x] Engineer lag features and rolling stats that never peek into the future. *`demand_lag_mw` at `cutoff = target − lead − publication_lag` — an **equi-join** onto `int_demand_hourly`, not an ASOF join: the hourly grid is dense, so `d.target_hour = date_trunc('hour', c.cutoff)` lands exactly and needs no "most recent at or before" search. (Rolling stats not yet added — single lag for now.)*
- [x] Add dbt tests, including no-future-leakage assertions. *19 tests: compound-grain uniqueness, not-nulls on keys/label, temperature validity bounds, `assert_heat_cool_signage` (HDD/CDD hinges can't both fire on the same side of `base_temperature`), and now **`assert_leakage_guard`** — the explicit no-future-leakage assertion. The design lesson: keeping `cutoff` in the mart is **not enough on its own**, because `cutoff` stays perfectly correct even if the lag join is repointed at `target_ts`, which is total leakage. What the test needs is **provenance** — which timestamp each predictor was actually read from. So the mart now also emits `issue_ts` and `demand_lag_ts`, and each predictor is checked against the bound it must meet. **Weather gets a different bound on purpose:** `publication_lag_hours` describes BMRS's settlement delay, so it claws back from `prediction_time` for the demand lags but not for a forecast run, which is available the moment it's issued (`issue_ts <= target_ts − lead_days×24h`). Both singular tests are **verified to have teeth** by mutation: swapping the HDD/CDD hinge arms gave `FAIL 141543`; repointing the lag join at `target_ts` gave `FAIL 142264` — every row — while uniqueness, not-nulls and signage all stayed green. Both reverted. Caveat recorded: the weather bound assumes **zero weather publication lag**, which is slightly optimistic since a real NWP run isn't downloadable the instant it's stamped.*
- [ ] Generate dbt docs; screenshot the lineage graph.
- [x] **Explain-back:** pick any feature and make me prove it can't leak. *(Done — weather-vs-demand asymmetry: forecast legal-at-target vs actual forbidden-at-target; demand's sliding cutoff + ASOF.)*

---

## Phase 5 — Forecasting Model & Honest Evaluation

*Goal: a model that beats baseline, validated correctly. Spec: Phase 5. This is the core ML learning — least help here.*

- [x] Build the seasonal-naive baseline FIRST. *(`ml/score_baseline.py` — same hour on the most recent **legal** same-weekday anchor: `lag_7d`, falling back to `lag_14d` at lead 7 where the publication gate makes a 7-day anchor unknowable.)*
- [x] Measure baseline MAE/MAPE. *(Settled on **RMSE as % of mean demand** — RMSE because large misses are what cost a grid operator, normalised so the number is comparable across leads. Baseline: 10.96% at leads 0–6, 12.33% at lead 7.)*
- [x] Implement walk-forward (expanding-window) validation. *(`ml/folds.py` — 12 monthly folds over Jul 2025 – Jun 2026, with a **7-day purge** between each fold's train cutoff and its test window, because a model fitted at `train_end` predicts up to 7 days past it.)*
- [x] Build the LightGBM forecaster on the point-in-time features. *(`ml/train.py` — one pooled model across all leads, `lead_days` as a feature. Deliberately untuned; see Running notes.)*
- [x] Compare to baseline by horizon. *(Beats baseline **23–45%** at every lead, scored on identical rows. Model error degrades monotonically with lead — the sanity check that nothing leaks. Full table in README.)*
- [x] Weather ablation: quantify what the point-in-time forecast pipeline actually buys. *(Removing the 3 weather features costs +0.16pp at lead 1 rising to +0.91pp at lead 6 — weather **flattens the degradation curve** rather than lowering the average. At lead 0 it makes the model slightly *worse*: a measured cost of pooling one model across all horizons.)*
- [x] Establish a noise floor before believing any of it. *(Seed sweep initially returned byte-identical scores — LightGBM is deterministic with bagging off. Re-ran with bagging enabled to manufacture variance: std 0.01–0.04pp, max spread 0.09pp. The weather effects are ~5–10× that, so they're real.)*
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
- **`publication_lag_hours` verified = `2`** (was a `24` placeholder). Measured against the live API 2026-08-03: the settlement period ending 15:00 UK was already published at 15:10 UK, so Elexon's real lag is ~10 min after *period end*. But `demand_hourly` buckets on the hour's **start**, so a bucket isn't complete until 60 min (rest of hour) + ~10 min ≈ **1h10m** after its label; rounded up to 2h for margin. Effects: `demand_lag_mw` is now 22h fresher at every lead (materially better feature); `lag_7d` at lead 6 goes 98.4% → 99.9% filled as the gate gains real margin instead of clearing by exactly zero. **Lead 7 still cannot use `lag_7d` at any lag value** — the anchor at `target−168h` is later than the cutoff at `target−170h`; that's structural, not a tuning knob, which is why `lag_14d` exists.
- **Ownership rule resolved (DESIGN §5):** live vs backfill weather writes collide at the file level (identical `issue_date` path, last-writer-wins). Defence = disjoint ranges by construction + per-client write-once guard (weather fail-closed; demand permissive since outturn gets revised) + delete-to-correct as the deliberate escape hatch. The grain uniqueness test is **not** the backstop (collision resolves before dbt reads).
- **`is_holiday` is all-`false` in the current window** — no E&W bank holiday falls in 10 Jun–11 Jul 2026. Expected, not a bug; the column exercises once the data window spans a real holiday. Division decision: filtered to `eng&wales` (dominates GB demand).
- **Local dev tip (post-DuckDB):** run dbt from inside `dbt/` with `--profiles-dir .` on every invocation, since there's no `~/.dbt`. To step through CTEs, `dbt compile` and open `target/compiled/.../fct_demand_features.sql` — but note dbt-athena wraps the model in a CTAS, so **compiled line numbers sit ~8 lines below source line numbers** in Athena's error messages. `ml/` reads the mart through `pyathena` (`ml/athena.py`) using `PandasCursor`, which pulls the result CSV straight from S3 rather than paging rows back through the Athena API — materially faster at 141k rows. No credentials appear anywhere in that file: identity comes from the boto3 chain (`~/.aws/credentials`), which is why it's safe to commit.
- ~~**Next-session fork:** backfill vs. build baseline first.~~ **Resolved:** did the backfill first (24 months), then baseline + walk-forward on top. Correct call — validation is meaningless without a full annual cycle.
- **Ingestion bug found 2026-08-10 — the chunk key and the partition key must agree.** The weather backfill fetched in chunks of **target** date but landed Bronze partitioned by **issue** date, and one issue date's records span the next 8 target days. Every issue date within 7 days of a chunk boundary was therefore split across two fetches, each writing its own half to the same key — last write wins, silently. Result: a recurring ~6-day hole every 30 days, hitting **short leads hardest** (lead 0 had 29% fewer rows than lead 7), and *nothing errored*, because `validate()` only checks non-empty + column presence and a truncated group passes both. **Fix:** a chunk covering targets `[lo, hi]` may only write issue dates `[lo, hi−7]`, and the loop advances so those *writable* ranges tile contiguously (`cur = hi + 1 − 7`). **Second bug the fix introduced:** subtracting 7 destroyed the forward-progress guarantee, so once `hi` clamped to `end` the loop never terminated — masked by an API rate-limit error that looked like the real problem. Loop condition is now `while cur + 7 <= end`. *Lessons worth being able to say out loud: deterministic-key idempotency assumes one key's data comes from one fetch; a validation that can't fail on truncation isn't validating; and skip-if-exists would have been the wrong fix — it only rescues this by luck of write ordering and blocks corrective re-runs.*
- **Hyperparameters deliberately untuned.** Enabling bagging measured ~0.05pp better at every lead, but adopting it means choosing a hyperparameter by reading the walk-forward scores — at which point those scores stop being an unbiased estimate of generalisation. Recorded in `ml/train.py` and the README rather than taken. *"I set a seed" and "I checked it's stable" are different claims; only the second is evidence.*
- **Feature candidates considered and parked** (not obviously worth the leakage risk yet): `lag_1d`, rolling means (need the point-in-time care the row-wise hinges didn't), cyclical hour encoding, holiday adjacency. Also: derive `base_temperature` empirically from the demand-vs-temperature minimum rather than taking the 15.5°C UK convention.
- **Known reproducibility gap (accepted, not fixed):** 14 Bronze partitions (`2024-06-24…30`, `2026-07-05…11`) survive from the pre-fix run and the corrected code deliberately never writes them. Their contents are correct, but a backfill into an empty `data/` wouldn't reproduce them. Fix when convenient by widening `backfill_start`/`backfill_end` by 7 days each so the wanted window sits inside the writable range.
- **Bronze stays raw JSON; Parquet belongs at silver.** The bronze files carry a `{"data": [...]}` envelope, so both staging models `unnest(data)` — that ports straight to `dbt-athena`, so nothing gets rewritten. The real cost is the **small-files problem**: 1490 objects averaging ~19KB is what Athena is worst at, since per-object overhead dominates the scan. Fix it by materialising *silver* as Parquet, not by reformatting the raw landing zone.
- **Track B starting position (2026-08-10):** AWS account has an IAM user (`joshuaman`, acct `971422716045`), billing alarms/budget set, `eu-west-2`. Terraform backend configured in `infra/backend.tf` against `s3://smart-energy-tfstate` (encrypted, `use_lockfile = true`) — but **`terraform state list` is empty: Terraform manages nothing yet.** The state bucket is the only bucket in the account.
- **Retrain owed (2026-08-16).** The saved LightGBM scores were produced under DuckDB's 0–6 Sunday-first `day` encoding; Trino's `day_of_week()` is 1–7 Monday-first. The feature is now a *different feature* with the same name, so the model needs a **retrain, not a re-point**. The baseline is unaffected and provably so — it never touches `day`, and its scores were bit-identical across the port, which is what isolates the change to the model.
- **`select *` in `ml/train.py` is only safe because `FEATURES` is an explicit allowlist.** The mart now carries `cutoff`, `issue_ts` and `demand_lag_ts` for the leakage guard; all three are pure functions of `target_ts − lead_days`, so a feature list derived from `df.columns` would hand LightGBM the answer key. Worth keeping the allowlist explicit for exactly this reason.
- **Open, unanswered:** (a) should `stg_weather_forecast` assert its variable set is exactly what's expected? The pivot is static conditional aggregation, so a new or renamed upstream variable is silently dropped rather than erroring — the same class of risk as choosing projection over a crawler. (b) The whole suite is **structural**; a semantic test (e.g. demand peaks in an expected evening window) would catch a class of regression none of the current 19 can. (c) Least privilege: the S3 sync ran as `joshuaman`; what's the minimum the ingestion Lambda actually needs?

---

## Definition of done (first pass)

Don't gold-plate. The first pass is **done** when: demand forecasting runs end-to-end, beats the seasonal-naive baseline, is validated walk-forward, deploys and tears down cleanly on AWS, and the README is honest and complete. The Agile-price extension, uncertainty intervals, and the Octopus charging-window layer are **stretch goals** — mention them as "next steps," don't let them block a finished first pass.

> **Feature idea parked for the Agile-price extension — gas/oil prices.** Gas price is a *premier* feature for forecasting electricity **price** (gas plants set the marginal price via merit order, so wholesale gas ≈ the price signal), so it belongs in the Agile-price stretch goal. But it's a **weak/noisy feature for the demand core** — short-run demand is price-inelastic, retail tariffs are capped/lagged so consumers never see the wholesale signal at a 1–7 day horizon, and it's one flat scalar per day so it can't help the intraday shape or weekly deviations that give the edge. Point-in-time legal (market data, published continuously), but fails on *signal*, not legality. General lesson: a feature needs a plausible causal story **at the specific target and horizon** — "it's energy-related" isn't enough.

### Stretch goal: household tariff analysis (real consumption data)

Using my dad's Octopus account (with his permission), pull the house's half-hourly smart-meter consumption via the authenticated Octopus API and join it against Agile half-hourly prices to answer: *what would this house have paid on Agile vs. the current tariff, and what would load-shifting save?* Notes to hold me to when we get here:

- [ ] Confirm permission with my dad first; treat this as his data, not mine.
- [ ] The consumption feed is lagged (typically yesterday's reads), NOT real-time — verify the actual lag against the API docs, and don't use it to justify a streaming layer.
- [ ] Credentials handled properly (never committed; Secrets Manager / env vars) — this is the security section of CLAUDE.md meeting a real authenticated source.
- [ ] Raw consumption data stays out of the public repo: gitignored locally or anonymised; code public, data private.
- [ ] Keep it an *analysis* (tariff comparison, savings estimate), not a household *forecast* — single-home demand is noisy and would make an ugly accuracy story; if I want to attempt a household forecast anyway, frame it explicitly as "here's why this is much harder than national."
- [ ] Interview framing: "my family's real consumption, used with permission" — the value is realness, not exclusivity.