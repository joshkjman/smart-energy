{{ config(
    materialized = "incremental",
    incremental_strategy = "insert_overwrite",
    partitioned_by = ["target_date"]
) }}

with raw as (
    select  cast(from_iso8601_timestamp(r.target_ts) at time zone 'UTC' as timestamp) as target_ts,
            target_date,
            r.variable,
            r.value
    from {{ source('bronze', 'weather_actual') }}
    cross join unnest(data) as t(r)
    {% if is_incremental() %}
    where target_date >= cast((current_date - interval '7' day) as varchar)
    {% endif %}
)
select
    target_ts,
    max(value) filter (where variable = 'temperature_2m') as temperature_2m,
    max(value) filter (where variable = 'shortwave_radiation') as shortwave_radiation,
    target_date
from raw
group by 1, 4
