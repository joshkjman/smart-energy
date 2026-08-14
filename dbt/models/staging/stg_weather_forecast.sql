with raw as (
    select unnest(data) as r
    from {{ source('bronze', 'weather_forecast') }}
)
select
    r.target_ts as target_ts,
    r.issue_ts as issue_ts,
    r.N as lead_days,
    max(r.value) filter (where regexp_replace(r.variable, '_previous_day\d+$', '') = 'temperature_2m') as temperature_2m
from raw
group by target_ts, issue_ts, lead_days
