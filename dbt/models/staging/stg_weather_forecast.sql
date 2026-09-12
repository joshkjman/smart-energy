with raw as (
    select  cast(from_iso8601_timestamp(r.target_ts) at time zone 'UTC' as timestamp) as target_ts,
            cast(from_iso8601_timestamp(r.issue_ts) at time zone 'UTC' as timestamp) as issue_ts,
            r.variable,
            r.value
    from {{ source('bronze', 'weather_forecast') }}
    cross join unnest(data) as t(r)
)
select
    target_ts,
    issue_ts,
    date_diff('day', issue_ts, date_trunc('day', target_ts)) as lead_days,
    max(value) filter (where regexp_replace(variable, '_previous_day\d+$', '') = 'temperature_2m') as temperature_2m,
    max(value) filter (where regexp_replace(variable, '_previous_day\d+$', '') = 'shortwave_radiation') as shortwave_radiation
from raw
group by 1, 2, 3
