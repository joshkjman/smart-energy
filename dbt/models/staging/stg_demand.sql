{{ config(
    materialized = "incremental",
    incremental_strategy = "insert_overwrite",
    partitioned_by = ["settlement_date"]
) }}

with raw as (
    select r          
    from {{ source('bronze', 'demand') }}
    cross join unnest(data) as t(r) -- explode the 48-row array into rows
    {% if is_incremental() %}
    where settlement_date >= cast((current_date - interval '7' day) as varchar)
    {% endif %}
)
select
    cast(from_iso8601_timestamp(r.publishtime) at time zone 'UTC' as timestamp) as publish_time,
    cast(from_iso8601_timestamp(r.starttime) at time zone 'UTC' as timestamp) as start_time,
    r.settlementperiod as settlement_period,
    r.initialdemandoutturn as initial_demand_outturn,
    r.initialtransmissionsystemdemandoutturn as initial_transmission_system_demand_outturn,
    cast(r.settlementdate as date) as settlement_date
from raw

