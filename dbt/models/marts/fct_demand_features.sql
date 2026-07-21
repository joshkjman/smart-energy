-- gold/fct_demand_features.sql
-- One row per (target_ts, lead) = one training example.
-- Invariant: every predictor must be knowable as of prediction_time = target_ts - lead.

with pivoted as (
    pivot {{ ref('stg_weather_forecast') }}
    on variable
    using first(value)
),
weather_wide as (
    select
        *,
        extract('day' from target_ts - issue_ts) as lead_days
    from pivoted
),
demand_hourly as (
    select
        date_trunc('hour', start_time) as target_hour,
        avg(initial_demand_outturn) as initial_demand_outturn
    from {{ ref('stg_demand') }}
    group by target_hour
),
labelled as (
    select w.*,
            d.initial_demand_outturn
    from weather_wide w
    left join demand_hourly d on w.target_ts = d.target_hour
)
select *
from labelled

-- calendar as (
--     -- TODO: features from the target itself
--     --   is target a bank holiday? (join stg_bank_holidays on holiday_date = target_ts::date, pick division)
--     --   hour, day-of-week from target_ts
--     select ...
-- ),

-- lagged as (
--     -- TODO (THE hard one — you write this, it's the leakage guard):
--     --   cutoff = target_ts - lead - publication_lag        (use {{ var('publication_lag_hours') }})
--     --   lag_1 = the most recent demand where start_time <= cutoff
--     --   shape: non-equi. correlated/LATERAL subquery, or qualify row_number() over (order by start_time desc)
--     --   RULES: join with <=, never =. anchor to the cutoff, never to target_ts.
--     select ...
-- )

-- select
--     -- keys: target_ts, lead
--     -- label: initial_demand_outturn
--     -- features: weather cols, calendar cols, lag cols
-- from ...