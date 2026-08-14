with raw as (
    select unnest(data) as r
    from {{ source('bronze', 'weather_forecast') }}
)
select
    r.target_ts as target_ts,
    r.issue_ts as issue_ts,
    r.N as lead_days,
    regexp_replace(r.variable, '_previous_day\d+$', '') as variable,
    r.value as value
from raw