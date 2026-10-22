with raw as (
    select  cast(from_iso8601_timestamp(r.target_ts) at time zone 'UTC' as timestamp) as target_ts,
            target_date,
            r.variable,
            r.value
    from {{ source('bronze', 'weather_actual') }}
    cross join unnest(data) as t(r)
)
select
    target_ts,
    target_date,
    max(value) filter (where variable = 'temperature_2m') as temperature_2m,
    max(value) filter (where variable = 'shortwave_radiation') as shortwave_radiation
from raw
group by 1, 2
