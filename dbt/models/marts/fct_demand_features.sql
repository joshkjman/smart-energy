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
            d.initial_demand_outturn as demand_mw
    from weather_wide w
    left join demand_hourly d on w.target_ts = d.target_hour
),
cutoff_data as (
    select *,
        (target_ts - lead_days * interval '1 day' - interval {{ var('publication_lag_hours') }} hour) as cutoff
    from labelled
),
lagged as (
    select c.*,
        d.initial_demand_outturn as demand_lag_mw
    from cutoff_data c
    asof left join demand_hourly d
    on d.target_hour <= c.cutoff
),
calendar as (
    select *
    from lagged l
    left join {{ ref('stg_bank_holidays') }} b
    on l.target_ts::date = b.holiday_date
    and division = 'eng&wales'
)
select
    target_ts,
    extract('hour' from target_ts) as hour,
    extract('dow' from target_ts) as day,
    lead_days,
    demand_mw,
    demand_lag_mw,
    holiday_date is not null as is_holiday,
    variable
from calendar