with raw as (
    select r
    from {{ source('bronze', 'weather_forecast') }}
    cross join unnest(data) as t(r)
)
select
    cast(from_iso8601_timestamp(r.target_ts) at time zone 'UTC' as timestamp) as target_ts,
    cast(from_iso8601_timestamp(r.issue_ts) at time zone 'UTC' as timestamp) as issue_ts,
    r.n as lead_days,
    max(r.value) filter (where regexp_replace(r.variable, '_previous_day\d+$', '') = 'temperature_2m') as temperature_2m
from raw
group by 1, 2, 3
