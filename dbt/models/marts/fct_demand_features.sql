-- gold/fct_demand_features.sql
-- One row per (target_ts, lead) = one training example.
-- Invariant: every predictor must be knowable as of prediction_time = target_ts - lead.


with weather_wide as (
    pivot {{ ref('stg_weather_forecast') }}
    on variable
    using first(value)
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
seasonal_naive as (
    select
        l.*,
        case
            when (l.target_ts - interval '168 hours') <= cutoff then d7.initial_demand_outturn
            else null
        end as lag_7d,
        case
            when (l.target_ts - interval '336 hours') <= cutoff then d14.initial_demand_outturn
            else null
        end as lag_14d
    from lagged l
    left join demand_hourly d7
      on d7.target_hour = (l.target_ts - interval '168 hours')
    left join demand_hourly d14
      on d14.target_hour = (l.target_ts - interval '336 hours')
),
calendar as (
    select *
    from seasonal_naive s
    left join {{ ref('stg_bank_holidays') }} b
    on s.target_ts::date = b.holiday_date
    and division = 'eng&wales'
)
select
    target_ts,
    extract('hour' from target_ts) as hour,
    extract('dow' from target_ts) as day,
    lead_days,
    demand_mw,
    demand_lag_mw,
    lag_7d,
    lag_14d,
    holiday_date is not null as is_holiday,
    temperature_2m
from calendar
where demand_mw is not null
and demand_lag_mw is not null