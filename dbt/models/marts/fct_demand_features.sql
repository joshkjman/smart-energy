-- gold/fct_demand_features.sql
-- One row per (target_ts, lead) = one training example.
-- Invariant: every predictor must be knowable as of prediction_time = target_ts - lead.


with labelled as (
    select w.*,
            d.avg_initial_demand_outturn as demand_mw
    from {{ ref('stg_weather_forecast') }} w
    left join {{ ref('int_demand_hourly' )}} d on w.target_ts = d.target_hour
),
cutoff_data as (
    select *,
        date_add('hour', -{{ var('publication_lag_hours') }}, date_add('day', -lead_days, target_ts)) as cutoff
    from labelled
),
lagged as (
    select c.*,
        d.avg_initial_demand_outturn as demand_lag_mw
    from cutoff_data c
    left join {{ ref('int_demand_hourly' )}} d
    on d.target_hour = date_trunc('hour', c.cutoff)
),
seasonal_naive as (
    select
        l.*,
        case
            when (l.target_ts - interval '168' hour) <= cutoff then d7.avg_initial_demand_outturn
            else null
        end as lag_7d,
        case
            when (l.target_ts - interval '336' hour) <= cutoff then d14.avg_initial_demand_outturn
            else null
        end as lag_14d
    from lagged l
    left join {{ ref('int_demand_hourly' )}} d7
      on d7.target_hour = (l.target_ts - interval '168' hour)
    left join {{ ref('int_demand_hourly' )}} d14
      on d14.target_hour = (l.target_ts - interval '336' hour)
),
local_ts as (
    select  *,
            cast(with_timezone(target_ts, 'UTC') at time zone 'Europe/London' as timestamp) as target_ts_local
    from seasonal_naive
),
calendar as (
    select *
    from local_ts l
    left join {{ ref('stg_bank_holidays') }} b
    on cast(l.target_ts_local as date) = b.holiday_date
    and division = 'eng&wales'
)
select
    target_ts,
    extract(hour from target_ts_local)  as hour,
    day_of_week(target_ts_local)  as day,
    lead_days,
    demand_mw,
    demand_lag_mw,
    lag_7d,
    lag_14d,
    holiday_date is not null as is_holiday,
    temperature_2m,
    greatest({{ var('base_temperature') }} - temperature_2m, 0) as heating_degrees,
    greatest(temperature_2m - {{ var('base_temperature') }}, 0) as cooling_degrees
from calendar
where demand_mw is not null
and demand_lag_mw is not null