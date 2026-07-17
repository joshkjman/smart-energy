# Foresight — Design Decisions

Running record of the *why* behind the architecture. Not a status tracker
(that's PLAN.md) — this is the reasoning I'd need to defend in an interview.

---

## 1. Medallion layering (Bronze / Silver / Gold)

[What each layer is responsible for, and the one rule that defines Bronze
(land faithfully, no cleaning). Where does typing/dedup happen? Where do
features get built?]

## 2. Point-in-time correctness (the core constraint)

[The two timestamps — target_ts vs issue_ts — in your own words. Why every
predictor feature must be knowable as of issue_ts. Where leakage is actually
prevented: what Bronze's job is vs what Gold's job is. Finish the sentence:
"Bronze remembers ____; Gold admits only ____."]

target_ts is the time that you want to predict, and issue_ts is the date of the prediction for that certain target_ts.
Every predictor feature must be knowable as of issue_ts so you can actually predict a target_ts as of issue_ts, and use the historical ones for training.
One form of this (weather features) is using predicted not actual values, because at predict time you only have predicted values not actual values of the future.
Bronze stamps each value with its issue_ts (when it became known), and Gold admits only features passing issue_ts + publication_lag ≤ prediction_time.

## 3. Why forecasts-as-issued, never actuals

[Train/serve symmetry. Why training features must match what the model sees
in production, and what breaks if you train on reanalysis actuals instead.]

## 4. Two weather clients: live vs backfill

[The distinction you landed on. Same *values*, different availabilty. Which endpoint
is operational vs archive. Which one serves the production hot path, which one
is the training-history cold-start, and why you can't just use one for both.]

Same *values*, different availabilty. The backfill/previous runs API is the archive data which is used for the training-history cold-start whereas the live is operational used for production hot path.
Can't use previous runs for prod hot path because it doesnt have the same availability, or as low latency.

## 5. Ownership / precedence rule (known gap)

[When both clients can write the same issue_date, who wins and why. Note that
no guard enforces this yet, and when it actually bites (window overlap).]

I keep the past days api data separate to the live api data, so there shouldn't be an overlap because I only use past days for historical data and then the live data for future/current forecasts.
The data written first is the data that will remain in the issue_date folder. I avoid overlapping by only allowing write_bronze to write in empty/non-existent issue_date subfolders.
If the data is actually wrong and I want to overwrite it, I delete it first then write again with the correct data. This only works with the weather forecast, which has to be reflected in write_bronze.

## 6. The wide -> long reshape (melt)

[Why the melt is a legitimate Bronze operation and not "cleaning". The subtlety
worth recording: backfill melts the ISSUE axis (previous_dayN), live melts the
VARIABLE axis — same tool, different job.]

the target-row window (past_days→forecast_days), each target's previous-day offsets, issue_ts = target − N, group-by-issue for landing, diagonals-clip-at-the-edge. Keep the two tweaks (N is the offset; each partition's targets sit 0–7 days ahead). And add the one line that makes the melt legitimate rather than "cleaning": the values are never touched — you're just re-indexing the same numbers from a target frame to an issue frame.

## 7. Partitioning

[Why weather partitions on issue_date (not target date) and demand on settlement
date. Tie it back to the Bronze principle: "what we knew, when."]

## 8. Resolution mismatch (deferred)

[Weather is hourly, demand is half-hourly. Where this gets reconciled and why
NOT at ingestion.]

## 9. Single-point GB-aggregate weather

[Why one representative lat/lon is defensible for a national demand target v1.]
